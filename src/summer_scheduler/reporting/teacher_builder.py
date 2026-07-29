"""講師別時間割を共通ページレイアウトへ変換する。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from summer_scheduler.reporting.common import (
    chunks,
    format_day,
    group_overlaps_slot,
    selected_dates,
    selected_students,
    selected_teachers,
    updated_text,
)
from summer_scheduler.reporting.data import (
    DEFAULT_OUTPUT_SELECTION,
    AssignmentRecord,
    DateRecord,
    GroupLessonRecord,
    OutputSelection,
    OutputSnapshot,
    SlotRecord,
    TeacherRecord,
)
from summer_scheduler.reporting.layout import (
    LayoutCell,
    LayoutDocument,
    LayoutPage,
    LayoutRow,
    LayoutSection,
    LayoutTable,
)
from summer_scheduler.reporting.settings import OutputSettings

_GROUP_ROWS_PER_PAGE = 24


def build_teacher_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    settings.validate()
    teachers = selected_teachers(snapshot, selection)
    dates = selected_dates(snapshot, selection)
    date_chunks = chunks(dates, settings.days_per_page) if dates else ((),)
    pages = tuple(
        _teacher_page(
            snapshot,
            settings,
            selection,
            teacher,
            dates=date_chunk,
            period_total_slots=_teacher_total_slots(
                snapshot,
                selection,
                teacher,
                dates=dates,
            ),
        )
        for teacher in teachers
        for date_chunk in date_chunks
    )
    if not pages:
        pages = (
            LayoutPage(
                heading="講師別時間割",
                subheading="対象講師なし",
                tables=(
                    LayoutTable(
                        rows=(
                            LayoutRow(
                                cells=(LayoutCell("出力対象の講師がいません", alignment="center"),)
                            ),
                        ),
                        column_widths=(80,),
                    ),
                ),
            ),
        )
    sections = [LayoutSection(name="講師別時間割", pages=pages)]
    supplemental_pages = _supplemental_group_pages(
        snapshot,
        settings,
        selection,
        teachers=teachers,
        dates=dates,
    )
    if supplemental_pages:
        sections.append(LayoutSection(name="標準コマ外の集団授業", pages=supplemental_pages))
    return LayoutDocument(
        report_code="teachers",
        title="講師別時間割",
        campus_name=snapshot.project.campus_name,
        course_name=snapshot.project.title,
        updated_text=updated_text(snapshot),
        sections=tuple(sections),
        page_size=settings.paper_size,
        orientation=settings.orientation,
        margin_mm=settings.margin_mm,
        font_size=settings.font_size,
        logo_path_optional=settings.logo_path_optional or snapshot.project.logo_path_optional,
    )


def _teacher_page(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection,
    teacher: TeacherRecord,
    *,
    dates: tuple[DateRecord, ...],
    period_total_slots: int,
) -> LayoutPage:
    allowed_days = {row.day for row in dates}
    allowed_students = {row.id for row in selected_students(snapshot, selection)}
    requests = {row.id: row for row in snapshot.lesson_requests}
    students = {row.id: row for row in snapshot.students}
    subjects = {row.id: row for row in snapshot.subjects}
    slots = tuple(row for row in snapshot.slots if row.enabled)
    assignments_by_cell: dict[tuple[date, int], list[AssignmentRecord]] = defaultdict(list)
    for assignment in snapshot.assignments:
        request = requests[assignment.lesson_request_id]
        if (
            assignment.teacher_id == teacher.id
            and assignment.day in allowed_days
            and request.student_id in allowed_students
        ):
            assignments_by_cell[(assignment.day, assignment.time_slot_id)].append(assignment)
    groups_by_cell: dict[tuple[date, int], list[GroupLessonRecord]] = defaultdict(list)
    for group in snapshot.group_lessons:
        if group.teacher_id_optional != teacher.id or group.day not in allowed_days:
            continue
        if selection.student_ids and not (set(group.student_ids) & allowed_students):
            continue
        for slot in slots:
            if group_overlaps_slot(
                group_start=group.start_time,
                group_end=group.end_time,
                slot_start=slot.start_time,
                slot_end=slot.end_time,
            ):
                groups_by_cell[(group.day, slot.id)].append(group)

    occupied: dict[date, set[int]] = defaultdict(set)
    rows: list[LayoutRow] = [
        LayoutRow(
            cells=tuple(
                LayoutCell(value, role="header", alignment="center")
                for value in (
                    "日付",
                    "コマ",
                    "時刻",
                    "生徒1",
                    "学年・科目",
                    "生徒2",
                    "学年・科目",
                    "集団授業",
                )
            )
        )
    ]
    for date_row in dates:
        if not date_row.is_open:
            rows.append(
                LayoutRow(
                    cells=(
                        LayoutCell(
                            f"{settings.style('closed').marker} {format_day(date_row.day)}"
                            f" {date_row.note}",
                            role="closed",
                            column_span=8,
                            style_codes=("closed",),
                            alignment="center",
                        ),
                    )
                )
            )
            continue
        for slot in slots:
            assignments = sorted(
                assignments_by_cell.get((date_row.day, slot.id), ()),
                key=lambda row: (row.lesson_request_id, row.session_index),
            )
            groups = groups_by_cell.get((date_row.day, slot.id), ())
            if assignments or groups:
                occupied[date_row.day].add(slot.sort_order)
            student_cells: list[LayoutCell] = []
            for index in range(2):
                if index < len(assignments):
                    assignment = assignments[index]
                    request = requests[assignment.lesson_request_id]
                    student = students[request.student_id]
                    subject = subjects[request.subject_id]
                    codes: list[str] = []
                    markers: list[str] = []
                    if request.one_to_one_required and "one_to_one" in settings.visible_fields:
                        codes.append("one_to_one")
                        markers.append(settings.style("one_to_one").marker)
                    if assignment.is_locked and "locked" in settings.visible_fields:
                        codes.append("locked")
                        markers.append(settings.style("locked").marker)
                    if assignment.is_manual and "manual" in settings.visible_fields:
                        codes.append("manual")
                        markers.append(settings.style("manual").marker)
                    marker = "".join(markers)
                    student_cells.extend(
                        (
                            LayoutCell(
                                f"{marker}{student.name}",
                                style_codes=tuple(codes),
                            ),
                            LayoutCell(
                                "・".join(
                                    value
                                    for value in (
                                        student.grade if "grade" in settings.visible_fields else "",
                                        subject.name
                                        if "subject" in settings.visible_fields
                                        else "",
                                    )
                                    if value
                                )
                                or "—",
                                style_codes=tuple(codes),
                            ),
                        )
                    )
                else:
                    student_cells.extend((LayoutCell("—"), LayoutCell("—")))
            group_text = (
                "\n".join(
                    f"{settings.style('group').marker} "
                    f"{group.course_name or group.group_code} "
                    f"{group.start_time:%H:%M}–{group.end_time:%H:%M}"
                    for group in groups
                )
                if "group" in settings.visible_fields
                else ""
            )
            if len(assignments) > 2:
                group_text = (
                    f"{group_text}\n" if group_text else ""
                ) + f"{settings.style('warning').marker} 定員超過"
            rows.append(
                LayoutRow(
                    cells=(
                        LayoutCell(format_day(date_row.day)),
                        LayoutCell(slot.code, alignment="center"),
                        LayoutCell(f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}"),
                        *student_cells,
                        LayoutCell(
                            group_text or "—",
                            style_codes=(
                                ("warning",)
                                if len(assignments) > 2
                                else ("group",)
                                if groups
                                else ()
                            ),
                        ),
                    )
                )
            )
    total_slots = sum(len(values) for values in occupied.values())
    range_text = (
        "／".join(
            f"{format_day(day)}: {_ranges(values, slots)}"
            for day, values in sorted(occupied.items())
        )
        or "稼働なし"
    )
    rows.append(
        LayoutRow(
            cells=(
                LayoutCell(
                    f"連続勤務範囲　{range_text}　　合計稼働コマ数　{period_total_slots}"
                    + (
                        f"（このページ {total_slots}）" if total_slots != period_total_slots else ""
                    ),
                    role="metadata",
                    column_span=8,
                ),
            )
        )
    )
    return LayoutPage(
        heading="講師別時間割",
        subheading=(
            f"{teacher.name}／{format_day(dates[0].day)} ～ {format_day(dates[-1].day)}"
            if dates
            else f"{teacher.name}／対象日なし"
        ),
        tables=(
            LayoutTable(
                rows=tuple(rows),
                column_widths=(14, 7, 13, 16, 16, 16, 16, 22),
                repeat_header_rows=1,
            ),
        ),
        footer_note="合計稼働コマ数は、生徒数ではなく日付×コマの重複を除いて集計します。",
    )


def _teacher_total_slots(
    snapshot: OutputSnapshot,
    selection: OutputSelection,
    teacher: TeacherRecord,
    *,
    dates: tuple[DateRecord, ...],
) -> int:
    allowed_days = {row.day for row in dates}
    allowed_students = {row.id for row in selected_students(snapshot, selection)}
    requests = {row.id: row for row in snapshot.lesson_requests}
    occupied = {
        (row.day, row.time_slot_id)
        for row in snapshot.assignments
        if row.teacher_id == teacher.id
        and row.day in allowed_days
        and requests[row.lesson_request_id].student_id in allowed_students
    }
    for group in snapshot.group_lessons:
        if group.teacher_id_optional != teacher.id or group.day not in allowed_days:
            continue
        if selection.student_ids and not (set(group.student_ids) & allowed_students):
            continue
        for slot in snapshot.slots:
            if slot.enabled and group_overlaps_slot(
                group_start=group.start_time,
                group_end=group.end_time,
                slot_start=slot.start_time,
                slot_end=slot.end_time,
            ):
                occupied.add((group.day, slot.id))
    return len(occupied)


def _supplemental_group_pages(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection,
    *,
    teachers: tuple[TeacherRecord, ...],
    dates: tuple[DateRecord, ...],
) -> tuple[LayoutPage, ...]:
    if "group" not in settings.visible_fields:
        return ()
    allowed_teachers = {row.id for row in teachers}
    allowed_students = {row.id for row in selected_students(snapshot, selection)}
    dates_by_day = {row.day: row for row in dates}
    slots = tuple(row for row in snapshot.slots if row.enabled)
    rows: list[tuple[GroupLessonRecord, str]] = []
    for group in snapshot.group_lessons:
        if group.teacher_id_optional not in allowed_teachers or group.day not in dates_by_day:
            continue
        if selection.student_ids and not (set(group.student_ids) & allowed_students):
            continue
        if not dates_by_day[group.day].is_open:
            rows.append((group, "休校日の固定授業"))
            continue
        if not any(
            group_overlaps_slot(
                group_start=group.start_time,
                group_end=group.end_time,
                slot_start=slot.start_time,
                slot_end=slot.end_time,
            )
            for slot in slots
        ):
            rows.append((group, "標準コマ外"))
    if not rows:
        return ()

    teacher_by_id: dict[int | None, TeacherRecord] = {row.id: row for row in snapshot.teachers}
    subjects = {row.id: row for row in snapshot.subjects}
    row_chunks = chunks(tuple(rows), _GROUP_ROWS_PER_PAGE)
    return tuple(
        LayoutPage(
            heading="標準コマ外の集団授業",
            subheading=f"講師別の標準コマ表へ表示できない固定授業 {len(rows)}件",
            tables=(
                LayoutTable(
                    rows=(
                        LayoutRow(
                            cells=tuple(
                                LayoutCell(value, role="header", alignment="center")
                                for value in (
                                    "講師",
                                    "日付",
                                    "実時刻",
                                    "コード",
                                    "講座",
                                    "学年・科目",
                                    "理由",
                                    "教室・備考",
                                )
                            )
                        ),
                        *(
                            LayoutRow(
                                cells=(
                                    LayoutCell(teacher_by_id[group.teacher_id_optional].name),
                                    LayoutCell(format_day(group.day)),
                                    LayoutCell(f"{group.start_time:%H:%M}–{group.end_time:%H:%M}"),
                                    LayoutCell(group.group_code),
                                    LayoutCell(group.course_name),
                                    LayoutCell(
                                        "・".join(
                                            value
                                            for value in (
                                                group.grade,
                                                subjects[group.subject_id].name,
                                            )
                                            if value
                                        )
                                    ),
                                    LayoutCell(reason),
                                    LayoutCell(
                                        "／".join(
                                            value for value in (group.room, group.note) if value
                                        )
                                    ),
                                )
                            )
                            for group, reason in row_group
                        ),
                    ),
                    column_widths=(15, 13, 12, 11, 20, 16, 15, 25),
                    repeat_header_rows=1,
                ),
            ),
            footer_note=(
                "合計稼働コマ数には標準コマへ対応しない固定授業を含めません。"
                "実時刻を確認してください。"
            ),
        )
        for row_group in row_chunks
    )


def _ranges(sort_orders: set[int], slots: tuple[SlotRecord, ...]) -> str:
    codes = {slot.sort_order: slot.code for slot in slots}
    ordered = sorted(sort_orders)
    if not ordered:
        return "なし"
    groups: list[list[int]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value == groups[-1][-1] + 1:
            groups[-1].append(value)
        else:
            groups.append([value])
    return "、".join(
        codes[group[0]] if len(group) == 1 else f"{codes[group[0]]}–{codes[group[-1]]}"
        for group in groups
    )


__all__ = ["build_teacher_document"]
