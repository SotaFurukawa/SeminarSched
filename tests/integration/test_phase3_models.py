"""Phase 3 ORMモデルと0002→0003 migrationの結合テスト。"""

from __future__ import annotations

import json
from datetime import date, time
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
    AuditLog,
    Campus,
    CourseProject,
    GroupLesson,
    GroupLessonStudent,
    ImportBatch,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TimeSlot,
    ValidationIssue,
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
_PHASE3_TABLES = _PHASE2_TABLES | {
    "audit_logs",
    "group_lesson_students",
    "group_lessons",
    "import_batches",
    "student_availabilities",
    "teacher_availabilities",
    "validation_issues",
}
_CURRENT_TABLES = _PHASE3_TABLES | {
    "assignments",
    "optimization_runs",
    "output_settings",
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


def _assert_no_metadata_diff(engine: Engine) -> None:
    config = _alembic_config(engine)
    connection = config.attributes["connection"]
    try:
        command.check(config)
    finally:
        connection.close()


def _add_phase2_graph(
    session: Session,
    *,
    title: str = "2026年度 夏期講習",
) -> tuple[CourseProject, Student, Teacher, Subject, TimeSlot]:
    campus = Campus(
        name="架空あおぞら校",
        address_optional=None,
        logo_path_optional=None,
    )
    session.add(campus)
    session.flush()
    project = CourseProject(
        campus_id=campus.id,
        title=title,
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
        note=None,
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
    time_slot = TimeSlot(
        project_id=project.id,
        code="A",
        display_name="Aコマ",
        start_time=time(17, 10),
        end_time=time(18, 30),
        sort_order=3,
        enabled=True,
    )
    session.add(time_slot)
    session.flush()
    return project, student, teacher, subject, time_slot


def _add_phase3_graph(
    session: Session,
    graph: tuple[CourseProject, Student, Teacher, Subject, TimeSlot],
) -> tuple[
    StudentAvailability,
    TeacherAvailability,
    GroupLesson,
    GroupLessonStudent,
    ImportBatch,
    ValidationIssue,
    AuditLog,
]:
    project, student, teacher, subject, time_slot = graph
    student_availability = StudentAvailability(
        project_id=project.id,
        student_id=student.id,
        date=date(2026, 8, 4),
        time_slot_id=time_slot.id,
        availability_level=2,
    )
    teacher_availability = TeacherAvailability(
        project_id=project.id,
        teacher_id=teacher.id,
        date=date(2026, 8, 4),
        time_slot_id=time_slot.id,
        availability_level=1,
    )
    group_lesson = GroupLesson(
        project_id=project.id,
        group_code="集団-001",
        grade="中学2年",
        subject_id=subject.id,
        course_name="数学発展",
        date=date(2026, 8, 4),
        start_time=time(17, 0),
        end_time=time(18, 0),
        teacher_id_optional=teacher.id,
        room_optional="第1教室",
        note="架空データ",
    )
    session.add_all([student_availability, teacher_availability, group_lesson])
    session.flush()
    membership = GroupLessonStudent(
        group_lesson_id=group_lesson.id,
        student_id=student.id,
    )
    import_batch = ImportBatch(
        project_id=project.id,
        import_type="student_availability",
        source_file_name="生徒アンケート_日本語.xlsx",
        row_count=1,
        success_count=1,
        warning_count=0,
        error_count=0,
        mapping_json=json.dumps({"生徒ID": "回答者ID"}, ensure_ascii=False),
    )
    issue = ValidationIssue(
        project_id=project.id,
        severity="warning",
        issue_type="insufficient_availability",
        entity_type="student",
        entity_id_optional=str(student.id),
        message="可能枠数が必要回数と同数です",
        details_json=json.dumps({"可能枠": 2}, ensure_ascii=False),
        resolved=False,
    )
    audit_log = AuditLog(
        project_id=project.id,
        action="import",
        entity_type="import_batch",
        entity_id="pending",
        before_json=None,
        after_json=json.dumps({"ファイル": import_batch.source_file_name}, ensure_ascii=False),
    )
    session.add_all([membership, import_batch, issue, audit_log])
    session.flush()
    return (
        student_availability,
        teacher_availability,
        group_lesson,
        membership,
        import_batch,
        issue,
        audit_log,
    )


def test_upgrade_from_0002_preserves_data_and_matches_metadata(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "日本語プロジェクト" / "夏期講習_入力.jukuschedule"
    database = create_database(database_path)

    try:
        _run_alembic(database.engine, "20260728_0002")
        with database.session_factory() as session:
            graph = _add_phase2_graph(session)
            session.commit()
            project_id = graph[0].id

        upgrade_database(database.engine)

        assert database_path.is_file()
        assert set(inspect(database.engine).get_table_names()) == _CURRENT_TABLES
        assert get_head_revision() == "20260729_0006"
        with database.engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260729_0006"
            )
            assert (
                connection.execute(
                    text("SELECT title FROM course_projects WHERE id = :project_id"),
                    {"project_id": project_id},
                ).scalar_one()
                == "2026年度 夏期講習"
            )

        with database.session_factory() as session:
            persisted_project = session.get(CourseProject, project_id)
            persisted_student = session.scalar(
                select(Student).where(Student.external_id == "生徒-001")
            )
            persisted_teacher = session.scalar(
                select(Teacher).where(Teacher.external_id == "講師-001")
            )
            persisted_subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
            persisted_time_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "A"))
            assert persisted_project is not None
            assert persisted_student is not None
            assert persisted_teacher is not None
            assert persisted_subject is not None
            assert persisted_time_slot is not None
            graph = (
                persisted_project,
                persisted_student,
                persisted_teacher,
                persisted_subject,
                persisted_time_slot,
            )
            _add_phase3_graph(session, graph)
            session.commit()

            assert session.scalar(select(ImportBatch.source_file_name)) == (
                "生徒アンケート_日本語.xlsx"
            )
            assert session.scalar(select(ValidationIssue.message)) == (
                "可能枠数が必要回数と同数です"
            )

        _assert_no_metadata_diff(database.engine)
    finally:
        database.dispose()


def test_phase3_checks_foreign_keys_and_delete_policies(tmp_path: Path) -> None:
    database = create_database(tmp_path / "制約確認_入力.jukuschedule")
    upgrade_database(database.engine)

    try:
        with database.session_factory() as session:
            graph = _add_phase2_graph(session)
            session.commit()
            project, student, teacher, subject, time_slot = graph

            session.add(
                StudentAvailability(
                    project_id=project.id,
                    student_id=student.id,
                    date=date(2026, 8, 5),
                    time_slot_id=time_slot.id,
                    availability_level=3,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            second_campus = Campus(name="架空第二校")
            session.add(second_campus)
            session.flush()
            second_project = CourseProject(
                campus_id=second_campus.id,
                title="別プロジェクト",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 8, 31),
                status="editing",
                file_version=1,
            )
            session.add(second_project)
            session.flush()
            foreign_slot = TimeSlot(
                project_id=second_project.id,
                code="B",
                display_name="Bコマ",
                start_time=time(18, 40),
                end_time=time(20, 0),
                sort_order=4,
                enabled=True,
            )
            session.add(foreign_slot)
            session.commit()

            session.add(
                StudentAvailability(
                    project_id=project.id,
                    student_id=student.id,
                    date=date(2026, 8, 5),
                    time_slot_id=foreign_slot.id,
                    availability_level=1,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            invalid_group = GroupLesson(
                project_id=project.id,
                group_code="不正時刻",
                grade="中学2年",
                subject_id=subject.id,
                course_name=None,
                date=date(2026, 8, 5),
                start_time=time(18, 0),
                end_time=time(18, 0),
                teacher_id_optional=teacher.id,
                room_optional=None,
                note=None,
            )
            session.add(invalid_group)
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            phase3_rows = _add_phase3_graph(session, graph)
            session.commit()
            (
                student_availability,
                teacher_availability,
                group_lesson,
                membership,
                import_batch,
                issue,
                audit_log,
            ) = phase3_rows

            session.add(
                GroupLesson(
                    project_id=project.id,
                    group_code=group_lesson.group_code,
                    grade="中学3年",
                    subject_id=subject.id,
                    course_name="重複コード",
                    date=date(2026, 8, 6),
                    start_time=time(18, 0),
                    end_time=time(19, 0),
                    teacher_id_optional=teacher.id,
                    room_optional=None,
                    note=None,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            teacher_availability_key = (
                teacher_availability.project_id,
                teacher_availability.teacher_id,
                teacher_availability.date,
                teacher_availability.time_slot_id,
            )
            student_availability_key = (
                student_availability.project_id,
                student_availability.student_id,
                student_availability.date,
                student_availability.time_slot_id,
            )
            membership_key = (membership.group_lesson_id, membership.student_id)
            project_id = project.id
            student_id = student.id
            group_lesson_id = group_lesson.id
            import_batch_id = import_batch.id
            issue_id = issue.id
            audit_log_id = audit_log.id

            session.delete(teacher)
            session.commit()
            session.expunge_all()
            assert session.get(TeacherAvailability, teacher_availability_key) is None
            persisted_group = session.get(GroupLesson, group_lesson_id)
            assert persisted_group is not None
            assert persisted_group.teacher_id_optional is None

            persisted_student = session.get(Student, student_id)
            assert persisted_student is not None
            session.delete(persisted_student)
            session.commit()
            session.expunge_all()
            assert session.get(StudentAvailability, student_availability_key) is None
            assert session.get(GroupLessonStudent, membership_key) is None

            persisted_project = session.get(CourseProject, project_id)
            assert persisted_project is not None
            session.delete(persisted_project)
            session.commit()
            session.expunge_all()
            assert session.get(GroupLesson, group_lesson_id) is None
            assert session.get(ImportBatch, import_batch_id) is None
            assert session.get(ValidationIssue, issue_id) is None
            assert session.get(AuditLog, audit_log_id) is None
    finally:
        database.dispose()


def test_downgrade_to_0002_removes_only_phase3_schema(tmp_path: Path) -> None:
    database = create_database(tmp_path / "日本語_downgrade.jukuschedule")

    try:
        upgrade_database(database.engine)
        with database.session_factory() as session:
            graph = _add_phase2_graph(session, title="保持する既存プロジェクト")
            _add_phase3_graph(session, graph)
            session.commit()

        _run_alembic(
            database.engine,
            "20260728_0002",
            downgrade=True,
        )

        inspector = inspect(database.engine)
        assert set(inspector.get_table_names()) == _PHASE2_TABLES
        assert "ix_time_slots_project_id_id_unique" not in {
            index["name"] for index in inspector.get_indexes("time_slots")
        }
        with database.engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "20260728_0002"
            )
            assert (
                connection.execute(text("SELECT title FROM course_projects")).scalar_one()
                == "保持する既存プロジェクト"
            )
    finally:
        database.dispose()
