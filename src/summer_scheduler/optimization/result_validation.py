"""OptimizationResultをsolverとは独立に再検証する保存前安全弁。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from summer_scheduler.domain.time_ranges import InvalidTimeRangeError
from summer_scheduler.optimization.diagnostics import diagnostic_message
from summer_scheduler.optimization.dto import (
    CandidateGenerationResult,
    DiagnosticCode,
    OptimizationInput,
    OptimizationResult,
    ScheduledAssignment,
)
from summer_scheduler.optimization.schedule_analysis import (
    ScheduleState,
    build_schedule_state,
    occupied_slots_are_contiguous,
    student_consecutive_limit_is_violated,
    student_day_requires_no_gap,
    student_occupied_slots,
    teacher_occupied_slots,
)
from summer_scheduler.optimization.sessions import SessionExpansionError, expand_sessions

_VALIDATION_ORDER = (
    DiagnosticCode.INVALID_INPUT,
    DiagnosticCode.SESSION_MISSING,
    DiagnosticCode.SESSION_DUPLICATE,
    DiagnosticCode.UNEXPECTED_SESSION,
    DiagnosticCode.RESULT_REFERENCE_MISMATCH,
    DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE,
    DiagnosticCode.LOCKED_ASSIGNMENT_NOT_PRESERVED,
    DiagnosticCode.STUDENT_TIME_CONFLICT,
    DiagnosticCode.TEACHER_CAPACITY_EXCEEDED,
    DiagnosticCode.ONE_TO_ONE_CAPACITY,
    DiagnosticCode.GROUP_LESSON_CONFLICT,
    DiagnosticCode.STUDENT_GAP_NOT_ALLOWED,
    DiagnosticCode.TEACHER_GAP_NOT_ALLOWED,
    DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT,
)
_ORDER_INDEX = {code: index for index, code in enumerate(_VALIDATION_ORDER)}


@dataclass(frozen=True, slots=True)
class ResultViolation:
    code: DiagnosticCode
    message: str
    lesson_request_id: int | None = None
    session_index: int | None = None
    day: date | None = None
    time_slot_id: int | None = None
    teacher_id: int | None = None
    details: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ResultValidationReport:
    violations: tuple[ResultViolation, ...]

    @property
    def is_valid(self) -> bool:
        return not self.violations


class InvalidOptimizationResultError(ValueError):
    """保存してはならないハード制約違反結果。"""

    def __init__(self, report: ResultValidationReport) -> None:
        self.report = report
        super().__init__(f"最適化結果に{len(report.violations)}件のハード制約違反があります")


def validate_optimization_result(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    result: OptimizationResult,
) -> ResultValidationReport:
    """入力と候補から独立に結果を検査し、全違反を安定順で返す。"""
    try:
        expected_sessions = expand_sessions(data.lesson_requests)
    except SessionExpansionError as exc:
        return ResultValidationReport(
            (
                _violation(
                    DiagnosticCode.INVALID_INPUT,
                    details=(("error", str(exc)),),
                ),
            )
        )

    if generation.input_diagnostics:
        return ResultValidationReport(
            tuple(
                _violation(
                    DiagnosticCode.INVALID_INPUT,
                    details=(("candidate_diagnostic", reason.code.value),),
                )
                for reason in generation.input_diagnostics
            )
        )
    try:
        state = build_schedule_state(data, result.assignments)
    except InvalidTimeRangeError as exc:
        return ResultValidationReport(
            (
                _violation(
                    DiagnosticCode.INVALID_INPUT,
                    details=(("error", str(exc)),),
                ),
            )
        )
    expected = {session.key: session for session in expected_sessions}
    requests = {request.id: request for request in data.lesson_requests}
    teachers = {teacher.id: teacher for teacher in data.teachers}
    subjects = {subject.id for subject in data.subjects}
    slots = {slot.id for slot in data.time_slots}
    violations: list[ResultViolation] = []

    _validate_generation_boundary(generation, set(expected), violations)
    _validate_session_partition(result, state, set(expected), violations)

    candidate_identities = {
        (
            candidate.lesson_request_id,
            candidate.session_index,
            candidate.student_id,
            candidate.subject_id,
            candidate.teacher_id,
            candidate.day,
            candidate.time_slot_id,
        )
        for candidate in generation.candidates
    }
    for assignment in result.assignments:
        key = (assignment.lesson_request_id, assignment.session_index)
        request = requests.get(assignment.lesson_request_id)
        if (
            request is None
            or assignment.student_id != request.student_id
            or assignment.subject_id != request.subject_id
            or assignment.teacher_id not in teachers
            or assignment.subject_id not in subjects
            or assignment.time_slot_id not in slots
        ):
            violations.append(
                _assignment_violation(DiagnosticCode.RESULT_REFERENCE_MISMATCH, assignment)
            )
        identity = (
            assignment.lesson_request_id,
            assignment.session_index,
            assignment.student_id,
            assignment.subject_id,
            assignment.teacher_id,
            assignment.day,
            assignment.time_slot_id,
        )
        if identity not in candidate_identities:
            violations.append(
                _assignment_violation(DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE, assignment)
            )
        if key not in expected:
            continue

    for unassigned in result.unassigned_lessons:
        request = requests.get(unassigned.lesson_request_id)
        if request is not None and (
            unassigned.student_id != request.student_id
            or unassigned.subject_id != request.subject_id
        ):
            violations.append(
                _violation(
                    DiagnosticCode.RESULT_REFERENCE_MISMATCH,
                    lesson_request_id=unassigned.lesson_request_id,
                    session_index=unassigned.session_index,
                )
            )

    _validate_locked_assignments(data, state, violations)
    _validate_occupancy_constraints(data, state, violations)
    return ResultValidationReport(tuple(sorted(violations, key=_violation_sort_key)))


def require_valid_optimization_result(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    result: OptimizationResult,
) -> None:
    report = validate_optimization_result(data, generation, result)
    if not report.is_valid:
        raise InvalidOptimizationResultError(report)


def _validate_generation_boundary(
    generation: CandidateGenerationResult,
    expected: set[tuple[int, int]],
    violations: list[ResultViolation],
) -> None:
    generated_keys = [session.key for session in generation.sessions]
    if len(generated_keys) != len(set(generated_keys)) or set(generated_keys) != expected:
        violations.append(
            _violation(
                DiagnosticCode.INVALID_INPUT,
                details=(("entity", "candidate_generation.sessions"),),
            )
        )
    if any(candidate.session_key not in expected for candidate in generation.candidates):
        violations.append(
            _violation(
                DiagnosticCode.INVALID_INPUT,
                details=(("entity", "candidate_generation.candidates"),),
            )
        )


def _validate_session_partition(
    result: OptimizationResult,
    state: ScheduleState,
    expected: set[tuple[int, int]],
    violations: list[ResultViolation],
) -> None:
    unassigned_by_session: dict[tuple[int, int], int] = {}
    for item in result.unassigned_lessons:
        key = (item.lesson_request_id, item.session_index)
        unassigned_by_session[key] = unassigned_by_session.get(key, 0) + 1

    represented_keys = set(state.assignments_by_session) | set(unassigned_by_session)
    for key in sorted(expected | represented_keys):
        count = len(state.assignments_by_session.get(key, ())) + unassigned_by_session.get(key, 0)
        if key not in expected:
            violations.append(
                _violation(
                    DiagnosticCode.UNEXPECTED_SESSION,
                    lesson_request_id=key[0],
                    session_index=key[1],
                )
            )
        elif count == 0:
            violations.append(
                _violation(
                    DiagnosticCode.SESSION_MISSING,
                    lesson_request_id=key[0],
                    session_index=key[1],
                )
            )
        elif count > 1:
            violations.append(
                _violation(
                    DiagnosticCode.SESSION_DUPLICATE,
                    lesson_request_id=key[0],
                    session_index=key[1],
                    details=(("representation_count", str(count)),),
                )
            )


def _validate_locked_assignments(
    data: OptimizationInput,
    state: ScheduleState,
    violations: list[ResultViolation],
) -> None:
    for locked in (item for item in data.existing_assignments if item.is_locked):
        matches = state.assignments_by_session.get(
            (locked.lesson_request_id, locked.session_index), ()
        )
        preserved = [
            item
            for item in matches
            if (
                item.day == locked.day
                and item.time_slot_id == locked.time_slot_id
                and item.teacher_id == locked.teacher_id
                and item.is_locked
            )
        ]
        if len(preserved) != 1:
            violations.append(
                _violation(
                    DiagnosticCode.LOCKED_ASSIGNMENT_NOT_PRESERVED,
                    lesson_request_id=locked.lesson_request_id,
                    session_index=locked.session_index,
                    day=locked.day,
                    time_slot_id=locked.time_slot_id,
                    teacher_id=locked.teacher_id,
                )
            )


def _validate_occupancy_constraints(
    data: OptimizationInput,
    state: ScheduleState,
    violations: list[ResultViolation],
) -> None:
    for (student_id, day, slot_id), assignments in state.student_occupancy.items():
        if len(assignments) > 1:
            violations.append(
                _violation(
                    DiagnosticCode.STUDENT_TIME_CONFLICT,
                    day=day,
                    time_slot_id=slot_id,
                    details=(
                        ("student_id", str(student_id)),
                        ("assignment_count", str(len(assignments))),
                    ),
                )
            )

    for (teacher_id, day, slot_id), assignments in state.teacher_occupancy.items():
        if len(assignments) > 2:
            violations.append(
                _violation(
                    DiagnosticCode.TEACHER_CAPACITY_EXCEEDED,
                    day=day,
                    time_slot_id=slot_id,
                    teacher_id=teacher_id,
                    details=(("assignment_count", str(len(assignments))),),
                )
            )
        if len(assignments) > 1 and any(
            state.requests.get(item.lesson_request_id) is None
            or state.requests[item.lesson_request_id].one_to_one_required
            for item in assignments
        ):
            violations.append(
                _violation(
                    DiagnosticCode.ONE_TO_ONE_CAPACITY,
                    day=day,
                    time_slot_id=slot_id,
                    teacher_id=teacher_id,
                )
            )

    for assignment in _result_assignments(state):
        if _assignment_group_conflict(state, assignment):
            violations.append(
                _assignment_violation(DiagnosticCode.GROUP_LESSON_CONFLICT, assignment)
            )

    _validate_gaps_and_consecutive(data, state, violations)


def _validate_gaps_and_consecutive(
    data: OptimizationInput,
    state: ScheduleState,
    violations: list[ResultViolation],
) -> None:
    student_days = set(state.assignments_by_student_day)
    student_days.update(
        (student_id, day) for student_id, day, _slot_id in state.group_student_occupancy
    )
    for student_id, day in sorted(student_days):
        if student_day_requires_no_gap(
            state, student_id, day
        ) and not occupied_slots_are_contiguous(
            state,
            student_occupied_slots(state, student_id, day),
        ):
            violations.append(
                _violation(
                    DiagnosticCode.STUDENT_GAP_NOT_ALLOWED,
                    day=day,
                    details=(("student_id", str(student_id)),),
                )
            )
        if student_consecutive_limit_is_violated(state, student_id, day):
            violations.append(
                _violation(
                    DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT,
                    day=day,
                    details=(("student_id", str(student_id)),),
                )
            )

    teachers = {teacher.id: teacher for teacher in data.teachers}
    teacher_days = set(state.assignments_by_teacher_day)
    teacher_days.update(
        (teacher_id, day) for teacher_id, day, _slot_id in state.group_teacher_occupancy
    )
    for teacher_id, day in sorted(teacher_days):
        teacher = teachers.get(teacher_id)
        if (
            teacher is None
            or teacher.allow_gap
            or occupied_slots_are_contiguous(
                state,
                teacher_occupied_slots(state, teacher_id, day),
            )
        ):
            continue
        violations.append(
            _violation(
                DiagnosticCode.TEACHER_GAP_NOT_ALLOWED,
                day=day,
                teacher_id=teacher_id,
            )
        )


def _result_assignments(state: ScheduleState) -> tuple[ScheduledAssignment, ...]:
    return tuple(
        assignment
        for assignments in state.assignments_by_session.values()
        for assignment in assignments
    )


def _assignment_group_conflict(
    state: ScheduleState,
    assignment: ScheduledAssignment,
) -> bool:
    candidate_key = (
        assignment.student_id,
        assignment.day,
        assignment.time_slot_id,
    )
    teacher_key = (
        assignment.teacher_id,
        assignment.day,
        assignment.time_slot_id,
    )
    return (
        candidate_key in state.group_student_occupancy
        or teacher_key in state.group_teacher_occupancy
    )


def _assignment_violation(
    code: DiagnosticCode,
    assignment: ScheduledAssignment,
) -> ResultViolation:
    return _violation(
        code,
        lesson_request_id=assignment.lesson_request_id,
        session_index=assignment.session_index,
        day=assignment.day,
        time_slot_id=assignment.time_slot_id,
        teacher_id=assignment.teacher_id,
    )


def _violation(
    code: DiagnosticCode,
    *,
    lesson_request_id: int | None = None,
    session_index: int | None = None,
    day: date | None = None,
    time_slot_id: int | None = None,
    teacher_id: int | None = None,
    details: tuple[tuple[str, str], ...] = (),
) -> ResultViolation:
    return ResultViolation(
        code=code,
        message=diagnostic_message(code),
        lesson_request_id=lesson_request_id,
        session_index=session_index,
        day=day,
        time_slot_id=time_slot_id,
        teacher_id=teacher_id,
        details=details,
    )


def _violation_sort_key(
    item: ResultViolation,
) -> tuple[int, int, int, str, int, int, tuple[tuple[str, str], ...]]:
    return (
        _ORDER_INDEX.get(item.code, len(_ORDER_INDEX)),
        item.lesson_request_id if item.lesson_request_id is not None else -1,
        item.session_index if item.session_index is not None else -1,
        item.day.isoformat() if item.day is not None else "",
        item.time_slot_id if item.time_slot_id is not None else -1,
        item.teacher_id if item.teacher_id is not None else -1,
        item.details,
    )


__all__ = [
    "InvalidOptimizationResultError",
    "ResultValidationReport",
    "ResultViolation",
    "require_valid_optimization_result",
    "validate_optimization_result",
]
