"""出力ビルダー間で共有する純粋な検索・整形処理。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, time

from summer_scheduler import __release_channel__, __version__
from summer_scheduler.reporting.data import (
    AssignmentRecord,
    DateRecord,
    OutputSelection,
    OutputSnapshot,
    StudentRecord,
    TeacherRecord,
)


def chunks[T](values: Sequence[T], size: int) -> tuple[tuple[T, ...], ...]:
    if size < 1:
        raise ValueError("分割数は1以上で指定してください")
    return tuple(tuple(values[index : index + size]) for index in range(0, len(values), size))


def selected_dates(
    snapshot: OutputSnapshot,
    selection: OutputSelection,
) -> tuple[DateRecord, ...]:
    allowed = set(selection.dates)
    return tuple(row for row in snapshot.dates if not allowed or row.day in allowed)


def selected_teachers(
    snapshot: OutputSnapshot,
    selection: OutputSelection,
) -> tuple[TeacherRecord, ...]:
    allowed = set(selection.teacher_ids)
    referenced = {row.teacher_id for row in snapshot.assignments}
    referenced.update(
        row.teacher_id_optional
        for row in snapshot.group_lessons
        if row.teacher_id_optional is not None
    )
    return tuple(
        row
        for row in snapshot.teachers
        if (not allowed and (row.active or row.id in referenced)) or row.id in allowed
    )


def selected_students(
    snapshot: OutputSnapshot,
    selection: OutputSelection,
) -> tuple[StudentRecord, ...]:
    allowed = set(selection.student_ids)
    requested = {row.student_id for row in snapshot.lesson_requests}
    group_members = {student_id for row in snapshot.group_lessons for student_id in row.student_ids}
    return tuple(
        row
        for row in snapshot.students
        if (not allowed and (row.active or row.id in requested or row.id in group_members))
        or row.id in allowed
    )


def selected_day_set(snapshot: OutputSnapshot, selection: OutputSelection) -> set[date]:
    return {row.day for row in selected_dates(snapshot, selection)}


def pairing_sizes(assignments: Iterable[AssignmentRecord]) -> dict[tuple[date, int, int], int]:
    result: dict[tuple[date, int, int], int] = {}
    for row in assignments:
        key = (row.day, row.time_slot_id, row.teacher_id)
        result[key] = result.get(key, 0) + 1
    return result


def group_overlaps_slot(
    *,
    group_start: time,
    group_end: time,
    slot_start: time,
    slot_end: time,
) -> bool:
    return slot_start < group_end and group_start < slot_end


def format_day(value: date) -> str:
    weekdays = "月火水木金土日"
    return f"{value:%Y/%m/%d}（{weekdays[value.weekday()]}）"


def updated_text(snapshot: OutputSnapshot) -> str:
    generated = snapshot.project.generated_at.astimezone().strftime("%Y/%m/%d %H:%M")
    return f"{generated}／アプリ v{__version__} ({__release_channel__})"


__all__ = [
    "chunks",
    "format_day",
    "group_overlaps_slot",
    "pairing_sizes",
    "selected_dates",
    "selected_day_set",
    "selected_students",
    "selected_teachers",
    "updated_text",
]
