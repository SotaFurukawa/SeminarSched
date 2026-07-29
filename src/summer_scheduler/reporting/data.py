"""DBから切り離した、Phase 6出力用の不変スナップショット。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Final


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: int
    title: str
    campus_name: str
    start_date: date
    end_date: date
    status: str
    generated_at: datetime
    logo_path_optional: str | None = None


@dataclass(frozen=True, slots=True)
class DateRecord:
    day: date
    is_open: bool
    note: str
    configured: bool = True


@dataclass(frozen=True, slots=True)
class SlotRecord:
    id: int
    code: str
    display_name: str
    start_time: time
    end_time: time
    sort_order: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class StudentRecord:
    id: int
    external_id: str
    name: str
    grade: str
    note: str
    active: bool


@dataclass(frozen=True, slots=True)
class TeacherRecord:
    id: int
    external_id: str
    name: str
    note: str
    active: bool


@dataclass(frozen=True, slots=True)
class SubjectRecord:
    id: int
    code: str
    name: str
    school_level: str


@dataclass(frozen=True, slots=True)
class LessonRequestRecord:
    id: int
    student_id: int
    subject_id: int
    required_sessions: int
    regular_teacher_id_optional: int | None
    regular_teacher_priority: int
    one_to_one_required: bool
    note: str


@dataclass(frozen=True, slots=True)
class AssignmentRecord:
    id: int
    lesson_request_id: int
    session_index: int
    day: date
    time_slot_id: int
    teacher_id: int
    is_locked: bool
    is_manual: bool
    note: str


@dataclass(frozen=True, slots=True)
class GroupLessonRecord:
    id: int
    group_code: str
    course_name: str
    grade: str
    subject_id: int
    day: date
    start_time: time
    end_time: time
    teacher_id_optional: int | None
    student_ids: tuple[int, ...]
    room: str
    note: str


@dataclass(frozen=True, slots=True)
class UnassignedRecord:
    lesson_request_id: int
    student_id: int
    subject_id: int
    required_sessions: int
    placed_sessions: int
    missing_sessions: int
    main_reason: str
    reason_codes: tuple[str, ...]
    resolution_candidates: tuple[str, ...]
    candidate_count: int
    priority: int
    regular_teacher_id_optional: int | None
    one_to_one_required: bool
    note: str


@dataclass(frozen=True, slots=True)
class WarningRecord:
    severity: str
    issue_type: str
    day_optional: date | None
    slot_code: str
    student_name: str
    teacher_name: str
    content: str
    status: str
    student_ids: tuple[int, ...] = ()
    teacher_id_optional: int | None = None


@dataclass(frozen=True, slots=True)
class OutputSnapshot:
    project: ProjectRecord
    dates: tuple[DateRecord, ...]
    slots: tuple[SlotRecord, ...]
    students: tuple[StudentRecord, ...]
    teachers: tuple[TeacherRecord, ...]
    subjects: tuple[SubjectRecord, ...]
    lesson_requests: tuple[LessonRequestRecord, ...]
    assignments: tuple[AssignmentRecord, ...]
    group_lessons: tuple[GroupLessonRecord, ...]
    unassigned: tuple[UnassignedRecord, ...]
    warnings: tuple[WarningRecord, ...]


@dataclass(frozen=True, slots=True)
class OutputSelection:
    """空tupleを「すべて」と解釈する出力対象フィルター。"""

    dates: tuple[date, ...] = ()
    teacher_ids: tuple[int, ...] = ()
    student_ids: tuple[int, ...] = ()


DEFAULT_OUTPUT_SELECTION: Final = OutputSelection()


__all__ = [
    "AssignmentRecord",
    "DateRecord",
    "DEFAULT_OUTPUT_SELECTION",
    "GroupLessonRecord",
    "LessonRequestRecord",
    "OutputSelection",
    "OutputSnapshot",
    "ProjectRecord",
    "SlotRecord",
    "StudentRecord",
    "SubjectRecord",
    "TeacherRecord",
    "UnassignedRecord",
    "WarningRecord",
]
