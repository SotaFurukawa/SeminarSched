"""割当て生データをExcelで開きやすい18列CSVへ変換する。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Final

from summer_scheduler.infrastructure.exporting.atomic_output import atomic_output_path
from summer_scheduler.infrastructure.exporting.errors import OutputDataError, OutputRenderError
from summer_scheduler.reporting.common import group_overlaps_slot
from summer_scheduler.reporting.data import (
    GroupLessonRecord,
    OutputSelection,
    OutputSnapshot,
)

ASSIGNMENT_CSV_COLUMNS: Final = (
    "project",
    "campus",
    "date",
    "slot",
    "start_time",
    "end_time",
    "teacher_id",
    "teacher_name",
    "student_id",
    "student_name",
    "grade",
    "subject_code",
    "subject_name",
    "one_to_one_required",
    "is_locked",
    "is_manual",
    "group_lesson",
    "note",
)
_TEXT_ID_COLUMNS: Final = frozenset({"teacher_id", "student_id"})


@dataclass(frozen=True, slots=True)
class _CsvRow:
    day: date
    start_time: time
    slot_sort_order: int
    teacher_external_id: str
    student_external_id: str
    group_code: str
    values: tuple[str, ...]


class CsvRenderer:
    """現在の個別Assignmentと固定集団授業を情報欠落なくCSV化する。"""

    def render(
        self,
        snapshot: OutputSnapshot,
        destination: Path,
        *,
        selection: OutputSelection | None = None,
        with_bom: bool = True,
        overwrite: bool = False,
    ) -> Path:
        target = _require_csv_suffix(destination)
        rows = self._rows(snapshot, selection or OutputSelection())
        encoding = "utf-8-sig" if with_bom else "utf-8"
        with atomic_output_path(target, overwrite=overwrite) as temporary:
            try:
                with temporary.open("w", encoding=encoding, newline="") as stream:
                    writer = csv.writer(stream, lineterminator="\r\n")
                    writer.writerow(ASSIGNMENT_CSV_COLUMNS)
                    writer.writerows(
                        tuple(
                            _safe_csv_text(
                                value,
                                preserve_numeric_text=column in _TEXT_ID_COLUMNS,
                            )
                            for column, value in zip(
                                ASSIGNMENT_CSV_COLUMNS,
                                row.values,
                                strict=True,
                            )
                        )
                        for row in rows
                    )
            except PermissionError:
                raise
            except OSError:
                raise
            except Exception as exc:
                raise OutputRenderError("割当てCSVの生成に失敗しました") from exc
        return target.expanduser().resolve()

    def _rows(
        self,
        snapshot: OutputSnapshot,
        selection: OutputSelection,
    ) -> tuple[_CsvRow, ...]:
        dates = set(selection.dates)
        teacher_ids = set(selection.teacher_ids)
        student_ids = set(selection.student_ids)
        slots = {row.id: row for row in snapshot.slots}
        students = {row.id: row for row in snapshot.students}
        teachers = {row.id: row for row in snapshot.teachers}
        subjects = {row.id: row for row in snapshot.subjects}
        requests = {row.id: row for row in snapshot.lesson_requests}
        rows: list[_CsvRow] = []

        for assignment in snapshot.assignments:
            request = requests.get(assignment.lesson_request_id)
            if request is None:
                raise OutputDataError(
                    f"割当ID {assignment.id} の受講希望が見つからないためCSVを生成できません"
                )
            if dates and assignment.day not in dates:
                continue
            if teacher_ids and assignment.teacher_id not in teacher_ids:
                continue
            if student_ids and request.student_id not in student_ids:
                continue
            slot = slots.get(assignment.time_slot_id)
            student = students.get(request.student_id)
            teacher = teachers.get(assignment.teacher_id)
            subject = subjects.get(request.subject_id)
            if slot is None or student is None or teacher is None or subject is None:
                raise OutputDataError(
                    f"割当ID {assignment.id} の参照先が不足しているためCSVを生成できません"
                )
            rows.append(
                _CsvRow(
                    day=assignment.day,
                    start_time=slot.start_time,
                    slot_sort_order=slot.sort_order,
                    teacher_external_id=teacher.external_id,
                    student_external_id=student.external_id,
                    group_code="",
                    values=(
                        snapshot.project.title,
                        snapshot.project.campus_name,
                        assignment.day.isoformat(),
                        slot.code,
                        slot.start_time.strftime("%H:%M"),
                        slot.end_time.strftime("%H:%M"),
                        teacher.external_id,
                        teacher.name,
                        student.external_id,
                        student.name,
                        student.grade,
                        subject.code,
                        subject.name,
                        _bool_text(request.one_to_one_required),
                        _bool_text(assignment.is_locked),
                        _bool_text(assignment.is_manual),
                        "",
                        assignment.note,
                    ),
                )
            )

        for group in snapshot.group_lessons:
            if dates and group.day not in dates:
                continue
            if teacher_ids and group.teacher_id_optional not in teacher_ids:
                continue
            subject = subjects.get(group.subject_id)
            if subject is None:
                raise OutputDataError(
                    f"集団授業「{group.group_code}」の科目が見つからないためCSVを生成できません"
                )
            teacher = (
                teachers.get(group.teacher_id_optional)
                if group.teacher_id_optional is not None
                else None
            )
            if group.teacher_id_optional is not None and teacher is None:
                raise OutputDataError(
                    f"集団授業「{group.group_code}」の講師が見つからないためCSVを生成できません"
                )
            participant_ids: tuple[int | None, ...]
            if group.student_ids:
                participant_ids = tuple(
                    student_id
                    for student_id in group.student_ids
                    if not student_ids or student_id in student_ids
                )
            elif student_ids:
                participant_ids = ()
            else:
                participant_ids = (None,)
            for student_id in participant_ids:
                student = students.get(student_id) if student_id is not None else None
                if student_id is not None and student is None:
                    raise OutputDataError(
                        f"集団授業「{group.group_code}」の生徒が見つからないためCSVを生成できません"
                    )
                rows.append(
                    self._group_row(
                        snapshot,
                        group,
                        subject_code=subject.code,
                        subject_name=subject.name,
                        teacher_external_id=teacher.external_id if teacher is not None else "",
                        teacher_name=teacher.name if teacher is not None else "",
                        student_external_id=student.external_id if student is not None else "",
                        student_name=student.name if student is not None else "",
                        grade=student.grade if student is not None else group.grade,
                    )
                )

        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    row.day,
                    row.start_time,
                    row.slot_sort_order,
                    row.teacher_external_id,
                    row.student_external_id,
                    row.group_code,
                ),
            )
        )

    @staticmethod
    def _group_row(
        snapshot: OutputSnapshot,
        group: GroupLessonRecord,
        *,
        subject_code: str,
        subject_name: str,
        teacher_external_id: str,
        teacher_name: str,
        student_external_id: str,
        student_name: str,
        grade: str,
    ) -> _CsvRow:
        overlapping = tuple(
            slot
            for slot in sorted(snapshot.slots, key=lambda row: (row.sort_order, row.id))
            if slot.enabled
            and group_overlaps_slot(
                group_start=group.start_time,
                group_end=group.end_time,
                slot_start=slot.start_time,
                slot_end=slot.end_time,
            )
        )
        slot_text = "/".join(slot.code for slot in overlapping)
        slot_sort_order = overlapping[0].sort_order if overlapping else 1_000_000
        note_parts = [
            value
            for value in (
                group.course_name,
                f"教室: {group.room}" if group.room else "",
                group.note,
            )
            if value
        ]
        return _CsvRow(
            day=group.day,
            start_time=group.start_time,
            slot_sort_order=slot_sort_order,
            teacher_external_id=teacher_external_id,
            student_external_id=student_external_id,
            group_code=group.group_code,
            values=(
                snapshot.project.title,
                snapshot.project.campus_name,
                group.day.isoformat(),
                slot_text,
                group.start_time.strftime("%H:%M"),
                group.end_time.strftime("%H:%M"),
                teacher_external_id,
                teacher_name,
                student_external_id,
                student_name,
                grade,
                subject_code,
                subject_name,
                "false",
                "true",
                "false",
                group.group_code,
                "／".join(note_parts),
            ),
        )


def _safe_csv_text(value: str, *, preserve_numeric_text: bool = False) -> str:
    """Excelで文字列として扱う値へ既存のapostrophe保護を適用する。

    生徒・講師IDは数字だけでも識別子であり、Excelの自動型変換による先頭ゼロ消失や
    桁丸めを避ける。日付、時刻等の通常列にはこの数値文字列保護を適用しない。
    """

    without_controls = value.lstrip(" \t\r\n")
    numeric_identifier = (
        preserve_numeric_text and without_controls.isascii() and without_controls.isdecimal()
    )
    if without_controls.startswith(("=", "+", "-", "@")) or numeric_identifier:
        return f"'{value}"
    return value


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _require_csv_suffix(path: Path) -> Path:
    if path.suffix.casefold() != ".csv":
        raise OutputRenderError("出力ファイルの拡張子は.csvを指定してください")
    return path


__all__ = ["ASSIGNMENT_CSV_COLUMNS", "CsvRenderer"]
