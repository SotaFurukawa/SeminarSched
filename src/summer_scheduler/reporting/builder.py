"""帳票種別から共通レイアウトビルダーを選ぶ純粋な窓口。"""

from __future__ import annotations

from typing import Literal

from summer_scheduler.reporting.data import OutputSelection, OutputSnapshot
from summer_scheduler.reporting.distribution_builder import (
    build_student_handout_document,
    build_student_schedule_document,
    build_teacher_handout_document,
    build_teacher_packet_document,
)
from summer_scheduler.reporting.issue_builder import build_issues_document
from summer_scheduler.reporting.layout import LayoutDocument
from summer_scheduler.reporting.settings import OutputSettings
from summer_scheduler.reporting.teacher_builder import build_teacher_document
from summer_scheduler.reporting.timetable_builder import build_timetable_document

ReportKind = Literal[
    "overall",
    "students",
    "teachers",
    "issues",
    "student_handouts",
    "teacher_handouts",
    "teacher_packets",
]


def build_report_document(
    kind: ReportKind,
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection,
) -> LayoutDocument:
    builders = {
        "overall": build_timetable_document,
        "students": build_student_schedule_document,
        "teachers": build_teacher_document,
        "issues": build_issues_document,
        "student_handouts": build_student_handout_document,
        "teacher_handouts": build_teacher_handout_document,
        "teacher_packets": build_teacher_packet_document,
    }
    return builders[kind](snapshot, settings, selection)


__all__ = ["ReportKind", "build_report_document"]
