"""Excel・PDF・CSVへ共通で渡す出力ドメイン。"""

from summer_scheduler.reporting.data import (
    AssignmentRecord,
    DateRecord,
    GroupLessonRecord,
    LessonRequestRecord,
    OutputSelection,
    OutputSnapshot,
    ProjectRecord,
    SlotRecord,
    StudentRecord,
    SubjectRecord,
    TeacherRecord,
    UnassignedRecord,
    WarningRecord,
)
from summer_scheduler.reporting.layout import (
    LayoutCell,
    LayoutDocument,
    LayoutPage,
    LayoutRow,
    LayoutSection,
    LayoutTable,
)
from summer_scheduler.reporting.settings import (
    DEFAULT_STYLE_RULES,
    OutputSettings,
    OutputSettingsDefaults,
    OutputSettingsValidationError,
    StyleRule,
)

__all__ = [
    "AssignmentRecord",
    "DEFAULT_STYLE_RULES",
    "DateRecord",
    "GroupLessonRecord",
    "LayoutCell",
    "LayoutDocument",
    "LayoutPage",
    "LayoutRow",
    "LayoutSection",
    "LayoutTable",
    "LessonRequestRecord",
    "OutputSelection",
    "OutputSettings",
    "OutputSettingsDefaults",
    "OutputSettingsValidationError",
    "OutputSnapshot",
    "ProjectRecord",
    "SlotRecord",
    "StudentRecord",
    "StyleRule",
    "SubjectRecord",
    "TeacherRecord",
    "UnassignedRecord",
    "WarningRecord",
]
