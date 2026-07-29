"""Phase 3の保存済みプロジェクト入力検証。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy import select

from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.application.project_validation_service import (
    ProjectValidationService,
)
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    GroupLesson,
    GroupLessonStudent,
    LessonRequest,
    OpenDate,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TeacherQualification,
    TimeSlot,
    ValidationIssue,
)


@pytest.fixture
def project_service(tmp_path: Path) -> Iterator[ProjectService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    service = ProjectService(registry, tmp_path / "バックアップ")
    service.create_project(
        tmp_path / "入力検証.jukuschedule",
        title="架空校 夏期講習",
        campus_name="架空みらい校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
    )
    yield service
    service.close_project()
    registry.dispose()


def test_revalidation_resolves_previous_issues(project_service: ProjectService) -> None:
    database = project_service.require_database()
    with database.session_factory.begin() as session:
        session.add_all(
            [
                _student("S-001", "架空 花子"),
                _student("S-002", "架空 花子"),
            ]
        )

    service = ProjectValidationService(project_service)
    first = service.run_validation()
    assert [issue.issue_type for issue in first] == ["duplicate_name"]

    with database.session_factory.begin() as session:
        second_student = session.scalar(select(Student).where(Student.external_id == "S-002"))
        assert second_student is not None
        second_student.name = "架空 次郎"

    assert service.run_validation() == ()
    history = service.list_issues(include_resolved=True)
    assert len(history) == 1
    assert history[0].issue_type == "duplicate_name"
    assert history[0].resolved is True
    assert service.list_issues() == ()


def test_revalidation_keeps_one_resolved_and_one_unresolved_history_row(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        session.add_all(
            [
                _student("S-101", "匿名 重複"),
                _student("S-102", "匿名 重複"),
            ]
        )

    service = ProjectValidationService(project_service)
    assert [issue.issue_type for issue in service.run_validation()] == ["duplicate_name"]
    assert [issue.issue_type for issue in service.run_validation()] == ["duplicate_name"]

    with database.session_factory() as session:
        rows = list(
            session.scalars(
                select(ValidationIssue)
                .where(
                    ValidationIssue.project_id == project_id,
                    ValidationIssue.issue_type == "duplicate_name",
                )
                .order_by(ValidationIssue.id)
            )
        )
    assert len(rows) == 2
    assert [row.resolved for row in rows] == [True, False]
    assert len(service.list_issues()) == 1
    assert service.list_issues()[0].resolved is False


def test_validation_detects_capacity_qualification_and_group_conflicts(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        y_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "Y"))
        assert subject is not None
        assert y_slot is not None
        student = _student("S-010", "架空 一郎")
        teacher = Teacher(
            external_id="T-010",
            name="架空 講師",
            allow_gap=False,
            note="テスト用",
            active=True,
        )
        session.add_all([student, teacher])
        session.flush()
        session.add(
            TeacherQualification(
                teacher_id=teacher.id,
                subject_id=subject.id,
                can_teach=False,
            )
        )
        request = LessonRequest(
            project_id=project_id,
            student_id=student.id,
            subject_id=subject.id,
            required_sessions=2,
            regular_teacher_id_optional=teacher.id,
            regular_teacher_priority=5,
            one_to_one_required=True,
        )
        session.add_all(
            [
                request,
                StudentAvailability(
                    project_id=project_id,
                    student_id=student.id,
                    date=date(2026, 8, 1),
                    time_slot_id=y_slot.id,
                    availability_level=2,
                ),
                TeacherAvailability(
                    project_id=project_id,
                    teacher_id=teacher.id,
                    date=date(2026, 8, 1),
                    time_slot_id=y_slot.id,
                    availability_level=1,
                ),
            ]
        )
        session.flush()
        first_group = GroupLesson(
            project_id=project_id,
            group_code="G-001",
            grade="中2",
            subject_id=subject.id,
            course_name="架空数学講座",
            date=date(2026, 8, 1),
            start_time=time(14, 0),
            end_time=time(15, 0),
            teacher_id_optional=teacher.id,
        )
        second_group = GroupLesson(
            project_id=project_id,
            group_code="G-002",
            grade="中2",
            subject_id=subject.id,
            course_name="架空演習講座",
            date=date(2026, 8, 1),
            start_time=time(14, 30),
            end_time=time(15, 30),
            teacher_id_optional=teacher.id,
        )
        session.add_all([first_group, second_group])
        session.flush()
        session.add_all(
            [
                GroupLessonStudent(
                    group_lesson_id=first_group.id,
                    student_id=student.id,
                ),
                GroupLessonStudent(
                    group_lesson_id=second_group.id,
                    student_id=student.id,
                ),
            ]
        )

    issues = ProjectValidationService(project_service).run_validation()
    issue_types = {issue.issue_type for issue in issues}
    assert "regular_teacher_unqualified" in issue_types
    assert "group_teacher_unqualified" in issue_types
    assert "group_teacher_overlap" in issue_types
    assert "group_student_overlap" in issue_types
    assert "student_availability_shortage" in issue_types
    assert "priority5_common_availability_shortage" in issue_types


def test_validation_detects_overlapping_enabled_time_slots(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        session.add(
            TimeSlot(
                project_id=project_id,
                code="Y2",
                display_name="Y重複",
                start_time=time(14, 30),
                end_time=time(15, 0),
                sort_order=6,
                enabled=True,
            )
        )

    issues = ProjectValidationService(project_service).run_validation()
    overlaps = [issue for issue in issues if issue.issue_type == "time_slot_overlap"]
    assert len(overlaps) == 1
    assert overlaps[0].severity == "error"
    assert "Y" in overlaps[0].message and "Y2" in overlaps[0].message


def test_validation_detects_availability_on_closed_date(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        open_date = session.scalar(
            select(OpenDate).where(
                OpenDate.project_id == project_id,
                OpenDate.date == date(2026, 8, 1),
            )
        )
        y_slot = session.scalar(
            select(TimeSlot).where(
                TimeSlot.project_id == project_id,
                TimeSlot.code == "Y",
            )
        )
        assert open_date is not None
        assert y_slot is not None
        open_date.is_open = False
        student = _student("S-020", "架空 休校日")
        session.add(student)
        session.flush()
        session.add(
            StudentAvailability(
                project_id=project_id,
                student_id=student.id,
                date=open_date.date,
                time_slot_id=y_slot.id,
                availability_level=1,
            )
        )

    issues = ProjectValidationService(project_service).run_validation()
    closed_date_issues = [
        issue for issue in issues if issue.issue_type == "availability_on_closed_date"
    ]
    assert len(closed_date_issues) == 1
    assert closed_date_issues[0].severity == "error"
    assert closed_date_issues[0].entity_type == "student"


def test_validation_detects_inactive_master_references_in_availability(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        y_slot = session.scalar(
            select(TimeSlot).where(
                TimeSlot.project_id == project_id,
                TimeSlot.code == "Y",
            )
        )
        assert y_slot is not None
        y_slot.enabled = False
        student = _student("S-030", "架空 無効")
        student.active = False
        session.add(student)
        session.flush()
        session.add(
            StudentAvailability(
                project_id=project_id,
                student_id=student.id,
                date=date(2026, 8, 1),
                time_slot_id=y_slot.id,
                availability_level=1,
            )
        )

    issues = ProjectValidationService(project_service).run_validation()
    inactive_references = [
        issue for issue in issues if issue.issue_type == "inactive_master_reference"
    ]
    assert {(issue.severity, issue.entity_type) for issue in inactive_references} == {
        ("warning", "student"),
        ("warning", "time_slot"),
    }


def test_validation_detects_priority5_without_regular_teacher(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        assert subject is not None
        student = _student("S-040", "架空 優先度五")
        session.add(student)
        session.flush()
        session.add(
            LessonRequest(
                project_id=project_id,
                student_id=student.id,
                subject_id=subject.id,
                required_sessions=1,
                regular_teacher_id_optional=None,
                regular_teacher_priority=5,
                one_to_one_required=False,
            )
        )

    issues = ProjectValidationService(project_service).run_validation()
    missing_teacher = [issue for issue in issues if issue.issue_type == "priority5_teacher_missing"]
    assert len(missing_teacher) == 1
    assert missing_teacher[0].severity == "error"
    assert missing_teacher[0].entity_type == "lesson_request"


def test_validation_detects_assignment_one_to_one_and_fixed_conflicts(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        math = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        english = session.scalar(select(Subject).where(Subject.code == "JH_ENG"))
        y_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "Y"))
        assert math is not None
        assert english is not None
        assert y_slot is not None
        first = _student("S-FIX-001", "架空 固定一")
        second = _student("S-FIX-002", "架空 固定二")
        third = _student("S-FIX-003", "架空 固定三")
        teacher = Teacher(
            external_id="T-FIX-001",
            name="架空 固定講師",
            allow_gap=False,
            active=True,
        )
        overlapping_slot = TimeSlot(
            project_id=project_id,
            code="Y-FIX",
            display_name="固定重複コマ",
            start_time=time(14, 30),
            end_time=time(15, 0),
            sort_order=6,
            enabled=True,
        )
        session.add_all([first, second, third, teacher, overlapping_slot])
        session.flush()
        requests = [
            LessonRequest(
                project_id=project_id,
                student_id=first.id,
                subject_id=math.id,
                required_sessions=1,
                regular_teacher_priority=1,
                one_to_one_required=True,
            ),
            LessonRequest(
                project_id=project_id,
                student_id=second.id,
                subject_id=math.id,
                required_sessions=1,
                regular_teacher_priority=1,
                one_to_one_required=False,
            ),
            LessonRequest(
                project_id=project_id,
                student_id=third.id,
                subject_id=math.id,
                required_sessions=1,
                regular_teacher_priority=1,
                one_to_one_required=False,
            ),
            LessonRequest(
                project_id=project_id,
                student_id=first.id,
                subject_id=english.id,
                required_sessions=1,
                regular_teacher_priority=1,
                one_to_one_required=False,
            ),
        ]
        session.add_all(requests)
        session.flush()
        session.add_all(
            [
                Assignment(
                    project_id=project_id,
                    lesson_request_id=requests[0].id,
                    session_index=1,
                    date=date(2026, 8, 1),
                    time_slot_id=y_slot.id,
                    teacher_id=teacher.id,
                    is_locked=True,
                    is_manual=True,
                    created_by="manual",
                ),
                Assignment(
                    project_id=project_id,
                    lesson_request_id=requests[1].id,
                    session_index=1,
                    date=date(2026, 8, 1),
                    time_slot_id=y_slot.id,
                    teacher_id=teacher.id,
                    is_locked=True,
                    is_manual=True,
                    created_by="manual",
                ),
                Assignment(
                    project_id=project_id,
                    lesson_request_id=requests[2].id,
                    session_index=1,
                    date=date(2026, 8, 1),
                    time_slot_id=y_slot.id,
                    teacher_id=teacher.id,
                    is_locked=True,
                    is_manual=True,
                    created_by="manual",
                ),
                Assignment(
                    project_id=project_id,
                    lesson_request_id=requests[3].id,
                    session_index=1,
                    date=date(2026, 8, 1),
                    time_slot_id=overlapping_slot.id,
                    teacher_id=teacher.id,
                    is_locked=True,
                    is_manual=True,
                    created_by="manual",
                ),
            ]
        )

    issue_types = {
        issue.issue_type for issue in ProjectValidationService(project_service).run_validation()
    }
    assert "one_to_one_assignment_conflict" in issue_types
    assert "fixed_teacher_capacity_conflict" in issue_types
    assert "fixed_student_time_conflict" in issue_types
    assert "fixed_teacher_time_conflict" in issue_types


def test_validation_detects_group_conflicts_with_fixed_assignment(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        y_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "Y"))
        assert subject is not None
        assert y_slot is not None
        student = _student("S-GROUP-FIX", "架空 集団重複")
        teacher = Teacher(
            external_id="T-GROUP-FIX",
            name="架空 集団講師",
            allow_gap=False,
            active=True,
        )
        session.add_all([student, teacher])
        session.flush()
        session.add(
            TeacherQualification(
                teacher_id=teacher.id,
                subject_id=subject.id,
                can_teach=True,
            )
        )
        request = LessonRequest(
            project_id=project_id,
            student_id=student.id,
            subject_id=subject.id,
            required_sessions=1,
            regular_teacher_id_optional=teacher.id,
            regular_teacher_priority=1,
            one_to_one_required=False,
        )
        group = GroupLesson(
            project_id=project_id,
            group_code="G-FIXED",
            grade="中2",
            subject_id=subject.id,
            course_name="架空集団",
            date=date(2026, 8, 1),
            start_time=time(14, 0),
            end_time=time(15, 0),
            teacher_id_optional=teacher.id,
        )
        session.add_all([request, group])
        session.flush()
        session.add_all(
            [
                GroupLessonStudent(
                    group_lesson_id=group.id,
                    student_id=student.id,
                ),
                Assignment(
                    project_id=project_id,
                    lesson_request_id=request.id,
                    session_index=1,
                    date=date(2026, 8, 1),
                    time_slot_id=y_slot.id,
                    teacher_id=teacher.id,
                    is_locked=True,
                    is_manual=True,
                    created_by="manual",
                ),
            ]
        )

    issue_types = {
        issue.issue_type for issue in ProjectValidationService(project_service).run_validation()
    }
    assert "fixed_assignment_group_student_conflict" in issue_types
    assert "fixed_assignment_group_teacher_conflict" in issue_types


def test_validation_accepts_two_fixed_students_in_one_teacher_slot(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        y_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "Y"))
        assert subject is not None
        assert y_slot is not None
        students = [
            _student("S-PAIR-001", "架空 ペア一"),
            _student("S-PAIR-002", "架空 ペア二"),
        ]
        teacher = Teacher(
            external_id="T-PAIR-001",
            name="架空 ペア講師",
            allow_gap=False,
            active=True,
        )
        session.add_all([*students, teacher])
        session.flush()
        requests = [
            LessonRequest(
                project_id=project_id,
                student_id=student.id,
                subject_id=subject.id,
                required_sessions=1,
                regular_teacher_priority=1,
                one_to_one_required=False,
            )
            for student in students
        ]
        session.add_all(requests)
        session.flush()
        session.add_all(
            [
                Assignment(
                    project_id=project_id,
                    lesson_request_id=request.id,
                    session_index=1,
                    date=date(2026, 8, 1),
                    time_slot_id=y_slot.id,
                    teacher_id=teacher.id,
                    is_locked=True,
                    is_manual=True,
                    created_by="manual",
                )
                for request in requests
            ]
        )

    forbidden_types = {
        "one_to_one_assignment_conflict",
        "fixed_teacher_capacity_conflict",
        "fixed_teacher_time_conflict",
    }
    issues = ProjectValidationService(project_service).run_validation()
    assert not (forbidden_types & {issue.issue_type for issue in issues})


def _student(external_id: str, name: str) -> Student:
    return Student(
        external_id=external_id,
        name=name,
        grade="中2",
        default_max_consecutive_slots=2,
        allow_gap=False,
        note="テスト用の架空データ",
        active=True,
    )
