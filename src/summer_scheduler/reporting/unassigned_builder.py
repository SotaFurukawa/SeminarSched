"""現在のAssignmentを基準に未配置理由と解決候補を再構築する。"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from summer_scheduler.optimization.diagnostics import diagnose_unassigned_lessons
from summer_scheduler.optimization.dto import (
    CandidateData,
    CandidateGenerationResult,
    DiagnosticCode,
    ObjectiveBreakdown,
    OptimizationInput,
    OptimizationResult,
    ScheduledAssignment,
    UnassignedLesson,
)
from summer_scheduler.optimization.result_validation import validate_optimization_result
from summer_scheduler.reporting.data import OutputSnapshot, UnassignedRecord

_SUGGESTIONS = {
    DiagnosticCode.PRIORITY_5_COMMON_SLOT_UNAVAILABLE.value: (
        "通常担当講師と生徒の共通可能枠を確認"
    ),
    DiagnosticCode.PRIORITY_5_TEACHER_REQUIRED.value: "通常担当講師の出勤希望を確認",
    DiagnosticCode.STUDENT_UNAVAILABLE.value: "生徒の受講可能日時を確認",
    DiagnosticCode.TEACHER_UNAVAILABLE.value: "講師の出勤可能日時を確認",
    DiagnosticCode.TEACHER_UNQUALIFIED.value: "指導可能講師の登録を確認",
    DiagnosticCode.GROUP_LESSON_CONFLICT.value: "集団授業と重ならない日時を確認",
    DiagnosticCode.ONE_TO_ONE_CAPACITY.value: "1対1専用の講師枠を確保",
    DiagnosticCode.TEACHER_CAPACITY_EXCEEDED.value: "講師の定員に空きがある枠を確認",
    DiagnosticCode.STUDENT_GAP_NOT_ALLOWED.value: "生徒の連続するコマへ移動を検討",
    DiagnosticCode.TEACHER_GAP_NOT_ALLOWED.value: "講師の連続するコマへ移動を検討",
    DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT.value: "生徒の別日への分散を検討",
    DiagnosticCode.GLOBAL_COMPETITION.value: "他授業の日時・講師変更を検討",
}


def build_unassigned_records(
    snapshot: OutputSnapshot,
    optimization_input: OptimizationInput,
    generation: CandidateGenerationResult,
) -> tuple[UnassignedRecord, ...]:
    """古いOptimizationRunではなく、現在の配置に対して診断する。"""
    current_result = build_current_result(snapshot, optimization_input, generation)
    assigned_counts = Counter(row.lesson_request_id for row in snapshot.assignments)
    diagnosed = diagnose_unassigned_lessons(
        optimization_input,
        generation,
        current_result,
    )
    diagnosed_by_request: dict[int, list[UnassignedLesson]] = {}
    for row in diagnosed:
        diagnosed_by_request.setdefault(row.lesson_request_id, []).append(row)
    teachers = {row.id: row.name for row in snapshot.teachers}
    slots = {row.id: row.code for row in snapshot.slots}
    result: list[UnassignedRecord] = []
    for request in snapshot.lesson_requests:
        missing = max(0, request.required_sessions - assigned_counts[request.id])
        if missing == 0:
            continue
        diagnosed_rows = diagnosed_by_request.get(request.id, [])
        reasons = tuple(reason for session in diagnosed_rows for reason in session.reasons)
        reason_codes = tuple(dict.fromkeys(reason.code.value for reason in reasons))
        main_reason = reasons[0].message if reasons else "現在の時間割では未配置です"
        candidates = tuple(
            candidate
            for session in diagnosed_rows
            for candidate in generation.candidates_for(
                session.lesson_request_id,
                session.session_index,
            )
        )
        feasible_candidates = _feasible_candidates(
            candidates,
            optimization_input=optimization_input,
            generation=generation,
            current_result=current_result,
        )
        candidate_texts = tuple(
            dict.fromkeys(
                f"{candidate.day:%Y/%m/%d} {slots.get(candidate.time_slot_id, '?')} "
                f"{teachers.get(candidate.teacher_id, '講師未登録')}（単独配置可）"
                for candidate in feasible_candidates
            )
        )
        if not candidate_texts:
            candidate_texts = tuple(
                dict.fromkeys(_SUGGESTIONS[code] for code in reason_codes if code in _SUGGESTIONS)
            )
        result.append(
            UnassignedRecord(
                lesson_request_id=request.id,
                student_id=request.student_id,
                subject_id=request.subject_id,
                required_sessions=request.required_sessions,
                placed_sessions=assigned_counts[request.id],
                missing_sessions=missing,
                main_reason=main_reason,
                reason_codes=reason_codes,
                resolution_candidates=candidate_texts[:3],
                candidate_count=len(feasible_candidates),
                priority=request.regular_teacher_priority,
                regular_teacher_id_optional=request.regular_teacher_id_optional,
                one_to_one_required=request.one_to_one_required,
                note=request.note,
            )
        )
    return tuple(result)


def _feasible_candidates(
    candidates: tuple[CandidateData, ...],
    *,
    optimization_input: OptimizationInput,
    generation: CandidateGenerationResult,
    current_result: OptimizationResult,
) -> tuple[CandidateData, ...]:
    """現在の配置を変えず、対象1授業を追加してもハード制約を満たす候補を返す。"""
    feasible: list[CandidateData] = []
    seen: set[tuple[object, int, int, int, int]] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.day,
            item.time_slot_id,
            item.teacher_id,
            item.lesson_request_id,
            item.session_index,
        ),
    ):
        key = (
            candidate.day,
            candidate.time_slot_id,
            candidate.teacher_id,
            candidate.lesson_request_id,
            candidate.session_index,
        )
        if key in seen:
            continue
        seen.add(key)
        trial = replace(
            current_result,
            assignments=(
                *current_result.assignments,
                ScheduledAssignment(
                    lesson_request_id=candidate.lesson_request_id,
                    session_index=candidate.session_index,
                    student_id=candidate.student_id,
                    subject_id=candidate.subject_id,
                    teacher_id=candidate.teacher_id,
                    day=candidate.day,
                    time_slot_id=candidate.time_slot_id,
                    is_locked=False,
                ),
            ),
            unassigned_lessons=tuple(
                row
                for row in current_result.unassigned_lessons
                if (
                    row.lesson_request_id,
                    row.session_index,
                )
                != candidate.session_key
            ),
        )
        if validate_optimization_result(
            optimization_input,
            generation,
            trial,
        ).is_valid:
            feasible.append(candidate)
            if len(feasible) == 3:
                break
    return tuple(feasible)


def build_current_result(
    snapshot: OutputSnapshot,
    optimization_input: OptimizationInput,
    generation: CandidateGenerationResult,
) -> OptimizationResult:
    """独立validatorへ渡せる、現在DBの全session partitionを作る。"""
    optimization_requests = {row.id: row for row in optimization_input.lesson_requests}
    assignments = tuple(
        ScheduledAssignment(
            lesson_request_id=row.lesson_request_id,
            session_index=row.session_index,
            student_id=optimization_requests[row.lesson_request_id].student_id,
            subject_id=optimization_requests[row.lesson_request_id].subject_id,
            teacher_id=row.teacher_id,
            day=row.day,
            time_slot_id=row.time_slot_id,
            is_locked=row.is_locked,
        )
        for row in snapshot.assignments
        if row.lesson_request_id in optimization_requests
    )
    assigned_keys = {(row.lesson_request_id, row.session_index) for row in snapshot.assignments}
    unassigned = tuple(
        UnassignedLesson(
            lesson_request_id=session.lesson_request_id,
            session_index=session.session_index,
            student_id=session.student_id,
            subject_id=session.subject_id,
            reasons=(),
        )
        for session in generation.sessions
        if session.key not in assigned_keys
    )
    return OptimizationResult(
        solver_status="FEASIBLE",
        assignments=assignments,
        unassigned_lessons=unassigned,
        objective_breakdown=ObjectiveBreakdown(unassigned_count=len(unassigned)),
        elapsed_seconds=0.0,
    )


__all__ = ["build_current_result", "build_unassigned_records"]
