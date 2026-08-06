"""生徒別時間割を共通ページレイアウトへ変換する。"""

from __future__ import annotations

from summer_scheduler.reporting.common import (
    chunks,
    format_day,
    group_overlaps_slot,
    pairing_sizes,
    selected_day_set,
    selected_students,
    updated_text,
)
from summer_scheduler.reporting.data import (
    DEFAULT_OUTPUT_SELECTION,
    OutputSelection,
    OutputSnapshot,
    StudentRecord,
)
from summer_scheduler.reporting.layout import (
    LayoutCell,
    LayoutDocument,
    LayoutPage,
    LayoutRow,
    LayoutSection,
    LayoutTable,
)
from summer_scheduler.reporting.person_names import compact_person_name_map
from summer_scheduler.reporting.settings import OutputSettings

_ONE_STUDENT_ROWS_PER_PAGE = 20
_COMBINED_STUDENT_ROWS_PER_TABLE = 9


def build_student_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    settings.validate()
    students = selected_students(snapshot, selection)
    if settings.student_page_mode == "one_per_page":
        pages = tuple(
            LayoutPage(
                heading="生徒別時間割",
                subheading=(
                    f"{student.name}（{student.grade}）"
                    + (f"　{part_index}/{len(parts)}" if len(parts) > 1 else "")
                ),
                tables=(table,),
                footer_note="個人情報を含みます。取扱いに注意してください。",
            )
            for student in students
            for parts in (
                _split_student_table(
                    _student_table(snapshot, settings, selection, student),
                    rows_per_part=_ONE_STUDENT_ROWS_PER_PAGE,
                ),
            )
            for part_index, table in enumerate(parts, start=1)
        )
    else:
        units = tuple(
            (student, part_index, len(parts), table)
            for student in students
            for parts in (
                _split_student_table(
                    _student_table(snapshot, settings, selection, student),
                    rows_per_part=_COMBINED_STUDENT_ROWS_PER_TABLE,
                ),
            )
            for part_index, table in enumerate(parts, start=1)
        )
        pages = tuple(
            LayoutPage(
                heading="生徒別時間割（まとめ）",
                subheading="、".join(
                    student.name + (f" {part_index}/{part_count}" if part_count > 1 else "")
                    for student, part_index, part_count, _ in group
                ),
                tables=tuple(table for _, _, _, table in group),
                footer_note="個人情報を含みます。取扱いに注意してください。",
            )
            for group in chunks(units, 2)
        )
    if not pages:
        pages = (
            LayoutPage(
                heading="生徒別時間割",
                subheading="対象生徒なし",
                tables=(_empty_table("出力対象の生徒がいません"),),
            ),
        )
    return LayoutDocument(
        report_code="students",
        title="生徒別時間割",
        campus_name=snapshot.project.campus_name,
        course_name=snapshot.project.title,
        updated_text=updated_text(snapshot),
        sections=(LayoutSection(name="生徒別時間割", pages=pages),),
        page_size=settings.paper_size,
        orientation=settings.orientation,
        margin_mm=settings.margin_mm,
        font_size=settings.font_size,
        logo_path_optional=settings.logo_path_optional or snapshot.project.logo_path_optional,
    )


def _student_table(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection,
    student: StudentRecord,
) -> LayoutTable:
    requests = {row.id: row for row in snapshot.lesson_requests}
    subjects = {row.id: row for row in snapshot.subjects}
    teachers = {row.id: row for row in snapshot.teachers}
    teacher_display_names = compact_person_name_map(snapshot.teachers)
    slots = {row.id: row for row in snapshot.slots}
    allowed_days = selected_day_set(snapshot, selection)
    allowed_teachers = set(selection.teacher_ids)
    assignments = tuple(
        row
        for row in snapshot.assignments
        if requests[row.lesson_request_id].student_id == student.id
        and row.day in allowed_days
        and (not allowed_teachers or row.teacher_id in allowed_teachers)
    )
    group_lessons = tuple(
        row
        for row in snapshot.group_lessons
        if "group" in settings.visible_fields
        if student.id in row.student_ids
        and row.day in allowed_days
        and (not allowed_teachers or row.teacher_id_optional in allowed_teachers)
    )
    pair_sizes = pairing_sizes(snapshot.assignments)
    missing_count = sum(
        row.missing_sessions for row in snapshot.unassigned if row.student_id == student.id
    )
    rows: list[LayoutRow] = [
        LayoutRow(
            cells=(
                LayoutCell(
                    f"{student.name}　{student.grade}　未配置残数: {missing_count}",
                    role="subtitle",
                    column_span=8,
                ),
            )
        ),
        LayoutRow(
            cells=tuple(
                LayoutCell(value, role="header", alignment="center")
                for value in (
                    "日付",
                    "コマ",
                    "時刻",
                    "科目",
                    "講師",
                    "形式",
                    "備考",
                    "状態",
                )
            )
        ),
    ]
    entries: list[tuple[object, int, LayoutRow]] = []
    for assignment in assignments:
        request = requests[assignment.lesson_request_id]
        subject = subjects[request.subject_id]
        teacher = teachers[assignment.teacher_id]
        slot = slots[assignment.time_slot_id]
        pair_size = pair_sizes[(assignment.day, assignment.time_slot_id, assignment.teacher_id)]
        style_codes: list[str] = []
        state_markers: list[str] = []
        if request.one_to_one_required and "one_to_one" in settings.visible_fields:
            style_codes.append("one_to_one")
            state_markers.append(settings.style("one_to_one").marker)
        if assignment.is_locked and "locked" in settings.visible_fields:
            style_codes.append("locked")
            state_markers.append(settings.style("locked").marker)
        if assignment.is_manual and "manual" in settings.visible_fields:
            style_codes.append("manual")
            state_markers.append(settings.style("manual").marker)
        if snapshot.project.status != "confirmed":
            style_codes.append("unconfirmed")
            state_markers.append(settings.style("unconfirmed").marker)
        entries.append(
            (
                assignment.day,
                slot.sort_order,
                LayoutRow(
                    cells=(
                        LayoutCell(format_day(assignment.day)),
                        LayoutCell(slot.code, alignment="center"),
                        LayoutCell(f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}"),
                        LayoutCell(subject.name if "subject" in settings.visible_fields else "—"),
                        LayoutCell(teacher_display_names[teacher.id]),
                        LayoutCell(
                            ("1対1" if pair_size == 1 else f"1対{pair_size}")
                            if "one_to_one" in settings.visible_fields
                            else "—"
                        ),
                        LayoutCell(
                            "／".join(
                                dict.fromkeys(
                                    value for value in (request.note, assignment.note) if value
                                )
                            )
                            if "note" in settings.visible_fields
                            else "—"
                        ),
                        LayoutCell(
                            "".join(state_markers) or "—",
                            style_codes=tuple(style_codes),
                        ),
                    )
                ),
            )
        )
    for group in group_lessons:
        subject = subjects[group.subject_id]
        overlapping = tuple(
            slot
            for slot in snapshot.slots
            if group_overlaps_slot(
                group_start=group.start_time,
                group_end=group.end_time,
                slot_start=slot.start_time,
                slot_end=slot.end_time,
            )
        )
        slot_text = "/".join(slot.code for slot in overlapping) or "任意"
        sort_order = min((slot.sort_order for slot in overlapping), default=999)
        teacher_name = (
            teacher_display_names[group.teacher_id_optional]
            if group.teacher_id_optional in teachers
            else "担当未設定"
        )
        entries.append(
            (
                group.day,
                sort_order,
                LayoutRow(
                    cells=(
                        LayoutCell(format_day(group.day)),
                        LayoutCell(slot_text, alignment="center"),
                        LayoutCell(f"{group.start_time:%H:%M}–{group.end_time:%H:%M}"),
                        LayoutCell(subject.name if "subject" in settings.visible_fields else "—"),
                        LayoutCell(teacher_name),
                        LayoutCell("集団"),
                        LayoutCell(
                            (group.note or group.room) if "note" in settings.visible_fields else "—"
                        ),
                        LayoutCell(
                            settings.style("group").marker,
                            style_codes=("group",),
                        ),
                    )
                ),
            )
        )
    rows.extend(item[2] for item in sorted(entries, key=lambda item: (item[0], item[1])))
    if not entries:
        rows.append(
            LayoutRow(
                cells=(
                    LayoutCell(
                        "対象期間に配置済み授業はありません",
                        column_span=8,
                        alignment="center",
                    ),
                )
            )
        )
    return LayoutTable(
        rows=tuple(rows),
        column_widths=(14, 7, 13, 14, 16, 9, 24, 18),
        repeat_header_rows=2,
    )


def _empty_table(message: str) -> LayoutTable:
    return LayoutTable(
        rows=(LayoutRow(cells=(LayoutCell(message, alignment="center"),)),),
        column_widths=(80,),
    )


def _split_student_table(
    table: LayoutTable,
    *,
    rows_per_part: int,
) -> tuple[LayoutTable, ...]:
    """長い生徒別一覧を、見出しを保持した読める物理ページへ分割する。"""

    header_count = table.repeat_header_rows
    headers = table.rows[:header_count]
    data_rows = table.rows[header_count:]
    row_chunks = chunks(data_rows, rows_per_part) if data_rows else ((),)
    return tuple(
        LayoutTable(
            rows=(*headers, *row_group),
            column_widths=table.column_widths,
            repeat_header_rows=header_count,
        )
        for row_group in row_chunks
    )


__all__ = ["build_student_document"]
