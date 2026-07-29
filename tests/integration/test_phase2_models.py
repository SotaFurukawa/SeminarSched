"""Phase 2 ORMモデルと0001→0002 migrationの結合テスト。"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db import create_database, migration_runner, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    Campus,
    CourseProject,
    LessonRequest,
    OpenDate,
    Student,
    Subject,
    Teacher,
    TeacherQualification,
    TimeSlot,
)

_PHASE2_TABLES = {
    "alembic_version",
    "application_metadata",
    "campuses",
    "course_projects",
    "lesson_requests",
    "open_dates",
    "students",
    "subjects",
    "teacher_qualifications",
    "teachers",
    "time_slots",
}


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


def _add_minimum_graph(
    session: Session,
) -> tuple[
    Campus,
    CourseProject,
    Student,
    Teacher,
    Subject,
    LessonRequest,
]:
    campus = Campus(
        name="架空みらい校",
        address_optional="東京都テスト区1-2-3",
        logo_path_optional="画像/校舎ロゴ.png",
    )
    session.add(campus)
    session.flush()
    project = CourseProject(
        campus_id=campus.id,
        title="2026年度 夏期講習",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 8, 31),
        status="editing",
        file_version=1,
    )
    student = Student(
        external_id="生徒-001",
        name="架空 花子",
        grade="中学2年",
        default_max_consecutive_slots=2,
        allow_gap=False,
        note="テスト用の架空データ",
        active=True,
    )
    teacher = Teacher(
        external_id="講師-001",
        name="架空 太郎",
        allow_gap=False,
        note=None,
        active=True,
    )
    subject = Subject(
        code="JH_MATH",
        display_name="中学校・数学",
        school_level="中学校",
        sort_order=2,
        active=True,
    )
    session.add_all([project, student, teacher, subject])
    session.flush()
    request = LessonRequest(
        project_id=project.id,
        student_id=student.id,
        subject_id=subject.id,
        required_sessions=4,
        regular_teacher_id_optional=teacher.id,
        regular_teacher_priority=5,
        preferred_teacher_1_id_optional=teacher.id,
        preferred_teacher_2_id_optional=None,
        preferred_teacher_3_id_optional=None,
        one_to_one_required=True,
        max_consecutive_slots_override_optional=3,
        allow_gap_override_optional=False,
        note="通常担当必須",
    )
    session.add_all(
        [
            TimeSlot(
                project_id=project.id,
                code="Y",
                display_name="Yコマ",
                start_time=time(14, 10),
                end_time=time(15, 30),
                sort_order=1,
                enabled=True,
            ),
            OpenDate(
                project_id=project.id,
                date=date(2026, 7, 20),
                is_open=True,
                note="初日",
            ),
            TeacherQualification(
                teacher_id=teacher.id,
                subject_id=subject.id,
                can_teach=True,
                note="明示登録",
            ),
            request,
        ]
    )
    return campus, project, student, teacher, subject, request


def test_upgrade_from_0001_preserves_metadata_and_accepts_japanese_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "日本語プロジェクト" / "2026_夏期講習.jukuschedule"
    database = create_database(database_path)

    try:
        _run_alembic(database.engine, "20260728_0001")
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO application_metadata(key, value, updated_at) "
                    "VALUES ('表示名', '既存データ', CURRENT_TIMESTAMP)"
                )
            )

        _run_alembic(database.engine, "20260728_0002")

        assert database_path.is_file()
        assert set(inspect(database.engine).get_table_names()) == _PHASE2_TABLES
        with database.engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260728_0002"
            )
            assert (
                connection.execute(
                    text("SELECT value FROM application_metadata WHERE key = '表示名'")
                ).scalar_one()
                == "既存データ"
            )

        with database.session_factory() as session:
            graph = _add_minimum_graph(session)
            session.commit()
            _, project, student, teacher, subject, request = graph
            assert request.regular_teacher_id_optional == teacher.id
            assert (
                session.scalar(select(Student.name).where(Student.id == student.id)) == "架空 花子"
            )
            assert project.title == "2026年度 夏期講習"
            assert subject.display_name == "中学校・数学"
    finally:
        database.dispose()


def test_database_constraints_and_teacher_ondelete_policy(tmp_path: Path) -> None:
    database = create_database(tmp_path / "制約確認.jukuschedule")
    upgrade_database(database.engine)

    try:
        with database.session_factory() as session:
            _, project, student, teacher, subject, request = _add_minimum_graph(session)
            session.commit()

            duplicate = LessonRequest(
                project_id=project.id,
                student_id=student.id,
                subject_id=subject.id,
                required_sessions=1,
                regular_teacher_priority=1,
            )
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            invalid_slot = TimeSlot(
                project_id=project.id,
                code="X",
                display_name="不正コマ",
                start_time=time(18, 0),
                end_time=time(17, 0),
                sort_order=9,
                enabled=True,
            )
            session.add(invalid_slot)
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            persisted_teacher = session.get(Teacher, teacher.id)
            assert persisted_teacher is not None
            session.delete(persisted_teacher)
            session.commit()

            persisted_request = session.get(LessonRequest, request.id)
            assert persisted_request is not None
            assert persisted_request.regular_teacher_id_optional is None
            assert persisted_request.preferred_teacher_1_id_optional is None
            assert (
                session.get(
                    TeacherQualification,
                    (teacher.id, subject.id),
                )
                is None
            )
    finally:
        database.dispose()


def test_downgrade_to_0001_drops_only_phase2_tables(tmp_path: Path) -> None:
    database = create_database(tmp_path / "downgrade.jukuschedule")

    try:
        upgrade_database(database.engine)
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO application_metadata(key, value, updated_at) "
                    "VALUES ('日本語', '保持', CURRENT_TIMESTAMP)"
                )
            )

        _run_alembic(
            database.engine,
            "20260728_0001",
            downgrade=True,
        )

        assert set(inspect(database.engine).get_table_names()) == {
            "alembic_version",
            "application_metadata",
        }
        with database.engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT value FROM application_metadata WHERE key = '日本語'")
                ).scalar_one()
                == "保持"
            )
    finally:
        database.dispose()
