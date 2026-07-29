"""MasterRepositoryのCRUD・transaction境界テスト。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db import create_database
from summer_scheduler.infrastructure.db.base import Base
from summer_scheduler.infrastructure.db.database import Database
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
from summer_scheduler.infrastructure.repositories import MasterRepository


@pytest.fixture
def repository(
    tmp_path: Path,
) -> Iterator[tuple[MasterRepository, Session, Database]]:
    database = create_database(tmp_path / "repository.jukuschedule")
    Base.metadata.create_all(database.engine)
    session = database.session_factory()
    try:
        yield MasterRepository(session), session, database
    finally:
        session.close()
        database.dispose()


def _create_base_graph(
    repository: MasterRepository,
) -> tuple[Campus, CourseProject, Student, Teacher, Subject]:
    campus = repository.create_campus(
        Campus(
            name="架空中央校",
            address_optional=None,
            logo_path_optional=None,
        )
    )
    project = repository.create_project(
        CourseProject(
            campus_id=campus.id,
            title="日本語講習名",
            start_date=date(2026, 7, 21),
            end_date=date(2026, 8, 30),
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
            code="HS_MATH_GENERAL",
            display_name="高校・数学一般",
            school_level="高校",
            sort_order=4,
            active=True,
        )
    )
    return campus, project, student, teacher, subject


def test_typed_crud_for_all_phase2_models_does_not_commit(
    repository: tuple[MasterRepository, Session, Database],
) -> None:
    repo, session, _database = repository
    campus, project, student, teacher, subject = _create_base_graph(repo)
    time_slot = repo.create_time_slot(
        TimeSlot(
            project_id=project.id,
            code="Y",
            display_name="Yコマ",
            start_time=time(14, 10),
            end_time=time(15, 30),
            sort_order=1,
            enabled=True,
        )
    )
    open_date = repo.create_open_date(
        OpenDate(
            project_id=project.id,
            date=date(2026, 7, 21),
            is_open=True,
            note=None,
        )
    )
    qualification = repo.create_teacher_qualification(
        TeacherQualification(
            teacher_id=teacher.id,
            subject_id=subject.id,
            can_teach=True,
            note=None,
        )
    )
    lesson_request = repo.create_lesson_request(
        LessonRequest(
            project_id=project.id,
            student_id=student.id,
            subject_id=subject.id,
            required_sessions=3,
            regular_teacher_id_optional=teacher.id,
            regular_teacher_priority=4,
            preferred_teacher_1_id_optional=teacher.id,
            preferred_teacher_2_id_optional=None,
            preferred_teacher_3_id_optional=None,
            one_to_one_required=False,
            max_consecutive_slots_override_optional=None,
            allow_gap_override_optional=None,
            note=None,
        )
    )

    assert repo.get_campus(campus.id) is campus
    assert repo.get_project(project.id) is project
    assert repo.get_only_course_project() is project
    assert repo.get_time_slot(time_slot.id) is time_slot
    assert repo.get_open_date(open_date.id) is open_date
    assert repo.get_student_by_external_id("S-001") is student
    assert repo.get_teacher_by_external_id("T-001") is teacher
    assert repo.get_subject_by_code("HS_MATH_GENERAL") is subject
    assert repo.get_teacher_qualification(teacher.id, subject.id) is qualification
    assert (
        repo.get_lesson_request_by_student_subject(
            project_id=project.id,
            student_id=student.id,
            subject_id=subject.id,
        )
        is lesson_request
    )
    assert repo.list_campuses() == [campus]
    assert repo.list_projects() == [project]
    assert repo.list_time_slots(project_id=project.id) == [time_slot]
    assert repo.list_open_dates(project_id=project.id) == [open_date]
    assert repo.list_students() == [student]
    assert repo.list_teachers() == [teacher]
    assert repo.list_subjects() == [subject]
    assert repo.list_teacher_qualifications() == [qualification]
    assert repo.list_lesson_requests(project_id=project.id) == [lesson_request]

    repo.update_campus(campus, name="架空東校")
    repo.update_project(project, title="更新後の講習")
    repo.update_time_slot(time_slot, display_name="第1コマ")
    repo.update_open_date(open_date, note="開講")
    repo.update_student(student, note="更新")
    repo.update_teacher(teacher, note="更新")
    repo.update_subject(subject, display_name="高校・数学")
    repo.update_teacher_qualification(qualification, note="確認済み")
    repo.update_lesson_request(lesson_request, required_sessions=4)

    assert session.in_transaction()
    session.rollback()
    assert repo.list_campuses() == []


def test_deactivate_filter_and_physical_delete(
    repository: tuple[MasterRepository, Session, Database],
) -> None:
    repo, session, _database = repository
    campus, project, student, teacher, subject = _create_base_graph(repo)
    session.commit()

    assert repo.deactivate_student(student.id) is student
    assert repo.deactivate_teacher(teacher.id) is teacher
    assert repo.deactivate_subject(subject.id) is subject
    assert repo.list_students(active_only=True) == []
    assert repo.list_teachers(active_only=True) == []
    assert repo.list_subjects(active_only=True) == []
    assert repo.activate_student(student.id) is student
    assert repo.activate_teacher(teacher.id) is teacher
    assert repo.activate_subject(subject.id) is subject

    assert repo.delete_student(student.id)
    assert repo.delete_teacher(teacher.id)
    assert repo.delete_subject(subject.id)
    assert repo.delete_project(project.id)
    assert repo.delete_campus(campus.id)
    assert not repo.delete_student(student.id)
    session.commit()


def test_qualification_decision_replace_and_copy(
    repository: tuple[MasterRepository, Session, Database],
) -> None:
    repo, _session, _database = repository
    _, _, _, teacher, subject = _create_base_graph(repo)
    second_subject = repo.create_subject(
        Subject(
            code="HS_MATH_III",
            display_name="高校・数学III",
            school_level="高校",
            sort_order=5,
            active=True,
        )
    )
    second_teacher = repo.create_teacher(
        Teacher(
            external_id="T-002",
            name="架空 第二講師",
            allow_gap=False,
            note=None,
            active=True,
        )
    )

    repo.set_teacher_qualification(
        teacher_id=teacher.id,
        subject_id=subject.id,
        can_teach=True,
        note="数学一般のみ",
    )
    assert repo.can_teacher_teach(teacher.id, subject.id)
    assert not repo.can_teacher_teach(teacher.id, second_subject.id)

    replaced = repo.replace_teacher_qualifications(
        teacher_id=teacher.id,
        qualifications={
            subject.id: False,
            second_subject.id: True,
        },
    )
    assert [row.can_teach for row in replaced] == [False, True]
    assert not repo.can_teacher_teach(teacher.id, subject.id)
    assert repo.can_teacher_teach(teacher.id, second_subject.id)

    copied = repo.copy_teacher_qualifications(
        source_teacher_id=teacher.id,
        target_teacher_id=second_teacher.id,
    )
    assert len(copied) == 2
    assert not repo.can_teacher_teach(second_teacher.id, subject.id)
    assert repo.can_teacher_teach(second_teacher.id, second_subject.id)
    assert repo.delete_teacher_qualification(
        second_teacher.id,
        second_subject.id,
    )


def test_repository_enforces_one_project_per_file(
    repository: tuple[MasterRepository, Session, Database],
) -> None:
    repo, _session, _database = repository
    campus, _, _, _, _ = _create_base_graph(repo)

    with pytest.raises(
        ValueError,
        match="1つのプロジェクトファイルには1件だけ",
    ):
        repo.create_project(
            CourseProject(
                campus_id=campus.id,
                title="2件目",
                start_date=date(2026, 12, 1),
                end_date=date(2026, 12, 31),
                status="editing",
                file_version=1,
            )
        )
