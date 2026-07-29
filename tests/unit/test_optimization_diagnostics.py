from __future__ import annotations

from dataclasses import replace
from datetime import date, time

from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.diagnostics import diagnose_unassigned_lessons
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    DiagnosticCode,
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

DAY = date(2026, 8, 3)
Y = TimeSlotData(100, "Y", "Yコマ", time(14, 10), time(15, 30), 1)
Z = TimeSlotData(101, "Z", "Zコマ", time(15, 40), time(17, 0), 2)
A = TimeSlotData(102, "A", "Aコマ", time(17, 10), time(18, 30), 3)


def test_zero_candidate_uses_candidate_generation_diagnostics() -> None:
    request = replace(
        _request(),
        regular_teacher_id=10,
        regular_teacher_priority=5,
    )
    source = _input(requests=(request,), slots=(Y,))
    source = replace(
        source,
        availabilities=tuple(
            item for item in source.availabilities if item.owner_type != "teacher"
        ),
    )
    generation = generate_candidates(source)
    result = _result(unassigned=(_unassigned(request, 1),))

    diagnosed = diagnose_unassigned_lessons(source, generation, result)

    codes = [reason.code for reason in diagnosed[0].reasons]
    assert DiagnosticCode.TEACHER_UNAVAILABLE in codes
    assert DiagnosticCode.PRIORITY_5_COMMON_SLOT_UNAVAILABLE in codes
    assert DiagnosticCode.NO_CANDIDATE in codes


def test_available_candidate_left_unused_gets_global_competition_reason() -> None:
    request = _request()
    source = _input(requests=(request,), slots=(Y,))
    generation = generate_candidates(source)
    result = _result(unassigned=(_unassigned(request, 1),))

    diagnosed = diagnose_unassigned_lessons(source, generation, result)

    assert [reason.code for reason in diagnosed[0].reasons] == [DiagnosticCode.GLOBAL_COMPETITION]
    assert diagnosed[0].reasons[0].excluded_candidate_count == 1


def test_final_solution_conflicts_are_reported_in_stable_reason_order() -> None:
    placed = _request()
    unassigned = _request(request_id=2000)
    source = _input(requests=(placed, unassigned), slots=(Y, Z, A))
    # 対象生徒と講師はYで既に埋まり、Aへ置けば双方に空きZが生じる。
    result = _result(
        assignments=(_assignment(placed, 1, Y),),
        unassigned=(_unassigned(unassigned, 1),),
    )

    diagnosed = diagnose_unassigned_lessons(
        source,
        generate_candidates(source),
        result,
    )

    codes = [reason.code for reason in diagnosed[0].reasons]
    assert codes == [
        DiagnosticCode.STUDENT_TIME_CONFLICT,
        DiagnosticCode.STUDENT_GAP_NOT_ALLOWED,
        DiagnosticCode.TEACHER_GAP_NOT_ALLOWED,
        DiagnosticCode.GLOBAL_COMPETITION,
    ]


def test_teacher_capacity_and_one_to_one_reasons_are_distinguished() -> None:
    placed_one = _request(student_id=1)
    placed_two = _request(request_id=2000, student_id=2)
    target = _request(request_id=3000, student_id=3, one_to_one=True)
    source = _input(
        requests=(placed_one, placed_two, target),
        students=tuple(_student(index) for index in (1, 2, 3)),
        slots=(Y,),
    )
    result = OptimizationResult(
        solver_status="FEASIBLE",
        assignments=(
            _assignment(placed_one, 1, Y),
            _assignment(placed_two, 1, Y),
        ),
        unassigned_lessons=(_unassigned(target, 1),),
        objective_breakdown=ObjectiveBreakdown(unassigned_count=1),
        elapsed_seconds=0.1,
    )

    diagnosed = diagnose_unassigned_lessons(
        source,
        generate_candidates(source),
        result,
    )

    assert [reason.code for reason in diagnosed[0].reasons] == [
        DiagnosticCode.TEACHER_CAPACITY_EXCEEDED,
        DiagnosticCode.ONE_TO_ONE_CAPACITY,
    ]


def test_adding_third_consecutive_slot_is_diagnosed() -> None:
    placed = replace(_request(), required_sessions=2)
    target = _request(request_id=2000)
    source = _input(requests=(placed, target), slots=(Y, Z, A))
    result = _result(
        assignments=(
            _assignment(placed, 1, Y),
            _assignment(placed, 2, Z),
        ),
        unassigned=(_unassigned(target, 1),),
    )

    diagnosed = diagnose_unassigned_lessons(
        source,
        generate_candidates(source),
        result,
    )

    assert [reason.code for reason in diagnosed[0].reasons] == [
        DiagnosticCode.STUDENT_TIME_CONFLICT,
        DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT,
    ]


def _input(
    *,
    requests: tuple[LessonRequestData, ...],
    slots: tuple[TimeSlotData, ...],
    students: tuple[StudentData, ...] = (StudentData(1, "架空生徒・青空"),),
) -> OptimizationInput:
    teacher = TeacherData(10, "架空講師・若葉", frozenset({500}))
    availabilities = tuple(
        [
            AvailabilityData("student", student.id, DAY, slot.id, 1)
            for student in students
            for slot in slots
        ]
        + [AvailabilityData("teacher", teacher.id, DAY, slot.id, 1) for slot in slots]
    )
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY,),
        time_slots=slots,
        students=students,
        teachers=(teacher,),
        subjects=(SubjectData(500, "JH_MATH", "中学校・数学"),),
        lesson_requests=requests,
        availabilities=availabilities,
        group_blocks=(),
        existing_assignments=(),
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
    one_to_one: bool = False,
) -> LessonRequestData:
    return LessonRequestData(
        id=request_id,
        student_id=student_id,
        subject_id=500,
        required_sessions=1,
        one_to_one_required=one_to_one,
    )


def _student(student_id: int) -> StudentData:
    return StudentData(student_id, f"架空生徒{student_id}")


def _assignment(
    request: LessonRequestData,
    session_index: int,
    slot: TimeSlotData,
) -> ScheduledAssignment:
    return ScheduledAssignment(
        lesson_request_id=request.id,
        session_index=session_index,
        student_id=request.student_id,
        subject_id=request.subject_id,
        teacher_id=10,
        day=DAY,
        time_slot_id=slot.id,
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
