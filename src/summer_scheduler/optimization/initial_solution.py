"""CP-SATへ渡す、安全で決定論的な初期実行可能解を構築する。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from summer_scheduler.optimization.dto import (
    CandidateData,
    CandidateGenerationResult,
    ExistingAssignmentData,
    LessonRequestData,
    ObjectiveBreakdown,
    OptimizationInput,
    OptimizationResult,
    ScheduledAssignment,
    TeacherData,
    UnassignedLesson,
)
from summer_scheduler.optimization.objectives import teacher_preference_penalty
from summer_scheduler.optimization.result_validation import (
    ResultValidationReport,
    validate_optimization_result,
)
from summer_scheduler.optimization.schedule_analysis import (
    ScheduleState,
    build_schedule_state,
    candidate_group_conflict,
    occupied_slots_are_contiguous,
    student_consecutive_limit_is_violated,
    student_day_requires_no_gap,
    student_occupied_slots,
    teacher_occupied_slots,
)

type SessionKey = tuple[int, int]


@dataclass(frozen=True, slots=True)
class InitialSolution:
    """検証済み初期解の候補選択と、残りの未配置セッション。"""

    selected_candidates: tuple[CandidateData, ...]
    unassigned_session_keys: tuple[SessionKey, ...]


class InitialSolutionCancelled(RuntimeError):
    """初期解構築が利用者または全体deadlineによって中止された。"""


def build_initial_solution(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    *,
    is_cancelled: Callable[[], bool] | None = None,
) -> InitialSolution | None:
    """貪欲に候補を選び、独立検証済みの初期実行可能解を返す。

    ロック済み授業を最初に固定し、候補の少ないセッションから処理する。各追加は
    solverと共有しないスケジュール解析で全ハード制約を確認する。完成した集合は独立
    結果検証器を通過した場合だけ返す。入力自体が不正な場合や、ロック済み授業だけの
    基底が実行可能でない場合は、不正なhintを返さず ``None`` を返す。
    """
    _raise_if_cancelled(is_cancelled)
    candidates_by_session: dict[SessionKey, list[CandidateData]] = defaultdict(list)
    for index, candidate in enumerate(generation.candidates):
        if index % 256 == 0:
            _raise_if_cancelled(is_cancelled)
        candidates_by_session[candidate.session_key].append(candidate)

    locked_by_session = _locked_assignments_by_session(data)
    if locked_by_session is None:
        return None

    selected: list[CandidateData] = []
    for key, locked in sorted(locked_by_session.items()):
        matches = [
            candidate
            for candidate in candidates_by_session.get(key, ())
            if (
                candidate.day == locked.day
                and candidate.time_slot_id == locked.time_slot_id
                and candidate.teacher_id == locked.teacher_id
            )
        ]
        if len(matches) != 1:
            return None
        selected.append(matches[0])

    all_session_keys = tuple(sorted(session.key for session in generation.sessions))
    unassigned = set(all_session_keys) - set(locked_by_session)
    solution = _make_solution(selected, unassigned)
    if not validate_initial_solution(data, generation, solution).is_valid:
        return None

    state = build_schedule_state(
        data,
        _scheduled_assignments(data, solution.selected_candidates),
    )
    requests = {request.id: request for request in data.lesson_requests}
    teachers = {teacher.id: teacher for teacher in data.teachers}
    slot_positions = {
        slot.id: position
        for position, slot in enumerate(
            sorted(data.time_slots, key=lambda item: (item.sort_order, item.id))
        )
    }
    existing_positions = {
        (
            item.lesson_request_id,
            item.session_index,
            item.day,
            item.time_slot_id,
            item.teacher_id,
        )
        for item in data.existing_assignments
        if not item.is_locked
    }

    sessions = sorted(
        (session for session in generation.sessions if session.key not in locked_by_session),
        key=lambda session: (
            len(candidates_by_session.get(session.key, ())),
            0
            if requests.get(session.lesson_request_id) is not None
            and requests[session.lesson_request_id].regular_teacher_priority == 5
            else 1,
            0 if session.one_to_one_required else 1,
            session.lesson_request_id,
            session.session_index,
        ),
    )
    for session in sessions:
        _raise_if_cancelled(is_cancelled)
        session_candidates = sorted(
            candidates_by_session.get(session.key, ()),
            key=lambda candidate: _candidate_preference_key(
                data,
                state,
                candidate,
                requests,
                slot_positions,
                existing_positions,
            ),
        )
        for index, candidate in enumerate(session_candidates):
            if index % 128 == 0:
                _raise_if_cancelled(is_cancelled)
            if not _candidate_is_feasible(state, candidate, teachers):
                continue

            selected.append(candidate)
            unassigned.remove(session.key)
            state = build_schedule_state(
                data,
                _scheduled_assignments(data, tuple(selected)),
            )
            break

    final_solution = _make_solution(selected, unassigned)
    if not validate_initial_solution(data, generation, final_solution).is_valid:
        return None
    return final_solution


def validate_initial_solution(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    solution: InitialSolution,
) -> ResultValidationReport:
    """初期解を通常のOptimizationResultへ変換し、独立検証器で検査する。"""
    result = OptimizationResult(
        solver_status="FEASIBLE",
        assignments=_scheduled_assignments(data, solution.selected_candidates),
        unassigned_lessons=_unassigned_lessons(data, solution.unassigned_session_keys),
        objective_breakdown=ObjectiveBreakdown(
            unassigned_count=len(solution.unassigned_session_keys)
        ),
        elapsed_seconds=0.0,
    )
    return validate_optimization_result(data, generation, result)


def _candidate_is_feasible(
    state: ScheduleState,
    candidate: CandidateData,
    teachers: dict[int, TeacherData],
) -> bool:
    request = state.requests.get(candidate.lesson_request_id)
    student = state.students.get(candidate.student_id)
    teacher = teachers.get(candidate.teacher_id)
    if (
        request is None
        or student is None
        or teacher is None
        or candidate.student_id != request.student_id
        or candidate.subject_id != request.subject_id
        or candidate.time_slot_id not in state.slot_by_id
        or candidate.session_key in state.assignments_by_session
        or candidate_group_conflict(state, candidate)
    ):
        return False

    student_key = (candidate.student_id, candidate.day, candidate.time_slot_id)
    if state.student_occupancy.get(student_key):
        return False

    teacher_key = (candidate.teacher_id, candidate.day, candidate.time_slot_id)
    concurrent = state.teacher_occupancy.get(teacher_key, ())
    if len(concurrent) >= 2:
        return False
    if concurrent and (
        request.one_to_one_required
        or any(
            state.requests.get(item.lesson_request_id) is None
            or state.requests[item.lesson_request_id].one_to_one_required
            for item in concurrent
        )
    ):
        return False

    if student_day_requires_no_gap(
        state,
        candidate.student_id,
        candidate.day,
        additional_request=request,
    ) and not occupied_slots_are_contiguous(
        state,
        student_occupied_slots(
            state,
            candidate.student_id,
            candidate.day,
            additional_slot_id=candidate.time_slot_id,
        ),
    ):
        return False

    if not teacher.allow_gap and not occupied_slots_are_contiguous(
        state,
        teacher_occupied_slots(
            state,
            candidate.teacher_id,
            candidate.day,
            additional_slot_id=candidate.time_slot_id,
        ),
    ):
        return False

    return not student_consecutive_limit_is_violated(
        state,
        candidate.student_id,
        candidate.day,
        additional_candidate=candidate,
    )


def _candidate_preference_key(
    data: OptimizationInput,
    state: ScheduleState,
    candidate: CandidateData,
    requests: dict[int, LessonRequestData],
    slot_positions: dict[int, int],
    existing_positions: set[tuple[int, int, date, int, int]],
) -> tuple[int, int, int, int, date, int, int, int]:
    request = requests[candidate.lesson_request_id]
    availability_score = (
        data.settings.student_preferred_time_weight
        if candidate.student_availability_level == 2
        else 0
    ) + (
        data.settings.teacher_preferred_time_weight
        if candidate.teacher_availability_level == 2
        else 0
    )
    identity = (
        candidate.lesson_request_id,
        candidate.session_index,
        candidate.day,
        candidate.time_slot_id,
        candidate.teacher_id,
    )
    teacher_slot_already_active = bool(
        state.teacher_occupancy.get((candidate.teacher_id, candidate.day, candidate.time_slot_id))
    )
    return (
        teacher_preference_penalty(request, candidate.teacher_id, data.settings),
        0 if teacher_slot_already_active else 1,
        -availability_score,
        0 if identity in existing_positions else 1,
        candidate.day,
        slot_positions.get(candidate.time_slot_id, len(slot_positions)),
        candidate.time_slot_id,
        candidate.teacher_id,
    )


def _locked_assignments_by_session(
    data: OptimizationInput,
) -> dict[SessionKey, ExistingAssignmentData] | None:
    locked: dict[SessionKey, ExistingAssignmentData] = {}
    for item in data.existing_assignments:
        if not item.is_locked:
            continue
        key = (item.lesson_request_id, item.session_index)
        if key in locked:
            return None
        locked[key] = item
    return locked


def _scheduled_assignments(
    data: OptimizationInput,
    selected: tuple[CandidateData, ...],
) -> tuple[ScheduledAssignment, ...]:
    locked_keys = {
        (item.lesson_request_id, item.session_index)
        for item in data.existing_assignments
        if item.is_locked
    }
    return tuple(
        ScheduledAssignment(
            lesson_request_id=item.lesson_request_id,
            session_index=item.session_index,
            student_id=item.student_id,
            subject_id=item.subject_id,
            teacher_id=item.teacher_id,
            day=item.day,
            time_slot_id=item.time_slot_id,
            is_locked=item.session_key in locked_keys,
        )
        for item in selected
    )


def _unassigned_lessons(
    data: OptimizationInput,
    keys: tuple[SessionKey, ...],
) -> tuple[UnassignedLesson, ...]:
    requests = {request.id: request for request in data.lesson_requests}
    lessons: list[UnassignedLesson] = []
    for request_id, session_index in keys:
        request = requests.get(request_id)
        lessons.append(
            UnassignedLesson(
                lesson_request_id=request_id,
                session_index=session_index,
                student_id=request.student_id if request is not None else -1,
                subject_id=request.subject_id if request is not None else -1,
                reasons=(),
            )
        )
    return tuple(lessons)


def _make_solution(
    selected: list[CandidateData] | tuple[CandidateData, ...],
    unassigned: set[SessionKey],
) -> InitialSolution:
    return InitialSolution(
        selected_candidates=tuple(
            sorted(
                selected,
                key=lambda item: (
                    item.lesson_request_id,
                    item.session_index,
                    item.day,
                    item.time_slot_id,
                    item.teacher_id,
                ),
            )
        ),
        unassigned_session_keys=tuple(sorted(unassigned)),
    )


def _raise_if_cancelled(is_cancelled: Callable[[], bool] | None) -> None:
    if is_cancelled is not None and is_cancelled():
        raise InitialSolutionCancelled


__all__ = [
    "InitialSolution",
    "InitialSolutionCancelled",
    "SessionKey",
    "build_initial_solution",
    "validate_initial_solution",
]
