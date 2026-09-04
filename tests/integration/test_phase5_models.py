"""Phase 5 ORMモデルと0004→0005 migrationの結合テスト。"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db import (
    create_database,
    get_head_revision,
    migration_runner,
    upgrade_database,
)
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    AuditLog,
    Campus,
    CourseProject,
    LessonRequest,
    Student,
    Subject,
    Teacher,
    TimeSlot,
)


def _alembic_config(engine: Engine) -> Config:
    config = Config()
    migration_directory = Path(migration_runner.__file__).resolve().parent / "alembic"
    config.set_main_option("script_location", str(migration_directory))
    config.attributes["connection"] = engine.connect()
    return config


def _run_alembic(engine: Engine, revision: str, *, downgrade: bool = False) -> None:
    config = _alembic_config(engine)
    connection = config.attributes["connection"]
    try:
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)
    finally:
        connection.close()


def _assert_no_metadata_diff(engine: Engine) -> None:
    config = _alembic_config(engine)
    connection = config.attributes["connection"]
    try:
        command.check(config)
    finally:
        connection.close()


def _add_graph(session: Session) -> tuple[int, int, int, int]:
    campus = Campus(name="架空みらい校")
    student = Student(
        external_id="S-P5-MIG-001",
        name="架空 生徒",
        grade="中学2年",
        default_max_consecutive_slots=2,
        allow_gap=False,
        active=True,
    )
    teacher = Teacher(
        external_id="T-P5-MIG-001",
        name="架空 講師",
        allow_gap=False,
        active=True,
    )
    subject = Subject(
        code="P5_MIG_MATH",
        display_name="中学校・数学",
        school_level="中学校",
        sort_order=501,
        active=True,
    )
    session.add_all([campus, student, teacher, subject])
    session.flush()
    project = CourseProject(
        campus_id=campus.id,
        title="Phase 5 migration確認",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        status="editing",
        file_version=1,
    )
    session.add(project)
    session.flush()
    slot = TimeSlot(
        project_id=project.id,
        code="A",
        display_name="Aコマ",
        start_time=time(17, 10),
        end_time=time(18, 30),
        sort_order=1,
        enabled=True,
    )
    request = LessonRequest(
        project_id=project.id,
        student_id=student.id,
        subject_id=subject.id,
        required_sessions=1,
        regular_teacher_id_optional=teacher.id,
        regular_teacher_priority=3,
        one_to_one_required=False,
    )
    session.add_all([slot, request])
    session.flush()
    return project.id, request.id, teacher.id, slot.id


def test_upgrade_from_0004_preserves_rows_and_sets_compatible_defaults(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "日本語フォルダー" / "Phase5移行.jukuschedule")
    try:
        _run_alembic(database.engine, "20260728_0004")
        with database.session_factory.begin() as session:
            project_id, request_id, teacher_id, slot_id = _add_graph(session)
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO assignments (
                        project_id, lesson_request_id, session_index, date,
                        time_slot_id, teacher_id, is_locked, is_manual, created_by
                    ) VALUES (
                        :project_id, :request_id, 1, '2026-08-05',
                        :slot_id, :teacher_id, 0, 1, 'manual'
                    )
                    """
                ),
                {
                    "project_id": project_id,
                    "request_id": request_id,
                    "slot_id": slot_id,
                    "teacher_id": teacher_id,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_logs (
                        project_id, action, entity_type, entity_id,
                        before_json, after_json
                        ) VALUES (
                            :project_id, 'phase3_import', 'ImportBatch', '1',
                            NULL, :after_json
                        )
                        """
                ),
                {"project_id": project_id, "after_json": '{"件数":1}'},
            )

        upgrade_database(database.engine)

        assert get_head_revision() == "20260904_0010"
        audit_check_names = {
            constraint["name"]
            for constraint in inspect(database.engine).get_check_constraints("audit_logs")
        }
        assert "ck_audit_logs_source_value" in audit_check_names
        assert "ck_audit_logs_ck_audit_logs_source_value" not in audit_check_names
        with database.session_factory.begin() as session:
            assignment = session.query(Assignment).one()
            audit = session.query(AuditLog).one()
            assert assignment.note is None
            assert audit.reason is None
            assert audit.source == "system"
            assert audit.operation_id_optional is None
            assignment.note = "保護者から時間変更の連絡"
            audit.reason = "既存監査行の互換性確認"
            audit.source = "import"
            audit.operation_id_optional = "00000000-0000-0000-0000-000000000005"

        _assert_no_metadata_diff(database.engine)
    finally:
        database.dispose()


def test_constraints_and_downgrade_preserve_pre_phase5_data(tmp_path: Path) -> None:
    database = create_database(tmp_path / "Phase5_downgrade.jukuschedule")
    try:
        upgrade_database(database.engine)
        with database.session_factory.begin() as session:
            project_id, request_id, teacher_id, slot_id = _add_graph(session)
            assignment = Assignment(
                project_id=project_id,
                lesson_request_id=request_id,
                session_index=1,
                date=date(2026, 8, 5),
                time_slot_id=slot_id,
                teacher_id=teacher_id,
                is_locked=True,
                is_manual=True,
                created_by="manual",
                note="日本語の備考",
            )
            audit = AuditLog(
                project_id=project_id,
                action="move",
                entity_type="AssignmentSession",
                entity_id=f"{request_id}:1",
                before_json='{"date":"2026-08-04"}',
                after_json='{"date":"2026-08-05"}',
                reason="授業日変更",
                source="manual",
            )
            session.add_all([assignment, audit])

        with database.session_factory() as session:
            invalid = AuditLog(
                project_id=project_id,
                action="move",
                entity_type="AssignmentSession",
                entity_id=f"{request_id}:1",
                source="external",
            )
            session.add(invalid)
            with pytest.raises(IntegrityError):
                session.flush()

        _run_alembic(database.engine, "20260728_0004", downgrade=True)

        assignment_columns = {
            column["name"] for column in inspect(database.engine).get_columns("assignments")
        }
        audit_columns = {
            column["name"] for column in inspect(database.engine).get_columns("audit_logs")
        }
        assert "note" not in assignment_columns
        assert {"reason", "source", "operation_id_optional"}.isdisjoint(audit_columns)
        with database.engine.connect() as connection:
            assert connection.execute(
                text(
                    """
                    SELECT date, is_locked, is_manual, created_by
                    FROM assignments
                    """
                )
            ).one() == ("2026-08-05", 1, 1, "manual")
            assert connection.execute(
                text(
                    """
                    SELECT action, entity_type, entity_id, before_json, after_json
                    FROM audit_logs
                    """
                )
            ).one() == (
                "move",
                "AssignmentSession",
                f"{request_id}:1",
                '{"date":"2026-08-04"}',
                '{"date":"2026-08-05"}',
            )
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260728_0004"
            )
    finally:
        database.dispose()
