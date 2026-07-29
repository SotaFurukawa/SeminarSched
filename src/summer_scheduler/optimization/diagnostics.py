"""候補除外と最終解を組み合わせた再現可能な未配置診断。"""

from __future__ import annotations

from collections import Counter

from summer_scheduler.optimization.dto import (
    CandidateData,
    CandidateGenerationResult,
    DiagnosticCode,
    DiagnosticReason,
    LessonRequestData,
    OptimizationInput,
    OptimizationResult,
    TeacherData,
    UnassignedLesson,
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

_MESSAGES: dict[DiagnosticCode, str] = {
    DiagnosticCode.NO_CANDIDATE: "必須条件をすべて満たす割当候補がありません",
    DiagnosticCode.INVALID_INPUT: "最適化入力に重複または不正な値があります",
    DiagnosticCode.INVALID_MASTER: "最適化に使用できないマスターデータです",
    DiagnosticCode.MISSING_STUDENT: "LessonRequestの生徒が登録されていません",
    DiagnosticCode.MISSING_SUBJECT: "LessonRequestの科目が登録されていません",
    DiagnosticCode.MISSING_TEACHER: "参照する講師が登録されていません",
    DiagnosticCode.INACTIVE_STUDENT: "無効な生徒は配置できません",
    DiagnosticCode.INACTIVE_SUBJECT: "無効な科目は配置できません",
    DiagnosticCode.INACTIVE_TEACHER: "無効な講師は配置できません",
    DiagnosticCode.CLOSED_DATE: "開校日以外には配置できません",
    DiagnosticCode.DISABLED_TIME_SLOT: "無効なコマには配置できません",
    DiagnosticCode.STUDENT_UNAVAILABLE: "生徒が受講不可または未回答です",
    DiagnosticCode.TEACHER_UNAVAILABLE: "講師が出勤不可または未回答です",
    DiagnosticCode.TEACHER_UNQUALIFIED: "科目を指導可能な講師ではありません",
    DiagnosticCode.PRIORITY_5_TEACHER_REQUIRED: "優先度5は通常担当講師以外へ配置できません",
    DiagnosticCode.PRIORITY_5_COMMON_SLOT_UNAVAILABLE: (
        "優先度5の通常担当講師と生徒に共通の配置可能枠がありません"
    ),
    DiagnosticCode.GROUP_LESSON_CONFLICT: "集団授業の生徒または担当講師と重複します",
    DiagnosticCode.LOCKED_ASSIGNMENT_CONFLICT: "固定済み授業と明白に衝突します",
    DiagnosticCode.ONE_TO_ONE_CAPACITY: "1対1必須授業と同一講師・同一コマを共有できません",
    DiagnosticCode.CONSECUTIVE_LIMIT: "生徒の連続授業上限に抵触します",
    DiagnosticCode.GAP_NOT_ALLOWED: "空きコマ禁止に抵触します",
    DiagnosticCode.SESSION_MISSING: "授業セッションが配置にも未配置にも含まれていません",
    DiagnosticCode.SESSION_DUPLICATE: "授業セッションが複数回結果へ含まれています",
    DiagnosticCode.UNEXPECTED_SESSION: "入力に存在しない授業セッションが結果に含まれています",
    DiagnosticCode.RESULT_REFERENCE_MISMATCH: "結果の生徒または科目参照が入力と一致しません",
    DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE: "候補生成を通過していない割当です",
    DiagnosticCode.LOCKED_ASSIGNMENT_NOT_PRESERVED: "固定済み授業が同じ日時・講師で保持されていません",
    DiagnosticCode.STUDENT_TIME_CONFLICT: "生徒が同じ日時に重複します",
    DiagnosticCode.TEACHER_CAPACITY_EXCEEDED: "同一講師・同一コマの生徒数が2名を超えます",
    DiagnosticCode.STUDENT_GAP_NOT_ALLOWED: "生徒に空きコマが発生します",
    DiagnosticCode.TEACHER_GAP_NOT_ALLOWED: "講師に空きコマが発生します",
    DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT: "生徒の最大連続コマ数を超えます",
    DiagnosticCode.GLOBAL_COMPETITION: "他の授業との全体的な競合により未配置です",
}

_UNASSIGNED_REASON_ORDER = (
    DiagnosticCode.STUDENT_TIME_CONFLICT,
    DiagnosticCode.TEACHER_CAPACITY_EXCEEDED,
    DiagnosticCode.ONE_TO_ONE_CAPACITY,
    DiagnosticCode.GROUP_LESSON_CONFLICT,
    DiagnosticCode.STUDENT_GAP_NOT_ALLOWED,
    DiagnosticCode.TEACHER_GAP_NOT_ALLOWED,
    DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT,
    DiagnosticCode.LOCKED_ASSIGNMENT_CONFLICT,
    DiagnosticCode.GLOBAL_COMPETITION,
)


def diagnostic_message(code: DiagnosticCode) -> str:
    return _MESSAGES[code]


def make_diagnostic_reason(
    code: DiagnosticCode,
    excluded_candidate_count: int = 0,
    *,
    details: tuple[tuple[str, str], ...] = (),
) -> DiagnosticReason:
    return DiagnosticReason(
        code=code,
        message=diagnostic_message(code),
        excluded_candidate_count=excluded_candidate_count,
        details=details,
    )


def diagnose_unassigned_lessons(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    result: OptimizationResult,
) -> tuple[UnassignedLesson, ...]:
    """未配置セッションへ候補段階または最終解競合の理由を付け直す。"""
    state = build_schedule_state(data, result.assignments)
    sessions = {session.key: session for session in generation.sessions}
    requests = {request.id: request for request in data.lesson_requests}
    teachers = {teacher.id: teacher for teacher in data.teachers}
    diagnosed: list[UnassignedLesson] = []

    for unassigned in sorted(
        result.unassigned_lessons,
        key=lambda item: (item.lesson_request_id, item.session_index),
    ):
        key = (unassigned.lesson_request_id, unassigned.session_index)
        session = sessions.get(key)
        if session is None:
            diagnosed.append(
                _replace_reasons(
                    unassigned,
                    (make_diagnostic_reason(DiagnosticCode.UNEXPECTED_SESSION),),
                )
            )
            continue
        candidates = generation.candidates_for(*key)
        if not candidates:
            candidate_diagnostics = generation.diagnostics_for(*key)
            reasons = (
                candidate_diagnostics.reasons
                if candidate_diagnostics is not None and candidate_diagnostics.reasons
                else (make_diagnostic_reason(DiagnosticCode.NO_CANDIDATE),)
            )
        else:
            request = requests[session.lesson_request_id]
            counts: Counter[DiagnosticCode] = Counter()
            for candidate in candidates:
                blockers = _candidate_blockers(
                    state,
                    request,
                    candidate,
                    teachers.get(candidate.teacher_id),
                )
                if not blockers:
                    counts[DiagnosticCode.GLOBAL_COMPETITION] += 1
                else:
                    counts.update(blockers)
            reasons = tuple(
                make_diagnostic_reason(code, counts[code])
                for code in _UNASSIGNED_REASON_ORDER
                if counts[code]
            )
        diagnosed.append(
            UnassignedLesson(
                lesson_request_id=session.lesson_request_id,
                session_index=session.session_index,
                student_id=session.student_id,
                subject_id=session.subject_id,
                reasons=reasons,
            )
        )
    return tuple(diagnosed)


def _candidate_blockers(
    state: ScheduleState,
    request: LessonRequestData,
    candidate: CandidateData,
    teacher: TeacherData | None,
) -> set[DiagnosticCode]:
    blockers: set[DiagnosticCode] = set()
    student_key = (candidate.student_id, candidate.day, candidate.time_slot_id)
    teacher_key = (candidate.teacher_id, candidate.day, candidate.time_slot_id)
    if state.student_occupancy.get(student_key):
        blockers.add(DiagnosticCode.STUDENT_TIME_CONFLICT)

    teacher_assignments = state.teacher_occupancy.get(teacher_key, ())
    if len(teacher_assignments) >= 2:
        blockers.add(DiagnosticCode.TEACHER_CAPACITY_EXCEEDED)
    if teacher_assignments and (
        request.one_to_one_required
        or any(
            state.requests.get(item.lesson_request_id) is None
            or state.requests[item.lesson_request_id].one_to_one_required
            for item in teacher_assignments
        )
    ):
        blockers.add(DiagnosticCode.ONE_TO_ONE_CAPACITY)
    if candidate_group_conflict(state, candidate):
        blockers.add(DiagnosticCode.GROUP_LESSON_CONFLICT)

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
        blockers.add(DiagnosticCode.STUDENT_GAP_NOT_ALLOWED)

    teacher_allow_gap = teacher.allow_gap if teacher is not None else False
    if not teacher_allow_gap and not occupied_slots_are_contiguous(
        state,
        teacher_occupied_slots(
            state,
            candidate.teacher_id,
            candidate.day,
            additional_slot_id=candidate.time_slot_id,
        ),
    ):
        blockers.add(DiagnosticCode.TEACHER_GAP_NOT_ALLOWED)
    if student_consecutive_limit_is_violated(
        state,
        candidate.student_id,
        candidate.day,
        additional_candidate=candidate,
    ):
        blockers.add(DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT)
    return blockers


def _replace_reasons(
    value: UnassignedLesson,
    reasons: tuple[DiagnosticReason, ...],
) -> UnassignedLesson:
    return UnassignedLesson(
        lesson_request_id=value.lesson_request_id,
        session_index=value.session_index,
        student_id=value.student_id,
        subject_id=value.subject_id,
        reasons=reasons,
    )


__all__ = [
    "diagnose_unassigned_lessons",
    "diagnostic_message",
    "make_diagnostic_reason",
]
