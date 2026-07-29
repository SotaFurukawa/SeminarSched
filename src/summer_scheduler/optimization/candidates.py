"""疎な割当候補と、候補除外理由を生成するsolver非依存処理。"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from summer_scheduler.domain.time_ranges import InvalidTimeRangeError, time_ranges_overlap
from summer_scheduler.optimization.diagnostics import make_diagnostic_reason
from summer_scheduler.optimization.dto import (
    AvailabilityOwner,
    CandidateData,
    CandidateGenerationResult,
    DiagnosticCode,
    DiagnosticReason,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    LessonSessionData,
    OptimizationInput,
    SessionCandidateDiagnostics,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
)
from summer_scheduler.optimization.sessions import SessionExpansionError, expand_sessions


@dataclass(frozen=True, slots=True)
class _Indexes:
    students: Mapping[int, StudentData]
    teachers: Mapping[int, TeacherData]
    subjects: Mapping[int, SubjectData]
    requests: Mapping[int, LessonRequestData]
    slots: Mapping[int, TimeSlotData]
    availability: Mapping[tuple[AvailabilityOwner, int, date, int], int]
    locked_by_session: Mapping[tuple[int, int], ExistingAssignmentData]
    locked_assignments: tuple[ExistingAssignmentData, ...]


class CandidateGenerationCancelled(RuntimeError):
    """候補生成が利用者の要求で安全に中止された。"""


def generate_candidates(
    data: OptimizationInput,
    *,
    is_cancelled: Callable[[], bool] | None = None,
) -> CandidateGenerationResult:
    """入力の明白な不適合を除外し、solverへ渡す疎な候補集合を返す。

    この段階で扱うのは単一候補だけで判断できる条件と固定授業の明白な
    占有である。連続数・空きコマ・最終的な1対2定員はsolver制約で扱う。
    """
    _raise_if_cancelled(is_cancelled)
    try:
        sessions = expand_sessions(data.lesson_requests)
    except SessionExpansionError as exc:
        return CandidateGenerationResult(
            sessions=(),
            candidates=(),
            diagnostics=(),
            input_diagnostics=(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(("error", str(exc)),),
                ),
            ),
        )

    input_diagnostics = _validate_input(data)
    if input_diagnostics:
        session_diagnostics = tuple(
            SessionCandidateDiagnostics(
                lesson_request_id=session.lesson_request_id,
                session_index=session.session_index,
                candidate_count=0,
                reasons=(
                    _reason(DiagnosticCode.INVALID_INPUT),
                    _reason(DiagnosticCode.NO_CANDIDATE),
                ),
            )
            for session in sessions
        )
        return CandidateGenerationResult(
            sessions=sessions,
            candidates=(),
            diagnostics=session_diagnostics,
            input_diagnostics=input_diagnostics,
        )

    indexes = _build_indexes(data)
    candidate_dates = _candidate_dates(data)
    candidates: list[CandidateData] = []
    diagnostics: list[SessionCandidateDiagnostics] = []

    for session in sessions:
        _raise_if_cancelled(is_cancelled)
        session_candidates, session_diagnostic = _generate_session_candidates(
            data=data,
            indexes=indexes,
            session=session,
            candidate_dates=candidate_dates,
            is_cancelled=is_cancelled,
        )
        candidates.extend(session_candidates)
        diagnostics.append(session_diagnostic)

    candidates.sort(
        key=lambda item: (
            item.lesson_request_id,
            item.session_index,
            item.day,
            indexes.slots[item.time_slot_id].sort_order,
            item.time_slot_id,
            item.teacher_id,
        )
    )
    return CandidateGenerationResult(
        sessions=sessions,
        candidates=tuple(candidates),
        diagnostics=tuple(diagnostics),
    )


def _generate_session_candidates(
    *,
    data: OptimizationInput,
    indexes: _Indexes,
    session: LessonSessionData,
    candidate_dates: tuple[date, ...],
    is_cancelled: Callable[[], bool] | None,
) -> tuple[list[CandidateData], SessionCandidateDiagnostics]:
    request = indexes.requests[session.lesson_request_id]
    immediate_reason = _request_master_reason(request, indexes)
    if immediate_reason is not None:
        immediate_reasons = (immediate_reason, _reason(DiagnosticCode.NO_CANDIDATE))
        return [], _session_diagnostics(session, 0, immediate_reasons)

    exclusion_counts: Counter[DiagnosticCode] = Counter()
    candidates: list[CandidateData] = []
    open_dates = frozenset(data.open_dates)

    for day in candidate_dates:
        _raise_if_cancelled(is_cancelled)
        for slot in data.time_slots:
            for teacher in data.teachers:
                exclusion = _candidate_exclusion(
                    request=request,
                    session=session,
                    teacher=teacher,
                    day=day,
                    slot=slot,
                    open_dates=open_dates,
                    group_blocks=data.group_blocks,
                    indexes=indexes,
                )
                if exclusion is not None:
                    exclusion_counts[exclusion] += 1
                    continue

                student_level = indexes.availability[("student", request.student_id, day, slot.id)]
                teacher_level = indexes.availability[("teacher", teacher.id, day, slot.id)]
                candidates.append(
                    CandidateData(
                        lesson_request_id=request.id,
                        session_index=session.session_index,
                        student_id=request.student_id,
                        subject_id=request.subject_id,
                        teacher_id=teacher.id,
                        day=day,
                        time_slot_id=slot.id,
                        student_availability_level=student_level,
                        teacher_availability_level=teacher_level,
                    )
                )

    reasons: tuple[DiagnosticReason, ...] = tuple(
        _reason(code, count)
        for code, count in sorted(exclusion_counts.items(), key=lambda item: item[0].value)
    )
    if not candidates:
        if request.regular_teacher_priority == 5:
            reasons += (_reason(DiagnosticCode.PRIORITY_5_COMMON_SLOT_UNAVAILABLE),)
        reasons += (_reason(DiagnosticCode.NO_CANDIDATE),)
    return candidates, _session_diagnostics(session, len(candidates), reasons)


def _candidate_exclusion(
    *,
    request: LessonRequestData,
    session: LessonSessionData,
    teacher: TeacherData,
    day: date,
    slot: TimeSlotData,
    open_dates: frozenset[date],
    group_blocks: tuple[GroupBlockData, ...],
    indexes: _Indexes,
) -> DiagnosticCode | None:
    if day not in open_dates:
        return DiagnosticCode.CLOSED_DATE
    if not slot.enabled:
        return DiagnosticCode.DISABLED_TIME_SLOT
    if indexes.availability.get(("student", request.student_id, day, slot.id), 0) == 0:
        return DiagnosticCode.STUDENT_UNAVAILABLE
    if not teacher.active:
        return DiagnosticCode.INACTIVE_TEACHER
    if request.subject_id not in teacher.qualified_subject_ids:
        return DiagnosticCode.TEACHER_UNQUALIFIED
    if request.regular_teacher_priority == 5 and teacher.id != request.regular_teacher_id:
        return DiagnosticCode.PRIORITY_5_TEACHER_REQUIRED
    if indexes.availability.get(("teacher", teacher.id, day, slot.id), 0) == 0:
        return DiagnosticCode.TEACHER_UNAVAILABLE
    if _has_group_conflict(
        request.student_id,
        teacher.id,
        day,
        slot,
        group_blocks,
    ):
        return DiagnosticCode.GROUP_LESSON_CONFLICT
    return _locked_conflict(request, session, teacher.id, day, slot.id, indexes)


def _request_master_reason(
    request: LessonRequestData,
    indexes: _Indexes,
) -> DiagnosticReason | None:
    student = indexes.students.get(request.student_id)
    if student is None:
        return _reason(
            DiagnosticCode.MISSING_STUDENT,
            details=(("student_id", str(request.student_id)),),
        )
    if not student.active:
        return _reason(DiagnosticCode.INACTIVE_STUDENT)

    subject = indexes.subjects.get(request.subject_id)
    if subject is None:
        return _reason(
            DiagnosticCode.MISSING_SUBJECT,
            details=(("subject_id", str(request.subject_id)),),
        )
    if not subject.active:
        return _reason(DiagnosticCode.INACTIVE_SUBJECT)

    if not 1 <= request.regular_teacher_priority <= 5:
        return _reason(
            DiagnosticCode.INVALID_MASTER,
            details=(
                ("field", "regular_teacher_priority"),
                ("value", str(request.regular_teacher_priority)),
            ),
        )
    if request.regular_teacher_priority == 5:
        if request.regular_teacher_id is None:
            return _reason(
                DiagnosticCode.MISSING_TEACHER,
                details=(("field", "regular_teacher_id"),),
            )
        if request.regular_teacher_id not in indexes.teachers:
            return _reason(
                DiagnosticCode.MISSING_TEACHER,
                details=(("teacher_id", str(request.regular_teacher_id)),),
            )
    return None


def _has_group_conflict(
    student_id: int,
    teacher_id: int,
    day: date,
    slot: TimeSlotData,
    group_blocks: tuple[GroupBlockData, ...],
) -> bool:
    for block in group_blocks:
        if block.day != day:
            continue
        if student_id not in block.student_ids and teacher_id != block.teacher_id:
            continue
        if time_ranges_overlap(
            slot.start_time,
            slot.end_time,
            block.start_time,
            block.end_time,
        ):
            return True
    return False


def _locked_conflict(
    request: LessonRequestData,
    session: LessonSessionData,
    teacher_id: int,
    day: date,
    slot_id: int,
    indexes: _Indexes,
) -> DiagnosticCode | None:
    locked_for_session = indexes.locked_by_session.get(session.key)
    if locked_for_session is not None:
        target = (
            locked_for_session.day,
            locked_for_session.time_slot_id,
            locked_for_session.teacher_id,
        )
        if (day, slot_id, teacher_id) != target:
            return DiagnosticCode.LOCKED_ASSIGNMENT_CONFLICT

    teacher_occupants = 0
    for locked in indexes.locked_assignments:
        if (locked.lesson_request_id, locked.session_index) == session.key:
            continue
        locked_request = indexes.requests[locked.lesson_request_id]
        if locked.day == day and locked.time_slot_id == slot_id:
            if locked_request.student_id == request.student_id:
                return DiagnosticCode.LOCKED_ASSIGNMENT_CONFLICT
            if locked.teacher_id == teacher_id:
                teacher_occupants += 1
                if locked_request.one_to_one_required or request.one_to_one_required:
                    return DiagnosticCode.ONE_TO_ONE_CAPACITY
    if teacher_occupants >= 2:
        return DiagnosticCode.LOCKED_ASSIGNMENT_CONFLICT
    return None


def _candidate_dates(data: OptimizationInput) -> tuple[date, ...]:
    days = set(data.open_dates)
    days.update(item.day for item in data.availabilities)
    days.update(item.day for item in data.existing_assignments if item.is_locked)
    return tuple(sorted(days))


def _build_indexes(data: OptimizationInput) -> _Indexes:
    availability = {
        (item.owner_type, item.owner_id, item.day, item.time_slot_id): item.level
        for item in data.availabilities
    }
    locked = tuple(item for item in data.existing_assignments if item.is_locked)
    return _Indexes(
        students={item.id: item for item in data.students},
        teachers={item.id: item for item in data.teachers},
        subjects={item.id: item for item in data.subjects},
        requests={item.id: item for item in data.lesson_requests},
        slots={item.id: item for item in data.time_slots},
        availability=availability,
        locked_by_session={(item.lesson_request_id, item.session_index): item for item in locked},
        locked_assignments=locked,
    )


def _validate_input(data: OptimizationInput) -> tuple[DiagnosticReason, ...]:
    errors: list[DiagnosticReason] = []
    _validate_unique_ids(errors, "student", (item.id for item in data.students))
    _validate_unique_ids(errors, "teacher", (item.id for item in data.teachers))
    _validate_unique_ids(errors, "subject", (item.id for item in data.subjects))
    _validate_unique_ids(errors, "time_slot", (item.id for item in data.time_slots))
    _validate_unique_ids(
        errors,
        "lesson_request",
        (item.id for item in data.lesson_requests),
    )
    _validate_unique_ids(errors, "group_block", (item.id for item in data.group_blocks))
    _validate_unique_ids(
        errors,
        "existing_assignment",
        (item.id for item in data.existing_assignments),
    )

    duplicate_orders = _duplicates(item.sort_order for item in data.time_slots)
    if duplicate_orders:
        errors.append(
            _reason(
                DiagnosticCode.INVALID_MASTER,
                details=(
                    ("entity", "time_slot"),
                    ("duplicate_sort_orders", _csv(duplicate_orders)),
                ),
            )
        )
    for slot in data.time_slots:
        if slot.sort_order <= 0 or slot.start_time >= slot.end_time:
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_MASTER,
                    details=(("entity", "time_slot"), ("id", str(slot.id))),
                )
            )

    availability_keys: list[tuple[AvailabilityOwner, int, date, int]] = []
    for availability in data.availabilities:
        availability_keys.append(
            (
                availability.owner_type,
                availability.owner_id,
                availability.day,
                availability.time_slot_id,
            )
        )
        if availability.level not in (0, 1, 2):
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(
                        ("entity", "availability"),
                        ("level", str(availability.level)),
                    ),
                )
            )
    if duplicate_availability := _duplicates(availability_keys):
        errors.append(
            _reason(
                DiagnosticCode.INVALID_INPUT,
                details=(
                    ("entity", "availability"),
                    ("duplicate_count", str(len(duplicate_availability))),
                ),
            )
        )

    request_by_id = {request.id: request for request in data.lesson_requests}
    student_ids = {student.id for student in data.students}
    slot_ids = {slot.id for slot in data.time_slots}
    teacher_ids = {teacher.id for teacher in data.teachers}
    subject_ids = {subject.id for subject in data.subjects}
    assignment_keys: list[tuple[int, int]] = []
    for assignment in data.existing_assignments:
        request = request_by_id.get(assignment.lesson_request_id)
        if (
            request is None
            or assignment.time_slot_id not in slot_ids
            or assignment.teacher_id not in teacher_ids
            or assignment.session_index <= 0
            or (request is not None and assignment.session_index > request.required_sessions)
        ):
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(("entity", "locked_assignment"), ("id", str(assignment.id))),
                )
            )
        assignment_keys.append((assignment.lesson_request_id, assignment.session_index))
    if duplicate_assignments := _duplicates(assignment_keys):
        errors.append(
            _reason(
                DiagnosticCode.INVALID_INPUT,
                details=(
                    ("entity", "existing_assignment"),
                    ("duplicate_count", str(len(duplicate_assignments))),
                ),
            )
        )

    for block in data.group_blocks:
        try:
            time_ranges_overlap(
                block.start_time,
                block.end_time,
                block.start_time,
                block.end_time,
            )
        except InvalidTimeRangeError:
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(("entity", "group_block"), ("id", str(block.id))),
                )
            )
        if block.teacher_id is not None and block.teacher_id not in teacher_ids:
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(("entity", "group_teacher"), ("id", str(block.teacher_id))),
                )
            )
        missing_participants = sorted(block.student_ids - student_ids)
        if missing_participants:
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(
                        ("entity", "group_student"),
                        ("missing_ids", _csv(missing_participants)),
                    ),
                )
            )

    for request in data.lesson_requests:
        if request.student_id not in student_ids or request.subject_id not in subject_ids:
            continue
        if request.regular_teacher_id is not None and request.regular_teacher_id not in teacher_ids:
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(
                        ("entity", "lesson_request"),
                        ("id", str(request.id)),
                        ("field", "regular_teacher_id"),
                    ),
                )
            )
        missing_preferred = sorted(
            {
                teacher_id
                for teacher_id in request.preferred_teacher_ids
                if teacher_id is not None and teacher_id not in teacher_ids
            }
        )
        if missing_preferred:
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(
                        ("entity", "lesson_request"),
                        ("id", str(request.id)),
                        ("missing_teacher_ids", _csv(missing_preferred)),
                    ),
                )
            )
        if (
            request.max_consecutive_slots_override is not None
            and request.max_consecutive_slots_override <= 0
        ):
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_INPUT,
                    details=(
                        ("entity", "lesson_request"),
                        ("id", str(request.id)),
                        ("field", "max_consecutive_slots_override"),
                    ),
                )
            )

    for student in data.students:
        if student.default_max_consecutive_slots <= 0:
            errors.append(
                _reason(
                    DiagnosticCode.INVALID_MASTER,
                    details=(
                        ("entity", "student"),
                        ("id", str(student.id)),
                        ("field", "default_max_consecutive_slots"),
                    ),
                )
            )

    if len(set(data.open_dates)) != len(data.open_dates):
        errors.append(
            _reason(
                DiagnosticCode.INVALID_INPUT,
                details=(("entity", "open_date"), ("reason", "duplicate")),
            )
        )
    if not math.isfinite(data.settings.time_limit_seconds) or data.settings.time_limit_seconds <= 0:
        errors.append(
            _reason(
                DiagnosticCode.INVALID_INPUT,
                details=(("field", "time_limit_seconds"),),
            )
        )
    if data.settings.num_search_workers <= 0:
        errors.append(
            _reason(
                DiagnosticCode.INVALID_INPUT,
                details=(("field", "num_search_workers"),),
            )
        )
    if any(
        weight < 0
        for weight in (
            *data.settings.regular_teacher_priority_weights,
            *data.settings.preferred_teacher_rank_weights,
            data.settings.student_preferred_time_weight,
            data.settings.teacher_preferred_time_weight,
            data.settings.preserve_existing_assignment_weight,
            data.settings.optional_balance_weight,
        )
    ):
        errors.append(
            _reason(
                DiagnosticCode.INVALID_INPUT,
                details=(("field", "optimization_weight"),),
            )
        )
    return tuple(errors)


def _validate_unique_ids(
    errors: list[DiagnosticReason],
    entity: str,
    ids: Iterable[int],
) -> None:
    if duplicates := _duplicates(ids):
        errors.append(
            _reason(
                DiagnosticCode.INVALID_MASTER,
                details=(("entity", entity), ("duplicate_ids", _csv(duplicates))),
            )
        )


def _duplicates[T](values: Iterable[T]) -> set[T]:
    seen: set[T] = set()
    duplicates: set[T] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _csv(values: Iterable[object]) -> str:
    return ",".join(str(value) for value in sorted(values, key=str))


def _reason(
    code: DiagnosticCode,
    excluded_candidate_count: int = 0,
    *,
    details: tuple[tuple[str, str], ...] = (),
) -> DiagnosticReason:
    return make_diagnostic_reason(
        code,
        excluded_candidate_count=excluded_candidate_count,
        details=details,
    )


def _session_diagnostics(
    session: LessonSessionData,
    candidate_count: int,
    reasons: tuple[DiagnosticReason, ...],
) -> SessionCandidateDiagnostics:
    return SessionCandidateDiagnostics(
        lesson_request_id=session.lesson_request_id,
        session_index=session.session_index,
        candidate_count=candidate_count,
        reasons=reasons,
    )


def _raise_if_cancelled(is_cancelled: Callable[[], bool] | None) -> None:
    if is_cancelled is not None and is_cancelled():
        raise CandidateGenerationCancelled


__all__ = ["CandidateGenerationCancelled", "generate_candidates"]
