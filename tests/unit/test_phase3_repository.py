"""Phase 3 RepositoryのCRUD・upsert・transaction境界テスト。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db import create_database
from summer_scheduler.infrastructure.db.base import Base
from summer_scheduler.infrastructure.db.database import Database
from summer_scheduler.infrastructure.db.models import (
    AuditLog,
    Campus,
    CourseProject,
    GroupLesson,
    ImportBatch,
    Student,
    Subject,
    Teacher,
    TimeSlot,
    ValidationIssue,
)
from summer_scheduler.infrastructure.repositories import MasterRepository


@pytest.fixture
def repository(
    tmp_path: Path,
) -> Iterator[tuple[MasterRepository, Session, Database]]:
    database = create_database(tmp_path / "日本語_repository.jukuschedule")
    Base.metadata.create_all(database.engine)
    session = database.session_factory()
    try:
        yield MasterRepository(session), session, database
    finally:
        session.close()
        database.dispose()


def _create_base_graph(
    repository: MasterRepository,
) -> tuple[CourseProject, Student, Teacher, Subject, TimeSlot]:
    campus = repository.create_campus(Campus(name="架空みどり校"))
    project = repository.create_project(
        CourseProject(
            campus_id=campus.id,
            title="日本語入力テスト",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 8, 31),
            status="editing",
            file_version=1,
        )
    )
    student = repository.create_student(
        Student(
            external_id="S-001",
            name="架空 生徒",
            grade="高校1年",
            default_max_consecutive_slots=2,
            allow_gap=False,
            note=None,
            active=True,
        )
    )
    teacher = repository.create_teacher(
        Teacher(
            external_id="T-001",
            name="架空 講師",
            allow_gap=False,
            note=None,
            active=True,
        )
    )
    subject = repository.create_subject(
        Subject(
            code="HS_ENGLISH",
            display_name="高校・英語",
            school_level="高校",
            sort_order=1,
            active=True,
        )
    )
    time_slot = repository.create_time_slot(
        TimeSlot(
            project_id=project.id,
            code="A",
            display_name="Aコマ",
            start_time=time(17, 10),
            end_time=time(18, 30),
            sort_order=3,
            enabled=True,
        )
    )
    return project, student, teacher, subject, time_slot


def test_availability_upsert_filter_delete_does_not_commit(
    repository: tuple[MasterRepository, Session, Database],
) -> None:
    repo, session, _database = repository
    project, student, teacher, _subject, time_slot = _create_base_graph(repo)
    target_date = date(2026, 8, 4)

    student_row = repo.upsert_student_availability(
        project_id=project.id,
        student_id=student.id,
        date_value=target_date,
        time_slot_id=time_slot.id,
        availability_level=0,
    )
    updated_student_row = repo.upsert_student_availability(
        project_id=project.id,
        student_id=student.id,
        date_value=target_date,
        time_slot_id=time_slot.id,
        availability_level=2,
    )
    teacher_row = repo.upsert_teacher_availability(
        project_id=project.id,
        teacher_id=teacher.id,
        date_value=target_date,
        time_slot_id=time_slot.id,
        availability_level=1,
    )

    assert updated_student_row is student_row
    assert updated_student_row.availability_level == 2
    assert (
        repo.get_student_availability(
            project_id=project.id,
            student_id=student.id,
            date_value=target_date,
            time_slot_id=time_slot.id,
        )
        is student_row
    )
    assert repo.list_student_availabilities(
        project_id=project.id,
        student_id=student.id,
        date_from=target_date,
        date_to=target_date,
    ) == [student_row]
    assert repo.list_teacher_availabilities(
        project_id=project.id,
        teacher_id=teacher.id,
        date_value=target_date,
    ) == [teacher_row]
    assert repo.delete_teacher_availability(
        project_id=project.id,
        teacher_id=teacher.id,
        date_value=target_date,
        time_slot_id=time_slot.id,
    )
    assert (
        repo.delete_student_availabilities(
            project_id=project.id,
            student_id=student.id,
        )
        == 1
    )
    assert session.in_transaction()

    session.rollback()
    assert repo.list_students() == []
    assert repo.list_student_availabilities(project_id=project.id) == []
    assert repo.list_teacher_availabilities(project_id=project.id) == []


def test_group_import_validation_and_audit_repository_api(
    repository: tuple[MasterRepository, Session, Database],
) -> None:
    repo, session, _database = repository
    project, first_student, teacher, subject, _time_slot = _create_base_graph(repo)
    second_student = repo.create_student(
        Student(
            external_id="S-002",
            name="架空 第二生徒",
            grade="高校1年",
            default_max_consecutive_slots=2,
            allow_gap=False,
            note=None,
            active=True,
        )
    )
    session.commit()

    group_lesson = repo.create_group_lesson(
        GroupLesson(
            project_id=project.id,
            group_code="集団-001",
            grade="高校1年",
            subject_id=subject.id,
            course_name="英語発展",
            date=date(2026, 8, 5),
            start_time=time(18, 0),
            end_time=time(19, 20),
            teacher_id_optional=teacher.id,
            room_optional="第2教室",
            note=None,
        )
    )
    memberships = repo.replace_group_lesson_students(
        group_lesson_id=group_lesson.id,
        student_ids=[second_student.id, first_student.id, first_student.id],
    )
    assert [row.student_id for row in memberships] == [
        first_student.id,
        second_student.id,
    ]
    assert (
        repo.get_group_lesson_by_code(
            project_id=project.id,
            group_code="集団-001",
        )
        is group_lesson
    )
    assert repo.list_group_lessons(
        project_id=project.id,
        teacher_id=teacher.id,
    ) == [group_lesson]

    older_batch = repo.create_import_batch(
        ImportBatch(
            project_id=project.id,
            import_type="student_availability",
            source_file_name="回答_旧.csv",
            imported_at=datetime(2026, 7, 29, 1, 0, tzinfo=UTC),
            row_count=2,
            success_count=2,
            warning_count=0,
            error_count=0,
            mapping_json='{"生徒ID":"ID"}',
        )
    )
    latest_batch = repo.create_import_batch(
        ImportBatch(
            project_id=project.id,
            import_type="student_availability",
            source_file_name="回答_新.xlsx",
            imported_at=datetime(2026, 7, 29, 2, 0, tzinfo=UTC),
            row_count=2,
            success_count=1,
            warning_count=1,
            error_count=0,
            mapping_json='{"生徒ID":"回答者ID"}',
        )
    )
    assert repo.list_import_batches(
        project_id=project.id,
        import_type="student_availability",
    ) == [latest_batch, older_batch]
    assert (
        repo.get_latest_import_batch(
            project_id=project.id,
            import_type="student_availability",
        )
        is latest_batch
    )

    old_issue = repo.create_validation_issue(
        ValidationIssue(
            project_id=project.id,
            severity="warning",
            issue_type="old_warning",
            entity_type="student",
            entity_id_optional=str(first_student.id),
            message="以前の警告",
            details_json="{}",
            resolved=False,
        )
    )
    new_issue = ValidationIssue(
        project_id=project.id,
        severity="error",
        issue_type="availability_shortage",
        entity_type="student",
        entity_id_optional=str(first_student.id),
        message="可能枠が不足しています",
        details_json='{"不足":1}',
        resolved=False,
    )
    assert repo.replace_validation_issues(
        project_id=project.id,
        issues=[new_issue],
    ) == [new_issue]
    assert old_issue.resolved
    assert repo.list_validation_issues(
        project_id=project.id,
        severity="error",
        resolved=False,
    ) == [new_issue]

    older_log = repo.create_audit_log(
        AuditLog(
            project_id=project.id,
            timestamp=datetime(2026, 7, 29, 1, 0, tzinfo=UTC),
            action="preview",
            entity_type="import_batch",
            entity_id=str(older_batch.id),
            before_json=None,
            after_json="{}",
        )
    )
    latest_log = repo.create_audit_log(
        AuditLog(
            project_id=project.id,
            timestamp=datetime(2026, 7, 29, 2, 0, tzinfo=UTC),
            action="apply",
            entity_type="import_batch",
            entity_id=str(latest_batch.id),
            before_json=None,
            after_json='{"成功":1}',
        )
    )
    assert repo.list_audit_logs(
        project_id=project.id,
        entity_type="import_batch",
    ) == [latest_log, older_log]

    assert session.in_transaction()
    session.rollback()
    assert repo.list_group_lessons(project_id=project.id) == []
    assert repo.list_import_batches(project_id=project.id) == []
    assert repo.list_validation_issues(project_id=project.id) == []
    assert repo.list_audit_logs(project_id=project.id) == []


def test_validation_replacement_rejects_another_project_before_mutation(
    repository: tuple[MasterRepository, Session, Database],
) -> None:
    repo, _session, _database = repository
    project, student, _teacher, _subject, _time_slot = _create_base_graph(repo)
    current = repo.create_validation_issue(
        ValidationIssue(
            project_id=project.id,
            severity="warning",
            issue_type="same_name",
            entity_type="student",
            entity_id_optional=str(student.id),
            message="同姓同名を確認してください",
            details_json="{}",
            resolved=False,
        )
    )

    with pytest.raises(ValueError, match="別プロジェクト"):
        repo.replace_validation_issues(
            project_id=project.id,
            issues=[
                ValidationIssue(
                    project_id=project.id + 1,
                    severity="error",
                    issue_type="invalid",
                    entity_type="project",
                    entity_id_optional=None,
                    message="別プロジェクト",
                    details_json="{}",
                    resolved=False,
                )
            ],
        )

    assert not current.resolved
