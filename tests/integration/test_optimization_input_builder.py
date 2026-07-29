"""DBから不変OptimizationInputを構築する境界の結合テスト。"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from summer_scheduler.application.optimization_input_builder import (
    OptimizationInputBuildError,
    build_optimization_input,
)
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.base import Base
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    Campus,
    CourseProject,
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
)
from summer_scheduler.optimization.dto import OptimizationInput, OptimizationSettings


def _settings() -> OptimizationSettings:
    return OptimizationSettings(
        time_limit_seconds=30,
        random_seed=42,
        num_search_workers=1,
        regular_teacher_priority_weights=(1, 2, 3, 4),
        preferred_teacher_rank_weights=(30, 20, 10),
        student_preferred_time_weight=3,
        teacher_preferred_time_weight=2,
        preserve_existing_assignment_weight=5,
        optional_balance_weight=0,
    )


def _add_source_graph(session: Session) -> dict[str, int]:
    campus = Campus(name="架空あさひ校")
    students = [
        Student(
            external_id="S-BUILD-001",
            name="架空 生徒一",
            grade="中2",
            default_max_consecutive_slots=3,
            allow_gap=True,
            active=True,
        ),
        Student(
            external_id="S-BUILD-002",
            name="架空 生徒二",
            grade="中3",
            default_max_consecutive_slots=2,
            allow_gap=False,
            active=False,
        ),
    ]
    teachers = [
        Teacher(
            external_id="T-BUILD-001",
            name="架空 講師一",
            allow_gap=True,
            active=True,
        ),
        Teacher(
            external_id="T-BUILD-002",
            name="架空 講師二",
            allow_gap=False,
            active=False,
        ),
    ]
    subjects = [
        Subject(
            code="BUILD_MATH",
            display_name="架空数学",
            school_level="junior_high",
            sort_order=1,
            active=True,
        ),
        Subject(
            code="BUILD_ENG",
            display_name="架空英語",
            school_level="junior_high",
            sort_order=2,
            active=False,
        ),
    ]
    session.add_all([campus, *students, *teachers, *subjects])
    session.flush()

    project = CourseProject(
        campus_id=campus.id,
        title="入力構築テスト",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        status="editing",
        file_version=1,
    )
    foreign_project = CourseProject(
        campus_id=campus.id,
        title="除外対象プロジェクト",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 2),
        status="editing",
        file_version=1,
    )
    session.add_all([project, foreign_project])
    session.flush()

    later_slot = TimeSlot(
        project_id=project.id,
        code="A",
        display_name="A・表示名",
        start_time=time(17, 10),
        end_time=time(18, 30),
        sort_order=2,
        enabled=True,
    )
    disabled_first_slot = TimeSlot(
        project_id=project.id,
        code="Z",
        display_name="Z・無効",
        start_time=time(15, 40),
        end_time=time(17, 0),
        sort_order=1,
        enabled=False,
    )
    foreign_slot = TimeSlot(
        project_id=foreign_project.id,
        code="X",
        display_name="除外コマ",
        start_time=time(10, 0),
        end_time=time(11, 0),
        sort_order=1,
        enabled=True,
    )
    session.add_all([later_slot, disabled_first_slot, foreign_slot])
    session.flush()

    first_request = LessonRequest(
        project_id=project.id,
        student_id=students[0].id,
        subject_id=subjects[0].id,
        required_sessions=2,
        regular_teacher_id_optional=teachers[0].id,
        regular_teacher_priority=5,
        preferred_teacher_1_id_optional=teachers[1].id,
        preferred_teacher_2_id_optional=teachers[0].id,
        preferred_teacher_3_id_optional=None,
        one_to_one_required=True,
        max_consecutive_slots_override_optional=3,
        allow_gap_override_optional=False,
    )
    second_request = LessonRequest(
        project_id=project.id,
        student_id=students[1].id,
        subject_id=subjects[1].id,
        required_sessions=1,
        regular_teacher_priority=1,
        one_to_one_required=False,
    )
    session.add_all([first_request, second_request])
    session.flush()

    day_one = date(2026, 8, 1)
    day_two = date(2026, 8, 2)
    session.add_all(
        [
            OpenDate(project_id=project.id, date=day_two, is_open=True),
            OpenDate(project_id=project.id, date=day_one, is_open=True),
            OpenDate(
                project_id=project.id,
                date=date(2026, 8, 3),
                is_open=False,
            ),
            OpenDate(
                project_id=foreign_project.id,
                date=date(2026, 9, 1),
                is_open=True,
            ),
            TeacherQualification(
                teacher_id=teachers[0].id,
                subject_id=subjects[1].id,
                can_teach=False,
            ),
            TeacherQualification(
                teacher_id=teachers[1].id,
                subject_id=subjects[1].id,
                can_teach=True,
            ),
            TeacherQualification(
                teacher_id=teachers[0].id,
                subject_id=subjects[0].id,
                can_teach=True,
            ),
            StudentAvailability(
                project_id=project.id,
                student_id=students[0].id,
                date=day_two,
                time_slot_id=later_slot.id,
                availability_level=2,
            ),
            StudentAvailability(
                project_id=project.id,
                student_id=students[0].id,
                date=day_one,
                time_slot_id=disabled_first_slot.id,
                availability_level=0,
            ),
            TeacherAvailability(
                project_id=project.id,
                teacher_id=teachers[0].id,
                date=day_one,
                time_slot_id=disabled_first_slot.id,
                availability_level=1,
            ),
        ]
    )

    later_group = GroupLesson(
        project_id=project.id,
        group_code="G-LATER",
        grade="中2",
        subject_id=subjects[0].id,
        course_name="後の集団",
        date=day_two,
        start_time=time(17, 0),
        end_time=time(18, 0),
        teacher_id_optional=teachers[1].id,
    )
    earlier_group = GroupLesson(
        project_id=project.id,
        group_code="G-EARLIER",
        grade="中2",
        subject_id=subjects[0].id,
        course_name="先の集団",
        date=day_one,
        start_time=time(14, 0),
        end_time=time(15, 0),
        teacher_id_optional=teachers[0].id,
    )
    session.add_all([later_group, earlier_group])
    session.flush()
    session.add_all(
        [
            GroupLessonStudent(
                group_lesson_id=later_group.id,
                student_id=students[1].id,
            ),
            GroupLessonStudent(
                group_lesson_id=earlier_group.id,
                student_id=students[1].id,
            ),
            GroupLessonStudent(
                group_lesson_id=earlier_group.id,
                student_id=students[0].id,
            ),
            Assignment(
                project_id=project.id,
                lesson_request_id=second_request.id,
                session_index=1,
                date=day_two,
                time_slot_id=later_slot.id,
                teacher_id=teachers[1].id,
                is_locked=False,
                is_manual=False,
                created_by="solver",
            ),
            Assignment(
                project_id=project.id,
                lesson_request_id=first_request.id,
                session_index=2,
                date=day_one,
                time_slot_id=disabled_first_slot.id,
                teacher_id=teachers[0].id,
                is_locked=True,
                is_manual=True,
                created_by="manual",
            ),
        ]
    )
    session.flush()
    return {
        "project": project.id,
        "student_1": students[0].id,
        "student_2": students[1].id,
        "teacher_1": teachers[0].id,
        "teacher_2": teachers[1].id,
        "subject_1": subjects[0].id,
        "subject_2": subjects[1].id,
        "slot_first": disabled_first_slot.id,
        "slot_later": later_slot.id,
        "request_1": first_request.id,
        "request_2": second_request.id,
        "group_earlier": earlier_group.id,
        "group_later": later_group.id,
    }


def test_builds_complete_deterministic_session_independent_input(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "日本語パス" / "入力境界.jukuschedule")
    upgrade_database(database.engine)
    settings = _settings()
    try:
        with database.session_factory.begin() as session:
            ids = _add_source_graph(session)

        with database.session_factory() as session:
            first = build_optimization_input(
                session=session,
                project_id=ids["project"],
                settings=settings,
            )
            second = build_optimization_input(
                session=session,
                project_id=ids["project"],
                settings=settings,
            )
            session.expunge_all()
    finally:
        database.dispose()

    assert first == second
    assert first.settings is settings
    assert first.open_dates == (date(2026, 8, 1), date(2026, 8, 2))
    assert [(row.id, row.enabled) for row in first.time_slots] == [
        (ids["slot_first"], False),
        (ids["slot_later"], True),
    ]
    assert [row.display_name for row in first.time_slots] == [
        "Z・無効",
        "A・表示名",
    ]
    assert [(row.id, row.active, row.allow_gap) for row in first.students] == [
        (ids["student_1"], True, True),
        (ids["student_2"], False, False),
    ]
    assert [(row.id, row.active, row.qualified_subject_ids) for row in first.teachers] == [
        (ids["teacher_1"], True, frozenset({ids["subject_1"]})),
        (ids["teacher_2"], False, frozenset({ids["subject_2"]})),
    ]
    assert [(row.id, row.active) for row in first.subjects] == [
        (ids["subject_1"], True),
        (ids["subject_2"], False),
    ]

    requests = first.lesson_requests
    assert [row.id for row in requests] == [ids["request_1"], ids["request_2"]]
    assert requests[0].regular_teacher_id == ids["teacher_1"]
    assert requests[0].preferred_teacher_ids == (
        ids["teacher_2"],
        ids["teacher_1"],
        None,
    )
    assert requests[0].one_to_one_required is True
    assert requests[0].max_consecutive_slots_override == 3
    assert requests[0].allow_gap_override is False

    assert [
        (row.owner_type, row.owner_id, row.day, row.time_slot_id, row.level)
        for row in first.availabilities
    ] == [
        (
            "student",
            ids["student_1"],
            date(2026, 8, 1),
            ids["slot_first"],
            0,
        ),
        (
            "student",
            ids["student_1"],
            date(2026, 8, 2),
            ids["slot_later"],
            2,
        ),
        (
            "teacher",
            ids["teacher_1"],
            date(2026, 8, 1),
            ids["slot_first"],
            1,
        ),
    ]
    assert [row.id for row in first.group_blocks] == [
        ids["group_earlier"],
        ids["group_later"],
    ]
    assert first.group_blocks[0].student_ids == frozenset({ids["student_1"], ids["student_2"]})
    assert first.group_blocks[0].teacher_id == ids["teacher_1"]
    assert [(row.lesson_request_id, row.session_index) for row in first.existing_assignments] == [
        (ids["request_1"], 2),
        (ids["request_2"], 1),
    ]
    assert first.existing_assignments[0].is_locked is True
    assert first.existing_assignments[0].is_manual is True
    _assert_no_orm_rows(first)


def test_missing_project_is_rejected_without_fallback(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "missing_project.jukuschedule")
    upgrade_database(database.engine)
    try:
        with database.session_factory() as session:
            with pytest.raises(
                OptimizationInputBuildError,
                match="project_id=999",
            ):
                build_optimization_input(
                    session=session,
                    project_id=999,
                    settings=_settings(),
                )
    finally:
        database.dispose()


def _assert_no_orm_rows(value: OptimizationInput) -> None:
    collections = (
        value.time_slots,
        value.students,
        value.teachers,
        value.subjects,
        value.lesson_requests,
        value.availabilities,
        value.group_blocks,
        value.existing_assignments,
    )
    assert all(not isinstance(item, Base) for collection in collections for item in collection)
