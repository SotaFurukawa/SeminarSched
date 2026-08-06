"""Phase 4 ORMモデルと0003→0004 migrationの結合テスト。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text
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
    Campus,
    CourseProject,
    LessonRequest,
    OptimizationRun,
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


def _add_graph(
    session: Session,
) -> tuple[CourseProject, LessonRequest, Teacher, TimeSlot]:
    campus = Campus(name="架空ひかり校")
    student = Student(
        external_id="S-P4-001",
        name="架空 生徒",
        grade="中学2年",
        default_max_consecutive_slots=2,
        allow_gap=False,
        active=True,
    )
    teacher = Teacher(
        external_id="T-P4-001",
        name="架空 講師",
        allow_gap=False,
        active=True,
    )
    subject = Subject(
        code="P4_JH_MATH",
        display_name="中学校・数学",
        school_level="中学校",
        sort_order=100,
        active=True,
    )
    session.add_all([campus, student, teacher, subject])
    session.flush()
    project = CourseProject(
        campus_id=campus.id,
        title="Phase 4 日本語プロジェクト",
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
        required_sessions=2,
        regular_teacher_id_optional=teacher.id,
        regular_teacher_priority=5,
        one_to_one_required=False,
    )
    session.add_all([slot, request])
    session.flush()
    return project, request, teacher, slot


def _run(project_id: int) -> OptimizationRun:
    return OptimizationRun(
        project_id=project_id,
        started_at=datetime(2026, 7, 29, 1, 0, tzinfo=UTC),
        finished_at=datetime(2026, 7, 29, 1, 0, 1, tzinfo=UTC),
        status="completed",
        solver_status="OPTIMAL",
        time_limit_seconds=30,
        objective_summary_json=json.dumps(
            {"unassigned": 0, "preference_score": 10},
            ensure_ascii=False,
        ),
        unassigned_count=0,
        warning_count=0,
        log_path_optional=None,
        input_snapshot_json=json.dumps(
            {"project_id": str(project_id), "label": "架空入力"},
            ensure_ascii=False,
        ),
        result_snapshot_json=json.dumps(
            {"previous_assignments": [], "assigned_count": 1},
            ensure_ascii=False,
        ),
        random_seed=42,
        elapsed_seconds=0.25,
    )


def test_upgrade_from_0003_preserves_data_and_matches_metadata(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "日本語フォルダー" / "時間割.jukuschedule")
    try:
        _run_alembic(database.engine, "20260728_0003")
        with database.session_factory.begin() as session:
            project, request, teacher, slot = _add_graph(session)
            ids = (project.id, request.id, teacher.id, slot.id)

        upgrade_database(database.engine)

        assert get_head_revision() == "20260807_0007"
        tables = set(inspect(database.engine).get_table_names())
        assert {"assignments", "optimization_runs"} <= tables
        with database.engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260807_0007"
            )

        project_id, request_id, teacher_id, slot_id = ids
        with database.session_factory.begin() as session:
            run = _run(project_id)
            session.add(run)
            session.flush()
            assignment = Assignment(
                project_id=project_id,
                lesson_request_id=request_id,
                session_index=1,
                date=date(2026, 8, 5),
                time_slot_id=slot_id,
                teacher_id=teacher_id,
                optimization_run_id_optional=run.id,
                is_locked=True,
                is_manual=False,
                created_by="solver",
            )
            session.add(assignment)
            session.flush()
            assignment_id = assignment.id
            run_id = run.id

        with database.session_factory() as session:
            persisted = session.get(Assignment, assignment_id)
            persisted_run = session.get(OptimizationRun, run_id)
            assert persisted is not None
            assert persisted.is_locked is True
            assert persisted_run is not None
            snapshot = json.loads(persisted_run.result_snapshot_json)
            assert snapshot["previous_assignments"] == []
            assert persisted_run.elapsed_seconds == pytest.approx(0.25)

        _assert_no_metadata_diff(database.engine)
    finally:
        database.dispose()


def test_phase4_foreign_keys_uniqueness_checks_and_delete_policy(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "制約確認_Phase4.jukuschedule")
    upgrade_database(database.engine)
    try:
        with database.session_factory.begin() as session:
            project, request, teacher, slot = _add_graph(session)
            run = _run(project.id)
            session.add(run)
            session.flush()
            assignment = Assignment(
                project_id=project.id,
                lesson_request_id=request.id,
                session_index=1,
                date=date(2026, 8, 5),
                time_slot_id=slot.id,
                teacher_id=teacher.id,
                optimization_run_id_optional=run.id,
                is_locked=False,
                is_manual=False,
                created_by="solver",
            )
            session.add(assignment)
            session.flush()
            ids = (
                project.id,
                request.id,
                teacher.id,
                slot.id,
                run.id,
                assignment.id,
            )

        project_id, request_id, teacher_id, slot_id, run_id, assignment_id = ids
        with database.session_factory() as session:
            session.add(
                Assignment(
                    project_id=project_id,
                    lesson_request_id=request_id,
                    session_index=1,
                    date=date(2026, 8, 6),
                    time_slot_id=slot_id,
                    teacher_id=teacher_id,
                    is_locked=False,
                    is_manual=False,
                    created_by="solver",
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            session.add(
                Assignment(
                    project_id=project_id,
                    lesson_request_id=request_id,
                    session_index=0,
                    date=date(2026, 8, 6),
                    time_slot_id=slot_id,
                    teacher_id=teacher_id,
                    is_locked=False,
                    is_manual=False,
                    created_by="solver",
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            session.add(
                OptimizationRun(
                    project_id=project_id,
                    status="completed",
                    solver_status="INVALID_VALUE",
                    time_limit_seconds=30,
                    unassigned_count=0,
                    warning_count=0,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            persisted_request = session.get(LessonRequest, request_id)
            assert persisted_request is not None
            session.delete(persisted_request)
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            persisted_teacher = session.get(Teacher, teacher_id)
            assert persisted_teacher is not None
            session.delete(persisted_teacher)
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            persisted_slot = session.get(TimeSlot, slot_id)
            assert persisted_slot is not None
            session.delete(persisted_slot)
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            persisted_run = session.get(OptimizationRun, run_id)
            assert persisted_run is not None
            session.delete(persisted_run)
            session.commit()
            session.expunge_all()
            persisted_assignment = session.get(Assignment, assignment_id)
            assert persisted_assignment is not None
            assert persisted_assignment.optimization_run_id_optional is None

            persisted_project = session.get(CourseProject, project_id)
            assert persisted_project is not None
            session.delete(persisted_project)
            session.commit()
            session.expunge_all()
            assert session.get(Assignment, assignment_id) is None
            assert (
                session.scalar(
                    select(OptimizationRun).where(OptimizationRun.project_id == project_id)
                )
                is None
            )
    finally:
        database.dispose()


def test_assignment_rejects_cross_project_request_and_slot(tmp_path: Path) -> None:
    database = create_database(tmp_path / "project_scope.jukuschedule")
    upgrade_database(database.engine)
    try:
        with database.session_factory.begin() as session:
            first = _add_graph(session)
            second_campus = Campus(name="架空別校")
            session.add(second_campus)
            session.flush()
            second_project = CourseProject(
                campus_id=second_campus.id,
                title="別プロジェクト",
                start_date=date(2026, 8, 1),
                end_date=date(2026, 8, 31),
                status="editing",
                file_version=1,
            )
            session.add(second_project)
            session.flush()
            second_slot = TimeSlot(
                project_id=second_project.id,
                code="B",
                display_name="Bコマ",
                start_time=time(18, 40),
                end_time=time(20, 0),
                sort_order=1,
                enabled=True,
            )
            session.add(second_slot)
            session.flush()
            first_project, first_request, teacher, _first_slot = first
            values = (
                first_project.id,
                first_request.id,
                teacher.id,
                second_project.id,
                second_slot.id,
            )

        (
            project_id,
            request_id,
            teacher_id,
            second_project_id,
            foreign_slot_id,
        ) = values
        with database.session_factory() as session:
            session.add(
                Assignment(
                    project_id=project_id,
                    lesson_request_id=request_id,
                    session_index=1,
                    date=date(2026, 8, 5),
                    time_slot_id=foreign_slot_id,
                    teacher_id=teacher_id,
                    is_locked=False,
                    is_manual=False,
                    created_by="solver",
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            session.add(
                Assignment(
                    project_id=second_project_id,
                    lesson_request_id=request_id,
                    session_index=1,
                    date=date(2026, 8, 5),
                    time_slot_id=foreign_slot_id,
                    teacher_id=teacher_id,
                    is_locked=False,
                    is_manual=False,
                    created_by="solver",
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
    finally:
        database.dispose()


def test_downgrade_to_0003_removes_only_phase4_schema(tmp_path: Path) -> None:
    database = create_database(tmp_path / "downgrade_Phase4.jukuschedule")
    try:
        upgrade_database(database.engine)
        with database.session_factory.begin() as session:
            project, request, teacher, slot = _add_graph(session)
            run = _run(project.id)
            session.add(run)
            session.flush()
            session.add(
                Assignment(
                    project_id=project.id,
                    lesson_request_id=request.id,
                    session_index=1,
                    date=date(2026, 8, 5),
                    time_slot_id=slot.id,
                    teacher_id=teacher.id,
                    optimization_run_id_optional=run.id,
                    is_locked=False,
                    is_manual=False,
                    created_by="solver",
                )
            )

        _run_alembic(database.engine, "20260728_0003", downgrade=True)

        inspector = inspect(database.engine)
        assert "assignments" not in inspector.get_table_names()
        assert "optimization_runs" not in inspector.get_table_names()
        assert "ix_lesson_requests_project_id_id_unique" not in {
            index["name"] for index in inspector.get_indexes("lesson_requests")
        }
        with database.engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260728_0003"
            )
            assert (
                connection.execute(text("SELECT title FROM course_projects")).scalar_one()
                == "Phase 4 日本語プロジェクト"
            )
    finally:
        database.dispose()
