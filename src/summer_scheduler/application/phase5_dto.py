"""Phase 5の時間割編集画面へ公開する不変DTO。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

DropDecision = Literal["green", "yellow", "red"]
EditAction = Literal["move", "assign_unassigned", "unassign", "lock", "unlock", "note"]


@dataclass(frozen=True, slots=True)
class SessionKeyDto:
    lesson_request_id: int
    session_index: int


@dataclass(frozen=True, slots=True)
class ScheduleDateDto:
    day: date
    is_open: bool
    note: str


@dataclass(frozen=True, slots=True)
class ScheduleSlotDto:
    id: int
    code: str
    display_name: str
    start_time: time
    end_time: time
    sort_order: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class ScheduleTeacherDto:
    id: int
    name: str
    active: bool


@dataclass(frozen=True, slots=True)
class ScheduleCardDto:
    assignment_id: int
    lesson_request_id: int
    session_index: int
    student_id: int
    student_name: str
    grade: str
    subject_id: int
    subject_code: str
    subject_name: str
    day: date
    time_slot_id: int
    teacher_id: int
    one_to_one_required: bool
    priority_five: bool
    is_locked: bool
    is_manual: bool
    note: str
    regular_teacher_name: str
    preferred_teacher_names: tuple[str, ...]
    availability_text: str
    consecutive_text: str
    gap_text: str
    warning_messages: tuple[str, ...] = ()
    change_history: tuple[str, ...] = ()
    warning_count: int = 0


@dataclass(frozen=True, slots=True)
class ScheduleCellDto:
    day: date
    time_slot_id: int
    teacher_id: int
    assignment_keys: tuple[SessionKeyDto, ...]
    group_lesson_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class GroupBlockDto:
    id: int
    group_code: str
    course_name: str
    grade: str
    subject_name: str
    day: date
    start_time: time
    end_time: time
    teacher_id: int | None


@dataclass(frozen=True, slots=True)
class UnassignedSessionDto:
    lesson_request_id: int
    session_index: int
    student_id: int
    student_name: str
    grade: str
    subject_id: int
    subject_code: str
    subject_name: str
    remaining_count: int
    primary_reason: str
    candidate_count: int
    priority_five: bool
    one_to_one_required: bool


@dataclass(frozen=True, slots=True)
class AuditLogDto:
    id: int
    timestamp: datetime
    action: str
    entity_type: str
    entity_id: str
    before_json: str | None
    after_json: str | None
    reason: str
    source: str
    operation_id: str | None


@dataclass(frozen=True, slots=True)
class ScheduleDiffDto:
    lesson_request_id: int
    session_index: int
    change_type: str
    change_codes: tuple[str, ...]
    before_summary: str
    after_summary: str
    before_pairing_size: int | None
    after_pairing_size: int | None


@dataclass(frozen=True, slots=True)
class ScheduleBoardDto:
    project_id: int
    dates: tuple[ScheduleDateDto, ...]
    slots: tuple[ScheduleSlotDto, ...]
    teachers: tuple[ScheduleTeacherDto, ...]
    cells: tuple[ScheduleCellDto, ...]
    cards: tuple[ScheduleCardDto, ...]
    group_blocks: tuple[GroupBlockDto, ...]
    unassigned: tuple[UnassignedSessionDto, ...]
    audit_logs: tuple[AuditLogDto, ...]
    diff: tuple[ScheduleDiffDto, ...]
    lock_count: int
    unassigned_count: int
    fingerprint: str
    can_undo: bool
    can_redo: bool


@dataclass(frozen=True, slots=True)
class EditPreviewDto:
    action: EditAction
    lesson_request_id: int
    session_index: int
    allowed: bool
    decision: DropDecision
    preview_code: str
    hard_issue_codes: tuple[str, ...]
    hard_issues: tuple[str, ...]
    soft_warnings: tuple[str, ...]
    soft_deltas: tuple[SoftMetricDeltaDto, ...]
    before_summary: str
    after_summary: str
    expected_fingerprint: str


@dataclass(frozen=True, slots=True)
class SoftMetricDeltaDto:
    code: str
    label: str
    direction: str
    before_value: int
    after_value: int
    worsened: bool
    message: str


@dataclass(frozen=True, slots=True)
class EditResultDto:
    action: str
    lesson_request_id: int
    session_index: int
    fingerprint: str
    audit_log_id: int
    can_undo: bool
    can_redo: bool


@dataclass(frozen=True, slots=True)
class ReoptimizationSummaryDto:
    project_id: int
    assignment_count: int
    lock_count: int
    manual_count: int
    unassigned_count: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class CheckpointBackupDto:
    path: Path
    lock_count: int
    unassigned_count: int
    fingerprint: str


__all__ = [
    "AuditLogDto",
    "CheckpointBackupDto",
    "DropDecision",
    "EditAction",
    "EditPreviewDto",
    "EditResultDto",
    "GroupBlockDto",
    "ReoptimizationSummaryDto",
    "ScheduleBoardDto",
    "ScheduleCardDto",
    "ScheduleCellDto",
    "ScheduleDateDto",
    "ScheduleDiffDto",
    "ScheduleSlotDto",
    "ScheduleTeacherDto",
    "SessionKeyDto",
    "SoftMetricDeltaDto",
    "UnassignedSessionDto",
]
