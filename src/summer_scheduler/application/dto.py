"""UIへORMを公開しないためのPhase 2読み取りDTO。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectDetails:
    id: int
    path: Path
    title: str
    campus_name: str
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class TimeSlotDto:
    id: int
    code: str
    display_name: str
    start_time: time
    end_time: time
    sort_order: int
    enabled: bool


@dataclass(frozen=True, slots=True)
class OpenDateDto:
    id: int
    date: date
    is_open: bool
    note: str


@dataclass(frozen=True, slots=True)
class StudentDto:
    id: int
    external_id: str
    name: str
    grade: str
    default_max_consecutive_slots: int
    allow_gap: bool
    note: str
    active: bool


@dataclass(frozen=True, slots=True)
class TeacherDto:
    id: int
    external_id: str
    name: str
    allow_gap: bool
    note: str
    active: bool


@dataclass(frozen=True, slots=True)
class SubjectDto:
    id: int
    code: str
    display_name: str
    school_level: str
    sort_order: int
    active: bool


@dataclass(frozen=True, slots=True)
class QualificationDto:
    teacher_id: int
    subject_id: int
    subject_code: str
    subject_name: str
    school_level: str
    can_teach: bool
    note: str


@dataclass(frozen=True, slots=True)
class LessonRequestDto:
    id: int
    project_id: int
    student_id: int
    student_name: str
    subject_id: int
    subject_name: str
    required_sessions: int
    regular_teacher_id: int | None
    regular_teacher_name: str
    regular_teacher_priority: int
    preferred_teacher_1_id: int | None
    preferred_teacher_2_id: int | None
    preferred_teacher_3_id: int | None
    one_to_one_required: bool
    max_consecutive_slots_override: int | None
    allow_gap_override: bool | None
    note: str


@dataclass(frozen=True, slots=True)
class SaveResult:
    """保存結果と、保存を妨げない警告。"""

    record_id: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    student_count: int
    teacher_count: int
    lesson_request_count: int
