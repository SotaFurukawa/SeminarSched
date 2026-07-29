"""ORM と solver の双方から独立した最適化境界の不変 DTO。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum
from typing import Literal

AvailabilityOwner = Literal["student", "teacher"]
SolverStatus = Literal[
    "OPTIMAL",
    "FEASIBLE",
    "INFEASIBLE",
    "UNKNOWN",
    "MODEL_INVALID",
]


class DiagnosticCode(StrEnum):
    """候補除外・未配置理由の安定した機械可読コード。"""

    NO_CANDIDATE = "no_candidate"
    INVALID_INPUT = "invalid_input"
    INVALID_MASTER = "invalid_master"
    MISSING_STUDENT = "missing_student"
    MISSING_SUBJECT = "missing_subject"
    MISSING_TEACHER = "missing_teacher"
    INACTIVE_STUDENT = "inactive_student"
    INACTIVE_SUBJECT = "inactive_subject"
    INACTIVE_TEACHER = "inactive_teacher"
    CLOSED_DATE = "closed_date"
    DISABLED_TIME_SLOT = "disabled_time_slot"
    STUDENT_UNAVAILABLE = "student_unavailable"
    TEACHER_UNAVAILABLE = "teacher_unavailable"
    TEACHER_UNQUALIFIED = "teacher_unqualified"
    PRIORITY_5_TEACHER_REQUIRED = "priority_5_teacher_required"
    PRIORITY_5_COMMON_SLOT_UNAVAILABLE = "priority_5_common_slot_unavailable"
    GROUP_LESSON_CONFLICT = "group_lesson_conflict"
    LOCKED_ASSIGNMENT_CONFLICT = "locked_assignment_conflict"
    ONE_TO_ONE_CAPACITY = "one_to_one_capacity"
    CONSECUTIVE_LIMIT = "consecutive_limit"
    GAP_NOT_ALLOWED = "gap_not_allowed"
    SESSION_MISSING = "session_missing"
    SESSION_DUPLICATE = "session_duplicate"
    UNEXPECTED_SESSION = "unexpected_session"
    RESULT_REFERENCE_MISMATCH = "result_reference_mismatch"
    ASSIGNMENT_NOT_CANDIDATE = "assignment_not_candidate"
    LOCKED_ASSIGNMENT_NOT_PRESERVED = "locked_assignment_not_preserved"
    STUDENT_TIME_CONFLICT = "student_time_conflict"
    TEACHER_CAPACITY_EXCEEDED = "teacher_capacity_exceeded"
    STUDENT_GAP_NOT_ALLOWED = "student_gap_not_allowed"
    TEACHER_GAP_NOT_ALLOWED = "teacher_gap_not_allowed"
    STUDENT_CONSECUTIVE_LIMIT = "student_consecutive_limit"
    GLOBAL_COMPETITION = "global_competition"


@dataclass(frozen=True, slots=True)
class TimeSlotData:
    id: int
    code: str
    display_name: str
    start_time: time
    end_time: time
    sort_order: int
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class StudentData:
    id: int
    display_name: str
    default_max_consecutive_slots: int = 2
    allow_gap: bool = False
    active: bool = True


@dataclass(frozen=True, slots=True)
class TeacherData:
    id: int
    display_name: str
    qualified_subject_ids: frozenset[int] = field(default_factory=frozenset)
    allow_gap: bool = False
    active: bool = True


@dataclass(frozen=True, slots=True)
class SubjectData:
    id: int
    code: str
    display_name: str
    active: bool = True


@dataclass(frozen=True, slots=True)
class LessonRequestData:
    id: int
    student_id: int
    subject_id: int
    required_sessions: int
    regular_teacher_id: int | None = None
    regular_teacher_priority: int = 1
    # DBの第1～第3希望を欠番込みで保持し、順位を詰めて意味を変えない。
    preferred_teacher_ids: tuple[int | None, int | None, int | None] = (
        None,
        None,
        None,
    )
    one_to_one_required: bool = False
    max_consecutive_slots_override: int | None = None
    allow_gap_override: bool | None = None


@dataclass(frozen=True, slots=True)
class AvailabilityData:
    owner_type: AvailabilityOwner
    owner_id: int
    day: date
    time_slot_id: int
    level: int


@dataclass(frozen=True, slots=True)
class GroupBlockData:
    id: int
    day: date
    start_time: time
    end_time: time
    teacher_id: int | None = None
    student_ids: frozenset[int] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ExistingAssignmentData:
    id: int
    lesson_request_id: int
    session_index: int
    day: date
    time_slot_id: int
    teacher_id: int
    is_locked: bool = False
    is_manual: bool = False


@dataclass(frozen=True, slots=True)
class OptimizationSettings:
    """Solver設定。評価値は設定ファイル等から明示的に注入する。"""

    time_limit_seconds: float
    random_seed: int
    num_search_workers: int
    regular_teacher_priority_weights: tuple[int, int, int, int]
    preferred_teacher_rank_weights: tuple[int, int, int]
    student_preferred_time_weight: int
    teacher_preferred_time_weight: int
    preserve_existing_assignment_weight: int
    optional_balance_weight: int = 0


@dataclass(frozen=True, slots=True)
class OptimizationInput:
    project_id: int
    open_dates: tuple[date, ...]
    time_slots: tuple[TimeSlotData, ...]
    students: tuple[StudentData, ...]
    teachers: tuple[TeacherData, ...]
    subjects: tuple[SubjectData, ...]
    lesson_requests: tuple[LessonRequestData, ...]
    availabilities: tuple[AvailabilityData, ...]
    group_blocks: tuple[GroupBlockData, ...]
    existing_assignments: tuple[ExistingAssignmentData, ...]
    settings: OptimizationSettings


@dataclass(frozen=True, slots=True)
class LessonSessionData:
    lesson_request_id: int
    session_index: int
    student_id: int
    subject_id: int
    one_to_one_required: bool
    max_consecutive_slots_override: int | None
    allow_gap_override: bool | None

    @property
    def key(self) -> tuple[int, int]:
        return (self.lesson_request_id, self.session_index)


@dataclass(frozen=True, slots=True)
class CandidateData:
    lesson_request_id: int
    session_index: int
    student_id: int
    subject_id: int
    teacher_id: int
    day: date
    time_slot_id: int
    student_availability_level: int
    teacher_availability_level: int

    @property
    def session_key(self) -> tuple[int, int]:
        return (self.lesson_request_id, self.session_index)


@dataclass(frozen=True, slots=True)
class DiagnosticReason:
    code: DiagnosticCode
    message: str
    excluded_candidate_count: int = 0
    details: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SessionCandidateDiagnostics:
    lesson_request_id: int
    session_index: int
    candidate_count: int
    reasons: tuple[DiagnosticReason, ...]

    @property
    def session_key(self) -> tuple[int, int]:
        return (self.lesson_request_id, self.session_index)


@dataclass(frozen=True, slots=True)
class CandidateGenerationResult:
    sessions: tuple[LessonSessionData, ...]
    candidates: tuple[CandidateData, ...]
    diagnostics: tuple[SessionCandidateDiagnostics, ...]
    input_diagnostics: tuple[DiagnosticReason, ...] = ()

    def candidates_for(
        self,
        lesson_request_id: int,
        session_index: int,
    ) -> tuple[CandidateData, ...]:
        key = (lesson_request_id, session_index)
        return tuple(candidate for candidate in self.candidates if candidate.session_key == key)

    def diagnostics_for(
        self,
        lesson_request_id: int,
        session_index: int,
    ) -> SessionCandidateDiagnostics | None:
        key = (lesson_request_id, session_index)
        return next(
            (diagnostic for diagnostic in self.diagnostics if diagnostic.session_key == key),
            None,
        )


@dataclass(frozen=True, slots=True)
class ScheduledAssignment:
    lesson_request_id: int
    session_index: int
    student_id: int
    subject_id: int
    teacher_id: int
    day: date
    time_slot_id: int
    is_locked: bool = False


@dataclass(frozen=True, slots=True)
class UnassignedLesson:
    lesson_request_id: int
    session_index: int
    student_id: int
    subject_id: int
    reasons: tuple[DiagnosticReason, ...]


@dataclass(frozen=True, slots=True)
class ObjectiveBreakdown:
    unassigned_count: int = 0
    teacher_preference_penalty: int = 0
    active_teacher_slot_count: int = 0
    availability_preference_score: int = 0
    changed_assignment_count: int = 0
    optional_balance_score: int = 0


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    solver_status: SolverStatus
    assignments: tuple[ScheduledAssignment, ...]
    unassigned_lessons: tuple[UnassignedLesson, ...]
    objective_breakdown: ObjectiveBreakdown
    elapsed_seconds: float
    warnings: tuple[str, ...] = ()
    cancelled: bool = False


__all__ = [
    "AvailabilityData",
    "AvailabilityOwner",
    "CandidateData",
    "CandidateGenerationResult",
    "DiagnosticCode",
    "DiagnosticReason",
    "ExistingAssignmentData",
    "GroupBlockData",
    "LessonRequestData",
    "LessonSessionData",
    "ObjectiveBreakdown",
    "OptimizationInput",
    "OptimizationResult",
    "OptimizationSettings",
    "ScheduledAssignment",
    "SessionCandidateDiagnostics",
    "SolverStatus",
    "StudentData",
    "SubjectData",
    "TeacherData",
    "TimeSlotData",
    "UnassignedLesson",
]
