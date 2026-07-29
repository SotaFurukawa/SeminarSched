"""Phase 3の取込み・集団授業・入力検証DTO。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Literal

AvailabilityKind = Literal["student", "teacher"]
DiffOperation = Literal["add", "change", "unchanged", "delete_candidate"]
IssueSeverity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class ImportIssueDto:
    severity: IssueSeverity
    message: str
    code: str
    sheet: str = ""
    row: int | None = None
    column: str = ""


@dataclass(frozen=True, slots=True)
class AvailabilityRow:
    """列mapping後に業務検証できる1日分のavailability回答。"""

    source_row: int
    external_id: str
    name: str
    day: date
    slot_levels: dict[str, int]
    subject_code: str | None = None
    preferred_teacher_ids: tuple[str | None, str | None, str | None] = (
        None,
        None,
        None,
    )
    preferred_teacher_fields_supplied: tuple[bool, bool, bool] = (
        False,
        False,
        False,
    )
    note: str = ""


@dataclass(frozen=True, slots=True)
class AvailabilityDiffDto:
    operation: DiffOperation
    entity_id: int
    external_id: str
    entity_name: str
    day: date
    time_slot_id: int
    slot_code: str
    before: int | None
    after: int | None
    message: str


@dataclass(frozen=True, slots=True)
class AvailabilityImportPreview:
    project_id: int
    kind: AvailabilityKind
    source_path: Path
    sheet_name: str
    encoding: str | None
    mapping: dict[str, str]
    rows: tuple[AvailabilityRow, ...]
    diffs: tuple[AvailabilityDiffDto, ...]
    issues: tuple[ImportIssueDto, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


@dataclass(frozen=True, slots=True)
class GroupLessonRow:
    source_row: int
    group_code: str
    grade: str
    subject_code: str
    course_name: str
    day: date
    start_time: time
    end_time: time
    teacher_external_id: str | None
    room: str | None
    note: str
    student_external_ids: tuple[str, ...]
    source_columns: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GroupLessonDiffDto:
    operation: DiffOperation
    group_lesson_id: int | None
    group_code: str
    day: date
    before: str
    after: str
    message: str


@dataclass(frozen=True, slots=True)
class GroupImportPreview:
    project_id: int
    source_path: Path
    rows: tuple[GroupLessonRow, ...]
    diffs: tuple[GroupLessonDiffDto, ...]
    issues: tuple[ImportIssueDto, ...]
    lesson_mapping: dict[str, str] = field(default_factory=dict)
    participant_mapping: dict[str, str] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


@dataclass(frozen=True, slots=True)
class GroupLessonDto:
    id: int
    group_code: str
    grade: str
    subject_name: str
    course_name: str
    day: date
    start_time: time
    end_time: time
    teacher_name: str
    room: str
    note: str
    student_count: int


@dataclass(frozen=True, slots=True)
class ValidationIssueDto:
    id: int
    severity: IssueSeverity
    issue_type: str
    entity_type: str
    entity_id: str | None
    message: str
    details: dict[str, object]
    resolved: bool


@dataclass(frozen=True, slots=True)
class ImportApplyResult:
    batch_id: int
    added: int
    changed: int
    unchanged: int
    deleted: int
    warnings: int


__all__ = [
    "AvailabilityDiffDto",
    "AvailabilityImportPreview",
    "AvailabilityKind",
    "AvailabilityRow",
    "DiffOperation",
    "GroupImportPreview",
    "GroupLessonDiffDto",
    "GroupLessonDto",
    "GroupLessonRow",
    "ImportApplyResult",
    "ImportIssueDto",
    "IssueSeverity",
    "ValidationIssueDto",
]
