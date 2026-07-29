"""時間割の手動編集をpreviewする、UI・ORM・solver非依存の境界。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

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
from summer_scheduler.optimization.result_validation import (
    ResultValidationReport,
    ResultViolation,
    validate_optimization_result,
)

type SessionKey = tuple[int, int]


class EditOperationKind(StrEnum):
    """手動編集で許可するsession partitionの変更種別。"""

    MOVE = "move"
    ASSIGN_UNASSIGNED = "assign_unassigned"
    UNASSIGN = "unassign"


class EditDecision(StrEnum):
    """色以外の文字・アイコンと併用するdrop判定。"""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class EditPreviewCode(StrEnum):
    """画面層や監査ログで利用する安定したpreview結果コード。"""

    ALLOWED = "edit_allowed"
    SOFT_WARNING = "soft_condition_worsened"
    HARD_REJECTED = "hard_constraint_rejected"
    INVALID_OPERATION = "invalid_edit_operation"
    INVALID_CURRENT_SCHEDULE = "invalid_current_schedule"


class EditIssueCode(StrEnum):
    """Phase 4のDiagnosticCodeでは表現できない編集境界エラー。"""

    INVALID_OPERATION = "invalid_edit_operation"
    SESSION_NOT_ASSIGNED = "session_not_assigned"
    SESSION_NOT_UNASSIGNED = "session_not_unassigned"
    TARGET_REQUIRED = "edit_target_required"
    TARGET_NOT_ALLOWED = "edit_target_not_allowed"


class SoftMetricCode(StrEnum):
    """手動編集前後で比較するソフト評価の安定コード。"""

    UNASSIGNED_COUNT = "unassigned_count"
    REGULAR_TEACHER_PENALTY = "regular_teacher_penalty"
    PREFERRED_TEACHER_PENALTY = "preferred_teacher_penalty"
    PREFERRED_TIME_SCORE = "preferred_time_score"
    PAIRED_SLOT_COUNT = "paired_slot_count"
    ACTIVE_TEACHER_SLOT_COUNT = "active_teacher_slot_count"
    CHANGED_EXISTING_ASSIGNMENT_COUNT = "changed_existing_assignment_count"


class MetricDirection(StrEnum):
    """評価値のどちら側を良いとするか。"""

    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"


@dataclass(frozen=True, slots=True)
class EditSchedule:
    """配置・未配置が全sessionを一度ずつ表す不変スナップショット。"""

    assignments: tuple[ScheduledAssignment, ...]
    unassigned_lessons: tuple[UnassignedLesson, ...]


@dataclass(frozen=True, slots=True)
class EditTarget:
    day: date
    time_slot_id: int
    teacher_id: int


@dataclass(frozen=True, slots=True)
class EditOperation:
    kind: EditOperationKind
    lesson_request_id: int
    session_index: int
    target: EditTarget | None = None

    @property
    def session_key(self) -> SessionKey:
        return (self.lesson_request_id, self.session_index)


@dataclass(frozen=True, slots=True)
class EditHardIssue:
    """Phase 4の違反codeを型を変えず保持する編集拒否理由。"""

    code: DiagnosticCode | EditIssueCode
    message: str
    lesson_request_id: int | None = None
    session_index: int | None = None
    day: date | None = None
    time_slot_id: int | None = None
    teacher_id: int | None = None
    details: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SoftMetricDelta:
    code: SoftMetricCode
    label: str
    direction: MetricDirection
    before_value: int
    after_value: int

    @property
    def worsened(self) -> bool:
        if self.direction is MetricDirection.LOWER_IS_BETTER:
            return self.after_value > self.before_value
        return self.after_value < self.before_value

    @property
    def message(self) -> str:
        if self.worsened:
            state = "悪化します"
        elif self.before_value == self.after_value:
            state = "変わりません"
        else:
            state = "改善します"
        return f"{self.label}: {self.before_value} → {self.after_value}（{state}）"


@dataclass(frozen=True, slots=True)
class EditPreview:
    operation: EditOperation
    decision: EditDecision
    code: EditPreviewCode
    message: str
    current_schedule: EditSchedule
    proposed_schedule: EditSchedule
    hard_issues: tuple[EditHardIssue, ...] = ()
    soft_deltas: tuple[SoftMetricDelta, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.decision is not EditDecision.RED

    @property
    def worsened_soft_deltas(self) -> tuple[SoftMetricDelta, ...]:
        return tuple(item for item in self.soft_deltas if item.worsened)


@dataclass(frozen=True, slots=True)
class _SoftMetrics:
    unassigned_count: int
    regular_teacher_penalty: int
    preferred_teacher_penalty: int
    preferred_time_score: int
    paired_slot_count: int
    active_teacher_slot_count: int
    changed_existing_assignment_count: int


_EDIT_ISSUE_MESSAGES: dict[EditIssueCode, str] = {
    EditIssueCode.INVALID_OPERATION: "編集操作の内容が正しくありません",
    EditIssueCode.SESSION_NOT_ASSIGNED: "指定した授業は現在の時間割に配置されていません",
    EditIssueCode.SESSION_NOT_UNASSIGNED: "指定した授業は未配置一覧にありません",
    EditIssueCode.TARGET_REQUIRED: "移動先の日付・コマ・講師を指定してください",
    EditIssueCode.TARGET_NOT_ALLOWED: "未配置化では移動先を指定できません",
}


def preview_edit(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    current: EditSchedule,
    operation: EditOperation,
) -> EditPreview:
    """操作を適用せず、候補境界・全ハード制約・ソフト差分を返す。

    現在状態も完全partitionとして先に検証する。壊れた状態を編集で上書きして
    正常扱いすることはない。赤判定には強制適用経路を設けない。
    """
    canonical_current = _canonical_schedule(current)
    current_report = validate_optimization_result(
        data,
        generation,
        _as_result(canonical_current),
    )
    if not current_report.is_valid:
        return _rejected_preview(
            operation=operation,
            code=EditPreviewCode.INVALID_CURRENT_SCHEDULE,
            message="現在の時間割が完全なpartitionまたはハード制約を満たしていません",
            current=canonical_current,
            proposed=canonical_current,
            issues=_issues_from_report(current_report),
        )

    operation_issue = _validate_operation(canonical_current, operation)
    if operation_issue is not None:
        return _rejected_preview(
            operation=operation,
            code=EditPreviewCode.INVALID_OPERATION,
            message=operation_issue.message,
            current=canonical_current,
            proposed=canonical_current,
            issues=(operation_issue,),
        )

    locked_issue = _locked_source_issue(data, canonical_current, operation)
    if locked_issue is not None:
        return _rejected_preview(
            operation=operation,
            code=EditPreviewCode.HARD_REJECTED,
            message=locked_issue.message,
            current=canonical_current,
            proposed=canonical_current,
            issues=(locked_issue,),
        )

    proposed = _apply_operation(data, generation, canonical_current, operation)
    proposed_report = validate_optimization_result(
        data,
        generation,
        _as_result(proposed),
    )
    if not proposed_report.is_valid:
        issues = _issues_from_report(proposed_report)
        first_message = issues[0].message if issues else "ハード制約に違反します"
        return _rejected_preview(
            operation=operation,
            code=EditPreviewCode.HARD_REJECTED,
            message=f"ハード制約違反のため変更できません: {first_message}",
            current=canonical_current,
            proposed=proposed,
            issues=issues,
        )

    deltas = _soft_deltas(data, generation, canonical_current, proposed)
    worsened = tuple(item for item in deltas if item.worsened)
    if worsened:
        return EditPreview(
            operation=operation,
            decision=EditDecision.YELLOW,
            code=EditPreviewCode.SOFT_WARNING,
            message=f"配置は可能ですが、ソフト条件が{len(worsened)}項目悪化します",
            current_schedule=canonical_current,
            proposed_schedule=proposed,
            soft_deltas=deltas,
        )
    return EditPreview(
        operation=operation,
        decision=EditDecision.GREEN,
        code=EditPreviewCode.ALLOWED,
        message="ハード制約を満たし、悪化するソフト条件はありません",
        current_schedule=canonical_current,
        proposed_schedule=proposed,
        soft_deltas=deltas,
    )


def preview_move(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    current: EditSchedule,
    *,
    lesson_request_id: int,
    session_index: int,
    target: EditTarget,
) -> EditPreview:
    return preview_edit(
        data,
        generation,
        current,
        EditOperation(
            kind=EditOperationKind.MOVE,
            lesson_request_id=lesson_request_id,
            session_index=session_index,
            target=target,
        ),
    )


def preview_assign_unassigned(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    current: EditSchedule,
    *,
    lesson_request_id: int,
    session_index: int,
    target: EditTarget,
) -> EditPreview:
    return preview_edit(
        data,
        generation,
        current,
        EditOperation(
            kind=EditOperationKind.ASSIGN_UNASSIGNED,
            lesson_request_id=lesson_request_id,
            session_index=session_index,
            target=target,
        ),
    )


def preview_unassign(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    current: EditSchedule,
    *,
    lesson_request_id: int,
    session_index: int,
) -> EditPreview:
    return preview_edit(
        data,
        generation,
        current,
        EditOperation(
            kind=EditOperationKind.UNASSIGN,
            lesson_request_id=lesson_request_id,
            session_index=session_index,
        ),
    )


def _validate_operation(
    current: EditSchedule,
    operation: EditOperation,
) -> EditHardIssue | None:
    assignment_count = sum(
        _assignment_key(item) == operation.session_key for item in current.assignments
    )
    unassigned_count = sum(
        _unassigned_key(item) == operation.session_key for item in current.unassigned_lessons
    )
    if operation.kind in (EditOperationKind.MOVE, EditOperationKind.ASSIGN_UNASSIGNED):
        if operation.target is None:
            return _edit_issue(EditIssueCode.TARGET_REQUIRED, operation)
    elif operation.kind is EditOperationKind.UNASSIGN and operation.target is not None:
        return _edit_issue(EditIssueCode.TARGET_NOT_ALLOWED, operation)

    if operation.kind in (EditOperationKind.MOVE, EditOperationKind.UNASSIGN):
        if assignment_count != 1:
            return _edit_issue(EditIssueCode.SESSION_NOT_ASSIGNED, operation)
    elif operation.kind is EditOperationKind.ASSIGN_UNASSIGNED:
        if unassigned_count != 1:
            return _edit_issue(EditIssueCode.SESSION_NOT_UNASSIGNED, operation)
    else:
        return _edit_issue(EditIssueCode.INVALID_OPERATION, operation)
    return None


def _locked_source_issue(
    data: OptimizationInput,
    current: EditSchedule,
    operation: EditOperation,
) -> EditHardIssue | None:
    if operation.kind is EditOperationKind.ASSIGN_UNASSIGNED:
        return None
    current_assignment = next(
        item for item in current.assignments if _assignment_key(item) == operation.session_key
    )
    input_lock = any(
        item.is_locked and (item.lesson_request_id, item.session_index) == operation.session_key
        for item in data.existing_assignments
    )
    if not current_assignment.is_locked and not input_lock:
        return None
    return EditHardIssue(
        code=DiagnosticCode.LOCKED_ASSIGNMENT_NOT_PRESERVED,
        message="ロック済み授業は移動または未配置化できません",
        lesson_request_id=operation.lesson_request_id,
        session_index=operation.session_index,
    )


def _apply_operation(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    current: EditSchedule,
    operation: EditOperation,
) -> EditSchedule:
    assignments = [
        item for item in current.assignments if _assignment_key(item) != operation.session_key
    ]
    unassigned = [
        item
        for item in current.unassigned_lessons
        if _unassigned_key(item) != operation.session_key
    ]
    if operation.kind is EditOperationKind.UNASSIGN:
        request = next(
            item for item in data.lesson_requests if item.id == operation.lesson_request_id
        )
        unassigned.append(
            UnassignedLesson(
                lesson_request_id=request.id,
                session_index=operation.session_index,
                student_id=request.student_id,
                subject_id=request.subject_id,
                reasons=(),
            )
        )
    else:
        target = operation.target
        if target is None:  # pragma: no cover - _validate_operationの型絞込み用
            raise AssertionError("target is required")
        candidate = _candidate_for_target(generation, operation.session_key, target)
        assignments.append(
            _assignment_from_target(data, generation, operation.session_key, target, candidate)
        )
    return _canonical_schedule(
        EditSchedule(assignments=tuple(assignments), unassigned_lessons=tuple(unassigned))
    )


def _candidate_for_target(
    generation: CandidateGenerationResult,
    key: SessionKey,
    target: EditTarget,
) -> CandidateData | None:
    return next(
        (
            candidate
            for candidate in generation.candidates_for(*key)
            if candidate.day == target.day
            and candidate.time_slot_id == target.time_slot_id
            and candidate.teacher_id == target.teacher_id
        ),
        None,
    )


def _assignment_from_target(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    key: SessionKey,
    target: EditTarget,
    candidate: CandidateData | None,
) -> ScheduledAssignment:
    if candidate is not None:
        student_id = candidate.student_id
        subject_id = candidate.subject_id
    else:
        session = next((item for item in generation.sessions if item.key == key), None)
        if session is not None:
            student_id = session.student_id
            subject_id = session.subject_id
        else:
            request = next(item for item in data.lesson_requests if item.id == key[0])
            student_id = request.student_id
            subject_id = request.subject_id
    return ScheduledAssignment(
        lesson_request_id=key[0],
        session_index=key[1],
        student_id=student_id,
        subject_id=subject_id,
        teacher_id=target.teacher_id,
        day=target.day,
        time_slot_id=target.time_slot_id,
        is_locked=False,
    )


def _soft_deltas(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    before: EditSchedule,
    after: EditSchedule,
) -> tuple[SoftMetricDelta, ...]:
    before_metrics = _soft_metrics(data, generation, before)
    after_metrics = _soft_metrics(data, generation, after)
    return (
        _delta(
            SoftMetricCode.UNASSIGNED_COUNT,
            "未配置授業数",
            MetricDirection.LOWER_IS_BETTER,
            before_metrics.unassigned_count,
            after_metrics.unassigned_count,
        ),
        _delta(
            SoftMetricCode.REGULAR_TEACHER_PENALTY,
            "通常担当講師から外れる度合い",
            MetricDirection.LOWER_IS_BETTER,
            before_metrics.regular_teacher_penalty,
            after_metrics.regular_teacher_penalty,
        ),
        _delta(
            SoftMetricCode.PREFERRED_TEACHER_PENALTY,
            "第1～第3希望講師から外れる度合い",
            MetricDirection.LOWER_IS_BETTER,
            before_metrics.preferred_teacher_penalty,
            after_metrics.preferred_teacher_penalty,
        ),
        _delta(
            SoftMetricCode.PREFERRED_TIME_SCORE,
            "生徒・講師の希望日時スコア",
            MetricDirection.HIGHER_IS_BETTER,
            before_metrics.preferred_time_score,
            after_metrics.preferred_time_score,
        ),
        _delta(
            SoftMetricCode.PAIRED_SLOT_COUNT,
            "1対2の講師枠数",
            MetricDirection.HIGHER_IS_BETTER,
            before_metrics.paired_slot_count,
            after_metrics.paired_slot_count,
        ),
        _delta(
            SoftMetricCode.ACTIVE_TEACHER_SLOT_COUNT,
            "稼働講師枠数",
            MetricDirection.LOWER_IS_BETTER,
            before_metrics.active_teacher_slot_count,
            after_metrics.active_teacher_slot_count,
        ),
        _delta(
            SoftMetricCode.CHANGED_EXISTING_ASSIGNMENT_COUNT,
            "前回割当てからの変更数",
            MetricDirection.LOWER_IS_BETTER,
            before_metrics.changed_existing_assignment_count,
            after_metrics.changed_existing_assignment_count,
        ),
    )


def _soft_metrics(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    schedule: EditSchedule,
) -> _SoftMetrics:
    requests = {item.id: item for item in data.lesson_requests}
    candidate_by_identity = {_candidate_identity(item): item for item in generation.candidates}
    regular_penalty = 0
    preferred_penalty = 0
    preferred_time_score = 0
    for assignment in schedule.assignments:
        request = requests[assignment.lesson_request_id]
        regular_penalty += _regular_teacher_penalty(data, request.id, assignment.teacher_id)
        preferred_penalty += _preferred_teacher_penalty(data, request.id, assignment.teacher_id)
        candidate = candidate_by_identity.get(_assignment_identity(assignment))
        if candidate is not None:
            if candidate.student_availability_level == 2:
                preferred_time_score += data.settings.student_preferred_time_weight
            if candidate.teacher_availability_level == 2:
                preferred_time_score += data.settings.teacher_preferred_time_weight

    occupancy: dict[tuple[int, date, int], int] = {}
    for assignment in schedule.assignments:
        key = (assignment.teacher_id, assignment.day, assignment.time_slot_id)
        occupancy[key] = occupancy.get(key, 0) + 1
    changed_existing = _changed_existing_count(data, schedule)
    return _SoftMetrics(
        unassigned_count=len(schedule.unassigned_lessons),
        regular_teacher_penalty=regular_penalty,
        preferred_teacher_penalty=preferred_penalty,
        preferred_time_score=preferred_time_score,
        paired_slot_count=sum(count == 2 for count in occupancy.values()),
        active_teacher_slot_count=len(occupancy),
        changed_existing_assignment_count=changed_existing,
    )


def _regular_teacher_penalty(
    data: OptimizationInput,
    request_id: int,
    teacher_id: int,
) -> int:
    request = next(item for item in data.lesson_requests if item.id == request_id)
    if (
        request.regular_teacher_id is None
        or request.regular_teacher_priority == 5
        or teacher_id == request.regular_teacher_id
        or not 1 <= request.regular_teacher_priority <= 4
    ):
        return 0
    return data.settings.regular_teacher_priority_weights[request.regular_teacher_priority - 1]


def _preferred_teacher_penalty(
    data: OptimizationInput,
    request_id: int,
    teacher_id: int,
) -> int:
    request = next(item for item in data.lesson_requests if item.id == request_id)
    scores: dict[int, int] = {}
    for rank, preferred_teacher_id in enumerate(request.preferred_teacher_ids):
        if preferred_teacher_id is None:
            continue
        scores[preferred_teacher_id] = max(
            scores.get(preferred_teacher_id, 0),
            data.settings.preferred_teacher_rank_weights[rank],
        )
    best = max(scores.values(), default=0)
    return best - scores.get(teacher_id, 0)


def _changed_existing_count(
    data: OptimizationInput,
    schedule: EditSchedule,
) -> int:
    assignments = {
        _assignment_key(item): (item.day, item.time_slot_id, item.teacher_id)
        for item in schedule.assignments
    }
    return sum(
        assignments.get((item.lesson_request_id, item.session_index))
        != (item.day, item.time_slot_id, item.teacher_id)
        for item in data.existing_assignments
        if not item.is_locked
    )


def _delta(
    code: SoftMetricCode,
    label: str,
    direction: MetricDirection,
    before: int,
    after: int,
) -> SoftMetricDelta:
    return SoftMetricDelta(
        code=code,
        label=label,
        direction=direction,
        before_value=before,
        after_value=after,
    )


def _as_result(schedule: EditSchedule) -> OptimizationResult:
    return OptimizationResult(
        solver_status="FEASIBLE",
        assignments=schedule.assignments,
        unassigned_lessons=schedule.unassigned_lessons,
        objective_breakdown=ObjectiveBreakdown(unassigned_count=len(schedule.unassigned_lessons)),
        elapsed_seconds=0.0,
    )


def _issues_from_report(report: ResultValidationReport) -> tuple[EditHardIssue, ...]:
    return tuple(_issue_from_violation(item) for item in report.violations)


def _issue_from_violation(violation: ResultViolation) -> EditHardIssue:
    return EditHardIssue(
        code=violation.code,
        message=violation.message,
        lesson_request_id=violation.lesson_request_id,
        session_index=violation.session_index,
        day=violation.day,
        time_slot_id=violation.time_slot_id,
        teacher_id=violation.teacher_id,
        details=violation.details,
    )


def _edit_issue(code: EditIssueCode, operation: EditOperation) -> EditHardIssue:
    return EditHardIssue(
        code=code,
        message=_EDIT_ISSUE_MESSAGES[code],
        lesson_request_id=operation.lesson_request_id,
        session_index=operation.session_index,
    )


def _rejected_preview(
    *,
    operation: EditOperation,
    code: EditPreviewCode,
    message: str,
    current: EditSchedule,
    proposed: EditSchedule,
    issues: tuple[EditHardIssue, ...],
) -> EditPreview:
    return EditPreview(
        operation=operation,
        decision=EditDecision.RED,
        code=code,
        message=message,
        current_schedule=current,
        proposed_schedule=proposed,
        hard_issues=issues,
    )


def _canonical_schedule(schedule: EditSchedule) -> EditSchedule:
    return EditSchedule(
        assignments=tuple(
            sorted(
                schedule.assignments,
                key=lambda item: (
                    item.lesson_request_id,
                    item.session_index,
                    item.day,
                    item.time_slot_id,
                    item.teacher_id,
                ),
            )
        ),
        unassigned_lessons=tuple(
            sorted(
                schedule.unassigned_lessons,
                key=lambda item: (item.lesson_request_id, item.session_index),
            )
        ),
    )


def _assignment_key(item: ScheduledAssignment) -> SessionKey:
    return (item.lesson_request_id, item.session_index)


def _unassigned_key(item: UnassignedLesson) -> SessionKey:
    return (item.lesson_request_id, item.session_index)


def _candidate_identity(
    item: CandidateData,
) -> tuple[int, int, int, int, int, date, int]:
    return (
        item.lesson_request_id,
        item.session_index,
        item.student_id,
        item.subject_id,
        item.teacher_id,
        item.day,
        item.time_slot_id,
    )


def _assignment_identity(
    item: ScheduledAssignment,
) -> tuple[int, int, int, int, int, date, int]:
    return (
        item.lesson_request_id,
        item.session_index,
        item.student_id,
        item.subject_id,
        item.teacher_id,
        item.day,
        item.time_slot_id,
    )


__all__ = [
    "EditDecision",
    "EditHardIssue",
    "EditIssueCode",
    "EditOperation",
    "EditOperationKind",
    "EditPreview",
    "EditPreviewCode",
    "EditSchedule",
    "EditTarget",
    "MetricDirection",
    "SoftMetricCode",
    "SoftMetricDelta",
    "preview_assign_unassigned",
    "preview_edit",
    "preview_move",
    "preview_unassign",
]
