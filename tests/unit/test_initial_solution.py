from __future__ import annotations

from dataclasses import replace
from datetime import date, time

import pytest

from summer_scheduler.optimization.candidates import generate_candidates
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
from summer_scheduler.optimization.initial_solution import (
    InitialSolutionCancelled,
    build_initial_solution,
    validate_initial_solution,
)

DAY = date(2026, 8, 3)
Y = TimeSlotData(100, "Y", "Yコマ", time(14, 10), time(15, 30), 1)
Z = TimeSlotData(101, "Z", "Zコマ", time(15, 40), time(17, 0), 2)
A = TimeSlotData(102, "A", "Aコマ", time(17, 10), time(18, 30), 3)


def test_zero_candidates_returns_valid_all_unassigned_solution() -> None:
    source = _input(
        requests=(_request(1000, 1),),
        students=(_student(1),),
        teachers=(_teacher(10),),
        slots=(Y,),
        student_availability={1: frozenset()},
    )
    generation = generate_candidates(source)

    solution = build_initial_solution(source, generation)

    assert solution is not None
    assert solution.selected_candidates == ()
    assert solution.unassigned_session_keys == ((1000, 1),)
    assert validate_initial_solution(source, generation, solution).is_valid


def test_scarce_priority_five_session_is_placed_before_flexible_session() -> None:
    priority_five = replace(
        _request(1000, 1),
        regular_teacher_id=10,
        regular_teacher_priority=5,
    )
    flexible = replace(
        _request(2000, 2),
        one_to_one_required=True,
        regular_teacher_id=10,
        regular_teacher_priority=4,
    )
    source = _input(
        requests=(priority_five, flexible),
        students=(_student(1), _student(2)),
        teachers=(_teacher(10), _teacher(20)),
        slots=(Y, Z),
        student_availability={1: frozenset({Y.id}), 2: frozenset({Y.id, Z.id})},
        teacher_availability={
            10: frozenset({Y.id}),
            20: frozenset({Z.id}),
        },
    )
    generation = generate_candidates(source)

    first = build_initial_solution(source, generation)
    second = build_initial_solution(source, generation)

    assert first == second
    assert first is not None
    assert {
        (item.lesson_request_id, item.teacher_id, item.time_slot_id)
        for item in first.selected_candidates
    } == {(1000, 10, Y.id), (2000, 20, Z.id)}
    assert first.unassigned_session_keys == ()
    assert validate_initial_solution(source, generation, first).is_valid


def test_teacher_capacity_and_one_to_one_are_never_relaxed() -> None:
    requests = tuple(_request(1000 + student_id, student_id) for student_id in (1, 2, 3))
    students = tuple(_student(student_id) for student_id in (1, 2, 3))
    source = _input(
        requests=requests,
        students=students,
        teachers=(_teacher(10),),
        slots=(Y,),
    )

    paired = build_initial_solution(source, generate_candidates(source))

    assert paired is not None
    assert len(paired.selected_candidates) == 2
    assert len(paired.unassigned_session_keys) == 1
    assert validate_initial_solution(source, generate_candidates(source), paired).is_valid

    one_to_one_source = replace(
        source,
        lesson_requests=(replace(requests[0], one_to_one_required=True), *requests[1:]),
    )
    one_to_one = build_initial_solution(
        one_to_one_source,
        generate_candidates(one_to_one_source),
    )

    assert one_to_one is not None
    assert len(one_to_one.selected_candidates) == 1
    assert one_to_one.selected_candidates[0].lesson_request_id == requests[0].id
    assert validate_initial_solution(
        one_to_one_source,
        generate_candidates(one_to_one_source),
        one_to_one,
    ).is_valid


def test_student_cannot_receive_two_sessions_in_the_same_slot() -> None:
    request = replace(_request(1000, 1), required_sessions=2)
    source = _input(
        requests=(request,),
        students=(_student(1),),
        teachers=(_teacher(10), _teacher(20)),
        slots=(Y,),
    )

    solution = build_initial_solution(source, generate_candidates(source))

    assert solution is not None
    assert len(solution.selected_candidates) == 1
    assert len(solution.unassigned_session_keys) == 1
    assert validate_initial_solution(
        source,
        generate_candidates(source),
        solution,
    ).is_valid


def test_locked_assignment_is_preserved_before_greedy_selection() -> None:
    request = replace(_request(1000, 1), required_sessions=2)
    source = _input(
        requests=(request,),
        students=(_student(1),),
        teachers=(_teacher(10),),
        slots=(Y, Z),
        existing=(
            ExistingAssignmentData(
                id=1,
                lesson_request_id=request.id,
                session_index=2,
                day=DAY,
                time_slot_id=Z.id,
                teacher_id=10,
                is_locked=True,
            ),
        ),
    )
    generation = generate_candidates(source)

    solution = build_initial_solution(source, generation)

    assert solution is not None
    assert {(item.session_index, item.time_slot_id) for item in solution.selected_candidates} == {
        (1, Y.id),
        (2, Z.id),
    }
    assert validate_initial_solution(source, generation, solution).is_valid


def test_request_consecutive_override_is_applied_exactly() -> None:
    default_request = replace(_request(1000, 1), required_sessions=3)
    source = _input(
        requests=(default_request,),
        students=(_student(1, max_consecutive=2),),
        teachers=(_teacher(10),),
        slots=(Y, Z, A),
    )

    default_solution = build_initial_solution(source, generate_candidates(source))

    assert default_solution is not None
    assert len(default_solution.selected_candidates) == 2
    assert default_solution.unassigned_session_keys == ((1000, 3),)

    override_source = replace(
        source,
        lesson_requests=(replace(default_request, max_consecutive_slots_override=3),),
    )
    override_solution = build_initial_solution(
        override_source,
        generate_candidates(override_source),
    )

    assert override_solution is not None
    assert len(override_solution.selected_candidates) == 3
    assert override_solution.unassigned_session_keys == ()
    assert validate_initial_solution(
        override_source,
        generate_candidates(override_source),
        override_solution,
    ).is_valid


def test_disabled_slot_remains_part_of_gap_sequence() -> None:
    disabled_z = replace(Z, enabled=False)
    request = replace(
        _request(1000, 1),
        required_sessions=2,
        allow_gap_override=True,
    )
    strict_teacher_source = _input(
        requests=(request,),
        students=(_student(1),),
        teachers=(_teacher(10, allow_gap=False),),
        slots=(Y, disabled_z, A),
    )

    strict_teacher = build_initial_solution(
        strict_teacher_source,
        generate_candidates(strict_teacher_source),
    )

    assert strict_teacher is not None
    assert len(strict_teacher.selected_candidates) == 1

    permissive_source = replace(
        strict_teacher_source,
        teachers=(_teacher(10, allow_gap=True),),
    )
    permissive = build_initial_solution(
        permissive_source,
        generate_candidates(permissive_source),
    )

    assert permissive is not None
    assert len(permissive.selected_candidates) == 2
    assert validate_initial_solution(
        permissive_source,
        generate_candidates(permissive_source),
        permissive,
    ).is_valid


def test_request_gap_override_takes_priority_over_permissive_student() -> None:
    disabled_z = replace(Z, enabled=False)
    strict_request = replace(
        _request(1000, 1),
        required_sessions=2,
        allow_gap_override=False,
    )
    source = _input(
        requests=(strict_request,),
        students=(replace(_student(1), allow_gap=True),),
        teachers=(_teacher(10, allow_gap=True),),
        slots=(Y, disabled_z, A),
    )

    strict_solution = build_initial_solution(source, generate_candidates(source))

    assert strict_solution is not None
    assert len(strict_solution.selected_candidates) == 1

    permissive_source = replace(
        source,
        lesson_requests=(replace(strict_request, allow_gap_override=True),),
    )
    permissive_solution = build_initial_solution(
        permissive_source,
        generate_candidates(permissive_source),
    )
    assert permissive_solution is not None
    assert len(permissive_solution.selected_candidates) == 2
    assert validate_initial_solution(
        permissive_source,
        generate_candidates(permissive_source),
        permissive_solution,
    ).is_valid


def test_group_lesson_occupancy_can_fill_student_and_teacher_gap() -> None:
    request = replace(
        _request(1000, 1),
        required_sessions=2,
        max_consecutive_slots_override=3,
    )
    source = _input(
        requests=(request,),
        students=(_student(1, max_consecutive=3),),
        teachers=(_teacher(10),),
        slots=(Y, Z, A),
        group_blocks=(
            GroupBlockData(
                id=1,
                day=DAY,
                start_time=Z.start_time,
                end_time=Z.end_time,
                teacher_id=10,
                student_ids=frozenset({1}),
            ),
        ),
    )
    generation = generate_candidates(source)

    solution = build_initial_solution(source, generation)

    assert solution is not None
    assert {item.time_slot_id for item in solution.selected_candidates} == {Y.id, A.id}
    assert validate_initial_solution(source, generation, solution).is_valid


def test_unsafe_locked_base_returns_no_hint() -> None:
    request = _request(1000, 1)
    source = _input(
        requests=(request,),
        students=(_student(1),),
        teachers=(_teacher(10),),
        slots=(Y,),
        existing=(
            ExistingAssignmentData(
                id=1,
                lesson_request_id=request.id,
                session_index=1,
                day=DAY,
                time_slot_id=Y.id,
                teacher_id=10,
                is_locked=True,
            ),
        ),
        group_blocks=(
            GroupBlockData(
                id=1,
                day=DAY,
                start_time=Y.start_time,
                end_time=Y.end_time,
                student_ids=frozenset({1}),
            ),
        ),
    )
    generation = generate_candidates(source)

    assert build_initial_solution(source, generation) is None


def test_public_validation_rejects_corrupted_partition() -> None:
    source = _input(
        requests=(_request(1000, 1),),
        students=(_student(1),),
        teachers=(_teacher(10),),
        slots=(Y,),
    )
    generation = generate_candidates(source)
    solution = build_initial_solution(source, generation)
    assert solution is not None
    corrupted = replace(solution, unassigned_session_keys=((1000, 1),))

    report = validate_initial_solution(source, generation, corrupted)

    assert not report.is_valid
    assert DiagnosticCode.SESSION_DUPLICATE in {violation.code for violation in report.violations}


def test_cancellation_is_checked_before_work() -> None:
    source = _input(
        requests=(_request(1000, 1),),
        students=(_student(1),),
        teachers=(_teacher(10),),
        slots=(Y,),
    )

    with pytest.raises(InitialSolutionCancelled):
        build_initial_solution(
            source,
            generate_candidates(source),
            is_cancelled=lambda: True,
        )


def _input(
    *,
    requests: tuple[LessonRequestData, ...],
    students: tuple[StudentData, ...],
    teachers: tuple[TeacherData, ...],
    slots: tuple[TimeSlotData, ...],
    student_availability: dict[int, frozenset[int]] | None = None,
    teacher_availability: dict[int, frozenset[int]] | None = None,
    existing: tuple[ExistingAssignmentData, ...] = (),
    group_blocks: tuple[GroupBlockData, ...] = (),
) -> OptimizationInput:
    student_availability = student_availability or {
        student.id: frozenset(slot.id for slot in slots) for student in students
    }
    teacher_availability = teacher_availability or {
        teacher.id: frozenset(slot.id for slot in slots) for teacher in teachers
    }
    availabilities = tuple(
        AvailabilityData("student", student.id, DAY, slot.id, 2)
        for student in students
        for slot in slots
        if slot.id in student_availability.get(student.id, ())
    ) + tuple(
        AvailabilityData("teacher", teacher.id, DAY, slot.id, 2)
        for teacher in teachers
        for slot in slots
        if slot.id in teacher_availability.get(teacher.id, ())
    )
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY,),
        time_slots=slots,
        students=students,
        teachers=teachers,
        subjects=(SubjectData(500, "JH_MATH", "中学校・数学"),),
        lesson_requests=requests,
        availabilities=availabilities,
        group_blocks=group_blocks,
        existing_assignments=existing,
        settings=OptimizationSettings(
            time_limit_seconds=30,
            random_seed=20260729,
            num_search_workers=1,
            regular_teacher_priority_weights=(1, 2, 3, 4),
            preferred_teacher_rank_weights=(3, 2, 1),
            student_preferred_time_weight=2,
            teacher_preferred_time_weight=1,
            preserve_existing_assignment_weight=3,
        ),
    )


def _request(request_id: int, student_id: int) -> LessonRequestData:
    return LessonRequestData(
        id=request_id,
        student_id=student_id,
        subject_id=500,
        required_sessions=1,
    )


def _student(student_id: int, *, max_consecutive: int = 2) -> StudentData:
    return StudentData(
        id=student_id,
        display_name=f"架空生徒{student_id}",
        default_max_consecutive_slots=max_consecutive,
    )


def _teacher(teacher_id: int, *, allow_gap: bool = False) -> TeacherData:
    return TeacherData(
        id=teacher_id,
        display_name=f"架空講師{teacher_id}",
        qualified_subject_ids=frozenset({500}),
        allow_gap=allow_gap,
    )
