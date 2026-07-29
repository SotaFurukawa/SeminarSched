"""Phase 6出力ユースケースがUIへ返す不変DTO。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from summer_scheduler.reporting.builder import ReportKind
from summer_scheduler.reporting.settings import OutputSettings


@dataclass(frozen=True, slots=True)
class OutputDateOptionDto:
    value: date
    label: str
    is_open: bool


@dataclass(frozen=True, slots=True)
class OutputPersonOptionDto:
    id: int
    label: str
    secondary_text: str


@dataclass(frozen=True, slots=True)
class OutputWorkspaceDto:
    project_id: int
    project_title: str
    campus_name: str
    settings: OutputSettings
    dates: tuple[OutputDateOptionDto, ...]
    teachers: tuple[OutputPersonOptionDto, ...]
    students: tuple[OutputPersonOptionDto, ...]
    assignment_count: int
    group_lesson_count: int
    unassigned_count: int
    warning_count: int


@dataclass(frozen=True, slots=True)
class OutputResultDto:
    kind: ReportKind | str
    format: str
    path: Path
    page_count_optional: int | None
    record_count: int


__all__ = [
    "OutputDateOptionDto",
    "OutputPersonOptionDto",
    "OutputResultDto",
    "OutputWorkspaceDto",
]
