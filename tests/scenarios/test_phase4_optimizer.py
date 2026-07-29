"""Phase 4の中核ハード制約と辞書式目的を実CP-SATで確認する。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, time

from summer_scheduler.optimization.dto import (
    AvailabilityData,
    DiagnosticCode,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    OptimizationInput,
    OptimizationSettings,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
)
from summer_scheduler.optimization.solver import OptimizationProgress, solve_optimization

DAY = date(2026, 8, 3)
SUBJECT_1 = SubjectData(id=1, code="MATH", display_name="架空数学")
SUBJECT_2 = SubjectData(id=2, code="ENGLISH", display_name="架空英語")


def test_all_required_sessions_are_placed_when_feasible() -> None:
    source = _input(
        students=(_student(1),),
        teachers=(_teacher(1),),
        requests=(_request(1, 1, sessions=2),),
        slots=_slots(2),
    )

    result = solve_optimization(source)

    assert result.solver_status == "OPTIMAL"
    assert len(result.assignments) == 2
    assert not result.unassigned_lessons
    assert {item.session_index for item in result.assignments} == {1, 2}


def test_priority_five_never_uses_another_teacher() -> None:
    students = (_student(1),)
    teachers = (_teacher(1), _teacher(2))
    slots = _slots(1)
    request = replace(
        _request(1, 1),
        regular_teacher_id=1,
        regular_teacher_priority=5,
    )
    availability = _availability(
        students,
        teachers,
        slots,
        allowed_students={(1, 1)},
        allowed_teachers={(2, 1)},
    )

    result = solve_optimization(
        _input(
            students=students,
            teachers=teachers,
            requests=(request,),
            slots=slots,
            availability=availability,
        )
    )

    assert not result.assignments
    assert len(result.unassigned_lessons) == 1
    assert DiagnosticCode.PRIORITY_5_COMMON_SLOT_UNAVAILABLE in {
        reason.code for reason in result.unassigned_lessons[0].reasons
    }


def test_one_to_one_required_slot_cannot_accept_another_student() -> None:
    source = _input(
        students=(_student(1), _student(2)),
        teachers=(_teacher(1),),
        requests=(
            replace(_request(1, 1), one_to_one_required=True),
            _request(2, 2),
        ),
        slots=_slots(1),
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 1
    assert len(result.unassigned_lessons) == 1


def test_normal_lessons_can_form_one_to_two() -> None:
    source = _input(
        students=(_student(1), _student(2)),
        teachers=(_teacher(1),),
        requests=(_request(1, 1), _request(2, 2)),
        slots=_slots(1),
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 2
    placements = {(item.teacher_id, item.day, item.time_slot_id) for item in result.assignments}
    assert placements == {(1, DAY, 1)}


def test_teacher_slot_capacity_is_at_most_two() -> None:
    source = _input(
        students=tuple(_student(student_id) for student_id in (1, 2, 3)),
        teachers=(_teacher(1),),
        requests=tuple(_request(request_id, request_id) for request_id in (1, 2, 3)),
        slots=_slots(1),
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 2
    assert len(result.unassigned_lessons) == 1


def test_student_three_consecutive_slots_are_prevented_at_limit_two() -> None:
    source = _input(
        students=(_student(1, max_consecutive=2),),
        teachers=(_teacher(1, allow_gap=True),),
        requests=tuple(_request(request_id, 1) for request_id in (1, 2, 3)),
        slots=_slots(3),
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 2
    assert len(result.unassigned_lessons) == 1


def test_student_configured_for_three_may_use_three_consecutive_slots() -> None:
    source = _input(
        students=(_student(1, max_consecutive=3),),
        teachers=(_teacher(1),),
        requests=tuple(_request(request_id, 1) for request_id in (1, 2, 3)),
        slots=_slots(3),
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 3
    assert not result.unassigned_lessons
    assert {item.time_slot_id for item in result.assignments} == {1, 2, 3}


def test_student_ac_availability_does_not_create_a_gap() -> None:
    students = (_student(1, allow_gap=False),)
    teachers = (_teacher(1, allow_gap=True),)
    slots = _slots(3)
    availability = _availability(
        students,
        teachers,
        slots,
        allowed_students={(1, 1), (1, 3)},
        allowed_teachers={(1, 1), (1, 3)},
    )
    source = _input(
        students=students,
        teachers=teachers,
        requests=(_request(1, 1), _request(2, 1)),
        slots=slots,
        availability=availability,
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 1
    assert len(result.unassigned_lessons) == 1


def test_teacher_ac_availability_does_not_create_a_gap() -> None:
    students = (_student(1), _student(2))
    teachers = (_teacher(1, allow_gap=False),)
    slots = _slots(3)
    availability = _availability(
        students,
        teachers,
        slots,
        allowed_students={(1, 1), (2, 3)},
        allowed_teachers={(1, 1), (1, 3)},
    )
    source = _input(
        students=students,
        teachers=teachers,
        requests=(_request(1, 1), _request(2, 2)),
        slots=slots,
        availability=availability,
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 1
    assert len(result.unassigned_lessons) == 1


def test_gap_allowed_student_and_teacher_may_use_ac() -> None:
    students = (_student(1, allow_gap=True),)
    teachers = (_teacher(1, allow_gap=True),)
    slots = _slots(3)
    availability = _availability(
        students,
        teachers,
        slots,
        allowed_students={(1, 1), (1, 3)},
        allowed_teachers={(1, 1), (1, 3)},
    )
    source = _input(
        students=students,
        teachers=teachers,
        requests=(_request(1, 1), _request(2, 1)),
        slots=slots,
        availability=availability,
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 2
    assert {item.time_slot_id for item in result.assignments} == {1, 3}


def test_one_to_two_aggregation_never_overrides_teacher_gap_constraint() -> None:
    students = (_student(1), _student(2), _student(3))
    teachers = (_teacher(1, allow_gap=False),)
    slots = _slots(3)
    availability = _availability(
        students,
        teachers,
        slots,
        allowed_students={(1, 1), (2, 3), (3, 3)},
        allowed_teachers={(1, 1), (1, 3)},
    )
    source = _input(
        students=students,
        teachers=teachers,
        requests=(_request(1, 1), _request(2, 2), _request(3, 3)),
        slots=slots,
        availability=availability,
    )

    result = solve_optimization(source)

    teacher_slots = {item.time_slot_id for item in result.assignments if item.teacher_id == 1}
    assert teacher_slots != {1, 3}
    assert len(result.unassigned_lessons) >= 1


def test_gap_causing_aggregation_uses_another_teacher_instead() -> None:
    students = (_student(1), _student(2), _student(3))
    teachers = (
        _teacher(1, allow_gap=False),
        _teacher(2, allow_gap=True),
    )
    slots = _slots(3)
    first = replace(
        _request(1, 1),
        regular_teacher_id=1,
        regular_teacher_priority=5,
    )
    availability = _availability(
        students,
        teachers,
        slots,
        allowed_students={(1, 1), (2, 3), (3, 3)},
        allowed_teachers={(1, 1), (1, 3), (2, 3)},
    )
    source = _input(
        students=students,
        teachers=teachers,
        requests=(first, _request(2, 2), _request(3, 3)),
        slots=slots,
        availability=availability,
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 3
    assert {
        (item.student_id, item.teacher_id, item.time_slot_id) for item in result.assignments
    } == {
        (1, 1, 1),
        (2, 2, 3),
        (3, 2, 3),
    }
    assert not result.unassigned_lessons


def test_group_lesson_blocks_participating_student() -> None:
    slot = _slots(1)[0]
    source = _input(
        students=(_student(1),),
        teachers=(_teacher(1),),
        requests=(_request(1, 1),),
        slots=(slot,),
        groups=(
            GroupBlockData(
                id=1,
                day=DAY,
                start_time=slot.start_time,
                end_time=slot.end_time,
                student_ids=frozenset({1}),
            ),
        ),
    )

    result = solve_optimization(source)

    assert not result.assignments
    assert len(result.unassigned_lessons) == 1


def test_group_lesson_blocks_its_teacher() -> None:
    slot = _slots(1)[0]
    source = _input(
        students=(_student(1),),
        teachers=(_teacher(1),),
        requests=(_request(1, 1),),
        slots=(slot,),
        groups=(
            GroupBlockData(
                id=1,
                day=DAY,
                start_time=slot.start_time,
                end_time=slot.end_time,
                teacher_id=1,
            ),
        ),
    )

    result = solve_optimization(source)

    assert not result.assignments
    assert len(result.unassigned_lessons) == 1


def test_locked_assignment_is_preserved_even_when_another_teacher_is_preferred() -> None:
    request = replace(
        _request(1, 1),
        regular_teacher_id=1,
        regular_teacher_priority=4,
        preferred_teacher_ids=(1, None, None),
    )
    source = _input(
        students=(_student(1),),
        teachers=(_teacher(1), _teacher(2)),
        requests=(request,),
        slots=_slots(1),
        existing=(
            ExistingAssignmentData(
                id=1,
                lesson_request_id=1,
                session_index=1,
                day=DAY,
                time_slot_id=1,
                teacher_id=2,
                is_locked=True,
            ),
        ),
    )

    result = solve_optimization(source)

    assert [(item.teacher_id, item.is_locked) for item in result.assignments] == [(2, True)]


def test_unlocked_existing_assignment_is_preserved_after_higher_objectives_tie() -> None:
    source = _input(
        students=(_student(1),),
        teachers=(_teacher(1), _teacher(2)),
        requests=(_request(1, 1),),
        slots=_slots(1),
        existing=(
            ExistingAssignmentData(
                id=1,
                lesson_request_id=1,
                session_index=1,
                day=DAY,
                time_slot_id=1,
                teacher_id=2,
            ),
        ),
    )

    result = solve_optimization(source)

    assert [(item.teacher_id, item.time_slot_id) for item in result.assignments] == [(2, 1)]
    assert result.objective_breakdown.changed_assignment_count == 0


def test_different_subjects_can_form_one_to_two_when_teacher_is_qualified() -> None:
    source = _input(
        students=(_student(1), _student(2)),
        teachers=(_teacher(1, subjects=frozenset({1, 2})),),
        subjects=(SUBJECT_1, SUBJECT_2),
        requests=(_request(1, 1, subject_id=1), _request(2, 2, subject_id=2)),
        slots=_slots(1),
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 2
    assert {item.subject_id for item in result.assignments} == {1, 2}


def test_unqualified_subject_is_never_assigned_for_aggregation() -> None:
    source = _input(
        students=(_student(1), _student(2)),
        teachers=(_teacher(1, subjects=frozenset({1})),),
        subjects=(SUBJECT_1, SUBJECT_2),
        requests=(_request(1, 1, subject_id=1), _request(2, 2, subject_id=2)),
        slots=_slots(1),
    )

    result = solve_optimization(source)

    assert [(item.subject_id, item.teacher_id) for item in result.assignments] == [(1, 1)]
    assert len(result.unassigned_lessons) == 1
    assert DiagnosticCode.TEACHER_UNQUALIFIED in {
        reason.code for reason in result.unassigned_lessons[0].reasons
    }


def test_required_session_count_is_exact_not_an_upper_bound() -> None:
    source = _input(
        students=(_student(1),),
        teachers=(_teacher(1),),
        requests=(_request(1, 1, sessions=2),),
        slots=_slots(4),
    )

    result = solve_optimization(source)

    assert len(result.assignments) == 2
    assert len({(item.lesson_request_id, item.session_index) for item in result.assignments}) == 2


def test_unassigned_count_precedes_teacher_preferences() -> None:
    request = replace(
        _request(1, 1),
        regular_teacher_id=1,
        regular_teacher_priority=4,
        preferred_teacher_ids=(1, None, None),
    )
    students = (_student(1),)
    teachers = (_teacher(1), _teacher(2))
    slots = _slots(1)
    availability = _availability(
        students,
        teachers,
        slots,
        allowed_students={(1, 1)},
        allowed_teachers={(2, 1)},
    )
    source = _input(
        students=students,
        teachers=teachers,
        requests=(request,),
        slots=slots,
        availability=availability,
    )

    result = solve_optimization(source)

    assert [(item.teacher_id, item.time_slot_id) for item in result.assignments] == [(2, 1)]
    assert result.objective_breakdown.unassigned_count == 0
    assert result.objective_breakdown.teacher_preference_penalty > 0


def test_deadline_after_first_stage_returns_the_verified_incumbent() -> None:
    source = replace(
        _input(
            students=(_student(1),),
            teachers=(_teacher(1),),
            requests=(_request(1, 1),),
            slots=_slots(1),
        ),
        settings=replace(_settings(), time_limit_seconds=5),
    )
    clock = _StageDeadlineClock()

    def expire_after_first_stage(progress: OptimizationProgress) -> None:
        if progress.stage_index == 1 and progress.solver_status == "OPTIMAL":
            clock.now = 6.0

    result = solve_optimization(source, progress=expire_after_first_stage, clock=clock)

    assert result.solver_status == "FEASIBLE"
    assert len(result.assignments) == 1
    assert not result.unassigned_lessons
    assert any("制限時間" in warning for warning in result.warnings)


def test_same_seed_and_single_worker_produce_same_normalized_solution() -> None:
    source = _input(
        students=(_student(1), _student(2)),
        teachers=(_teacher(1), _teacher(2)),
        requests=(_request(1, 1, sessions=2), _request(2, 2, sessions=2)),
        slots=_slots(3),
    )

    first = solve_optimization(source)
    second = solve_optimization(source)

    assert first.solver_status == second.solver_status == "OPTIMAL"
    assert first.assignments == second.assignments
    assert first.unassigned_lessons == second.unassigned_lessons
    assert first.objective_breakdown == second.objective_breakdown


class _StageDeadlineClock:
    """第1段階のsolve後、次段階開始時だけdeadline超過を再現する。"""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _settings() -> OptimizationSettings:
    return OptimizationSettings(
        time_limit_seconds=10,
        random_seed=20260729,
        num_search_workers=1,
        regular_teacher_priority_weights=(1, 3, 6, 10),
        preferred_teacher_rank_weights=(9, 6, 3),
        student_preferred_time_weight=1,
        teacher_preferred_time_weight=1,
        preserve_existing_assignment_weight=1,
    )


def _student(
    student_id: int,
    *,
    max_consecutive: int = 2,
    allow_gap: bool = False,
) -> StudentData:
    return StudentData(
        id=student_id,
        display_name=f"架空生徒{student_id}",
        default_max_consecutive_slots=max_consecutive,
        allow_gap=allow_gap,
    )


def _teacher(
    teacher_id: int,
    *,
    subjects: frozenset[int] = frozenset({1}),
    allow_gap: bool = False,
) -> TeacherData:
    return TeacherData(
        id=teacher_id,
        display_name=f"架空講師{teacher_id}",
        qualified_subject_ids=subjects,
        allow_gap=allow_gap,
    )


def _request(
    request_id: int,
    student_id: int,
    *,
    subject_id: int = 1,
    sessions: int = 1,
) -> LessonRequestData:
    return LessonRequestData(
        id=request_id,
        student_id=student_id,
        subject_id=subject_id,
        required_sessions=sessions,
    )


def _slots(count: int) -> tuple[TimeSlotData, ...]:
    starts = (time(9), time(10), time(11), time(12), time(13), time(14))
    return tuple(
        TimeSlotData(
            id=index,
            code=chr(ord("A") + index - 1),
            display_name=f"{chr(ord('A') + index - 1)}コマ",
            start_time=starts[index - 1],
            end_time=time(starts[index - 1].hour, 50),
            sort_order=index,
        )
        for index in range(1, count + 1)
    )


def _availability(
    students: tuple[StudentData, ...],
    teachers: tuple[TeacherData, ...],
    slots: tuple[TimeSlotData, ...],
    *,
    allowed_students: set[tuple[int, int]] | None = None,
    allowed_teachers: set[tuple[int, int]] | None = None,
) -> tuple[AvailabilityData, ...]:
    student_keys = allowed_students or {
        (student.id, slot.id) for student in students for slot in slots
    }
    teacher_keys = allowed_teachers or {
        (teacher.id, slot.id) for teacher in teachers for slot in slots
    }
    return tuple(
        [
            *(
                AvailabilityData(
                    owner_type="student",
                    owner_id=student_id,
                    day=DAY,
                    time_slot_id=slot_id,
                    level=1,
                )
                for student_id, slot_id in sorted(student_keys)
            ),
            *(
                AvailabilityData(
                    owner_type="teacher",
                    owner_id=teacher_id,
                    day=DAY,
                    time_slot_id=slot_id,
                    level=1,
                )
                for teacher_id, slot_id in sorted(teacher_keys)
            ),
        ]
    )


def _input(
    *,
    students: tuple[StudentData, ...],
    teachers: tuple[TeacherData, ...],
    requests: tuple[LessonRequestData, ...],
    slots: tuple[TimeSlotData, ...],
    subjects: tuple[SubjectData, ...] = (SUBJECT_1,),
    availability: tuple[AvailabilityData, ...] | None = None,
    groups: tuple[GroupBlockData, ...] = (),
    existing: tuple[ExistingAssignmentData, ...] = (),
    extra_dates: Iterable[date] = (),
) -> OptimizationInput:
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY, *tuple(extra_dates)),
        time_slots=slots,
        students=students,
        teachers=teachers,
        subjects=subjects,
        lesson_requests=requests,
        availabilities=(
            availability if availability is not None else _availability(students, teachers, slots)
        ),
        group_blocks=groups,
        existing_assignments=existing,
        settings=_settings(),
    )
