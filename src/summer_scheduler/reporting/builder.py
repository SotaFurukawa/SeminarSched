"""帳票種別から共通レイアウトビルダーを選ぶ純粋な窓口。"""

from __future__ import annotations

from typing import Literal

from summer_scheduler.reporting.data import OutputSelection, OutputSnapshot
from summer_scheduler.reporting.issue_builder import build_issues_document
from summer_scheduler.reporting.layout import LayoutDocument
from summer_scheduler.reporting.settings import OutputSettings
from summer_scheduler.reporting.student_builder import build_student_document
from summer_scheduler.reporting.teacher_builder import build_teacher_document
from summer_scheduler.reporting.timetable_builder import build_timetable_document

ReportKind = Literal["overall", "students", "teachers", "issues"]


def build_report_document(
    kind: ReportKind,
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection,
) -> LayoutDocument:
    builders = {
        "overall": build_timetable_document,
        "students": build_student_document,
        "teachers": build_teacher_document,
        "issues": build_issues_document,
    }
    return builders[kind](snapshot, settings, selection)


__all__ = ["ReportKind", "build_report_document"]
