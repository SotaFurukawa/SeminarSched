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
    ObjectiveBreakdown,
    OptimizationInput,
    OptimizationResult,
    OptimizationSettings,
    ScheduledAssignment,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
    UnassignedLesson,
)
from summer_scheduler.optimization.result_validation import (
    InvalidOptimizationResultError,
    ResultValidationReport,
    require_valid_optimization_result,
    validate_optimization_result,
)

DAY = date(2026, 8, 3)
Y = TimeSlotData(100, "Y", "Yコマ", time(14, 10), time(15, 30), 1)
Z = TimeSlotData(101, "Z", "Zコマ", time(15, 40), time(17, 0), 2)
A = TimeSlotData(102, "A", "Aコマ", time(17, 10), time(18, 30), 3)


def test_valid_result_has_no_violations() -> None:
    request = _request(required_sessions=2)
    source = _input(requests=(request,), slots=(Y, Z))
    result = _result(
        assignments=(
            _assignment(request, 1, Y),
            _assignment(request, 2, Z),
        )
    )

    report = validate_optimization_result(source, generate_candidates(source), result)

    assert report.is_valid
    assert report.violations == ()
    require_valid_optimization_result(source, generate_candidates(source), result)


def test_each_session_must_have_exactly_one_result_representation() -> None:
    request = _request()
    source = _input(requests=(request,), slots=(Y,))
    duplicate = _result(
        assignments=(_assignment(request, 1, Y),),
        unassigned=(_unassigned(request, 1), _unassigned(replace(request, id=999), 1)),
    )

    report = validate_optimization_result(source, generate_candidates(source), duplicate)

    assert DiagnosticCode.SESSION_DUPLICATE in _codes(report)
    assert DiagnosticCode.UNEXPECTED_SESSION in _codes(report)

    missing = validate_optimization_result(
        source,
        generate_candidates(source),
        _result(),
    )
    assert DiagnosticCode.SESSION_MISSING in _codes(missing)


def test_assignment_must_match_generated_candidate_and_request_references() -> None:
    request = _request()
    source = _input(requests=(request,), slots=(Y,))
    invalid = replace(
        _assignment(request, 1, Y),
        student_id=999,
        day=date(2026, 8, 9),
    )

    report = validate_optimization_result(
        source,
        generate_candidates(source),
        _result(assignments=(invalid,)),
    )

    assert {
        DiagnosticCode.RESULT_REFERENCE_MISMATCH,
        DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE,
    }.issubset(_codes(report))


def test_locked_assignment_must_keep_target_and_locked_flag() -> None:
    request = _request()
    source = _input(
        requests=(request,),
        slots=(Y, Z),
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
    )
    changed = _assignment(request, 1, Z, is_locked=False)

    report = validate_optimization_result(
        source,
        generate_candidates(source),
        _result(assignments=(changed,)),
    )

    assert DiagnosticCode.LOCKED_ASSIGNMENT_NOT_PRESERVED in _codes(report)
    with pytest.raises(InvalidOptimizationResultError) as exc_info:
        require_valid_optimization_result(
            source,
            generate_candidates(source),
            _result(assignments=(changed,)),
        )
    assert not exc_info.value.report.is_valid


def test_student_same_time_and_teacher_capacity_are_rejected() -> None:
    same_student_requests = (_request(), _request(request_id=2000))
    student_source = _input(requests=same_student_requests, slots=(Y,))
    student_result = _result(
        assignments=tuple(_assignment(request, 1, Y) for request in same_student_requests)
    )
    student_report = validate_optimization_result(
        student_source,
        generate_candidates(student_source),
        student_result,
    )
    assert DiagnosticCode.STUDENT_TIME_CONFLICT in _codes(student_report)

    requests = tuple(_request(request_id=1000 + index, student_id=index) for index in (1, 2, 3))
    teacher_source = _input(
        requests=requests,
        students=tuple(_student(index) for index in (1, 2, 3)),
        slots=(Y,),
    )
    teacher_result = _result(assignments=tuple(_assignment(request, 1, Y) for request in requests))
    teacher_report = validate_optimization_result(
        teacher_source,
        generate_candidates(teacher_source),
        teacher_result,
    )
    assert DiagnosticCode.TEACHER_CAPACITY_EXCEEDED in _codes(teacher_report)


def test_one_to_one_cannot_share_teacher_slot() -> None:
    requests = (
        _request(one_to_one=True),
        _request(request_id=2000, student_id=2),
    )
    source = _input(
        requests=requests,
        students=(_student(1), _student(2)),
        slots=(Y,),
    )
    result = _result(assignments=tuple(_assignment(request, 1, Y) for request in requests))

    report = validate_optimization_result(source, generate_candidates(source), result)

    assert DiagnosticCode.ONE_TO_ONE_CAPACITY in _codes(report)


def test_group_conflict_uses_half_open_interval_boundaries() -> None:
    request = _request()
    overlap = _input(
        requests=(request,),
        slots=(Y,),
        group_blocks=(
            GroupBlockData(
                id=1,
                day=DAY,
                start_time=time(15, 0),
                end_time=time(15, 45),
                student_ids=frozenset({1}),
            ),
        ),
    )
    overlap_report = validate_optimization_result(
        overlap,
        generate_candidates(overlap),
        _result(assignments=(_assignment(request, 1, Y),)),
    )
    assert DiagnosticCode.GROUP_LESSON_CONFLICT in _codes(overlap_report)

    touching = replace(
        overlap,
        group_blocks=(
            GroupBlockData(
                id=2,
                day=DAY,
                start_time=Y.end_time,
                end_time=time(16, 0),
                student_ids=frozenset({1}),
            ),
        ),
    )
    touching_report = validate_optimization_result(
        touching,
        generate_candidates(touching),
        _result(assignments=(_assignment(request, 1, Y),)),
    )
    assert touching_report.is_valid


def test_student_and_teacher_gaps_are_rejected() -> None:
    request = _request(required_sessions=2)
    source = _input(requests=(request,), slots=(Y, Z, A))
    result = _result(
        assignments=(
            _assignment(request, 1, Y),
            _assignment(request, 2, A),
        )
    )

    report = validate_optimization_result(source, generate_candidates(source), result)

    assert DiagnosticCode.STUDENT_GAP_NOT_ALLOWED in _codes(report)
    assert DiagnosticCode.TEACHER_GAP_NOT_ALLOWED in _codes(report)


def test_request_gap_override_takes_priority_over_student_default() -> None:
    request = _request(required_sessions=2, allow_gap_override=True)
    source = _input(
        requests=(request,),
        slots=(Y, Z, A),
        teachers=(_teacher(10, allow_gap=True),),
    )
    result = _result(
        assignments=(
            _assignment(request, 1, Y),
            _assignment(request, 2, A),
        )
    )

    report = validate_optimization_result(source, generate_candidates(source), result)

    assert report.is_valid


def test_request_consecutive_override_takes_priority_over_student_default() -> None:
    permitted = _request(required_sessions=3, max_consecutive_override=3)
    source = _input(requests=(permitted,), slots=(Y, Z, A))
    result = _result(
        assignments=(
            _assignment(permitted, 1, Y),
            _assignment(permitted, 2, Z),
            _assignment(permitted, 3, A),
        )
    )
    assert validate_optimization_result(
        source,
        generate_candidates(source),
        result,
    ).is_valid

    default_limit = replace(permitted, max_consecutive_slots_override=None)
    rejected_source = replace(source, lesson_requests=(default_limit,))
    rejected = validate_optimization_result(
        rejected_source,
        generate_candidates(rejected_source),
        result,
    )
    assert DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT in _codes(rejected)


def test_group_lesson_occupancy_can_fill_a_gap_without_being_overlapped() -> None:
    request = _request(
        required_sessions=2,
        max_consecutive_override=3,
    )
    source = _input(
        requests=(request,),
        slots=(Y, Z, A),
        students=(_student(1, max_consecutive=3),),
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
    result = _result(
        assignments=(
            _assignment(request, 1, Y),
            _assignment(request, 2, A),
        )
    )

    report = validate_optimization_result(source, generate_candidates(source), result)

    assert report.is_valid


def _input(
    *,
    requests: tuple[LessonRequestData, ...],
    slots: tuple[TimeSlotData, ...],
    students: tuple[StudentData, ...] = (StudentData(1, "架空生徒・青空"),),
    teachers: tuple[TeacherData, ...] = (TeacherData(10, "架空講師・若葉", frozenset({500})),),
    group_blocks: tuple[GroupBlockData, ...] = (),
    existing: tuple[ExistingAssignmentData, ...] = (),
) -> OptimizationInput:
    availabilities: list[AvailabilityData] = []
    for student in students:
        availabilities.extend(
            AvailabilityData("student", student.id, DAY, slot.id, 1) for slot in slots
        )
    for teacher in teachers:
        availabilities.extend(
            AvailabilityData("teacher", teacher.id, DAY, slot.id, 1) for slot in slots
        )
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY,),
        time_slots=slots,
        students=students,
        teachers=teachers,
        subjects=(SubjectData(500, "JH_MATH", "中学校・数学"),),
        lesson_requests=requests,
        availabilities=tuple(availabilities),
        group_blocks=group_blocks,
        existing_assignments=existing,
        settings=OptimizationSettings(
            time_limit_seconds=30,
            random_seed=7,
            num_search_workers=1,
            regular_teacher_priority_weights=(1, 2, 3, 4),
            preferred_teacher_rank_weights=(3, 2, 1),
            student_preferred_time_weight=2,
            teacher_preferred_time_weight=1,
            preserve_existing_assignment_weight=3,
        ),
    )


def _request(
    *,
    request_id: int = 1000,
    student_id: int = 1,
    required_sessions: int = 1,
    one_to_one: bool = False,
    allow_gap_override: bool | None = None,
    max_consecutive_override: int | None = None,
) -> LessonRequestData:
    return LessonRequestData(
        id=request_id,
        student_id=student_id,
        subject_id=500,
        required_sessions=required_sessions,
        one_to_one_required=one_to_one,
        allow_gap_override=allow_gap_override,
        max_consecutive_slots_override=max_consecutive_override,
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


def _assignment(
    request: LessonRequestData,
    session_index: int,
    slot: TimeSlotData,
    *,
    teacher_id: int = 10,
    is_locked: bool = False,
) -> ScheduledAssignment:
    return ScheduledAssignment(
        lesson_request_id=request.id,
        session_index=session_index,
        student_id=request.student_id,
        subject_id=request.subject_id,
        teacher_id=teacher_id,
        day=DAY,
        time_slot_id=slot.id,
        is_locked=is_locked,
    )


def _unassigned(
    request: LessonRequestData,
    session_index: int,
) -> UnassignedLesson:
    return UnassignedLesson(
        lesson_request_id=request.id,
        session_index=session_index,
        student_id=request.student_id,
        subject_id=request.subject_id,
        reasons=(),
    )


def _result(
    *,
    assignments: tuple[ScheduledAssignment, ...] = (),
    unassigned: tuple[UnassignedLesson, ...] = (),
) -> OptimizationResult:
    return OptimizationResult(
        solver_status="FEASIBLE",
        assignments=assignments,
        unassigned_lessons=unassigned,
        objective_breakdown=ObjectiveBreakdown(unassigned_count=len(unassigned)),
        elapsed_seconds=0.1,
    )


def _codes(report: ResultValidationReport) -> set[DiagnosticCode]:
    return {violation.code for violation in report.violations}
