"""全体時間割を共通ページレイアウトへ変換する。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from summer_scheduler.reporting.common import (
    chunks,
    format_day,
    group_overlaps_slot,
    selected_dates,
    selected_teachers,
    updated_text,
)
from summer_scheduler.reporting.data import (
    DEFAULT_OUTPUT_SELECTION,
    AssignmentRecord,
    DateRecord,
    GroupLessonRecord,
    LessonRequestRecord,
    OutputSelection,
    OutputSnapshot,
    SlotRecord,
    StudentRecord,
    SubjectRecord,
    TeacherRecord,
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
from summer_scheduler.reporting.settings import OutputSettings

_GROUP_ROWS_PER_PAGE = 24


def build_timetable_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    """日付×講師を設定値で分割し、情報を失わない全体時間割を作る。"""
    settings.validate()
    dates = selected_dates(snapshot, selection)
    teachers = selected_teachers(snapshot, selection)
    slots = tuple(row for row in snapshot.slots if row.enabled)
    date_chunks = chunks(dates, settings.days_per_page) if dates else ((),)
    teacher_chunks = chunks(teachers, settings.teacher_columns_per_page) if teachers else ((),)

    sections: list[LayoutSection] = []
    for teacher_chunk_index, teacher_chunk in enumerate(teacher_chunks, start=1):
        pages = tuple(
            _build_page(
                snapshot,
                settings,
                date_chunk,
                teacher_chunk,
                slots,
                selection,
            )
            for date_chunk in date_chunks
        )
        section_name = (
            "全体時間割" if len(teacher_chunks) == 1 else f"全体時間割_{teacher_chunk_index:02d}"
        )
        sections.append(LayoutSection(name=section_name, pages=pages))

    supplemental_group_pages = _supplemental_group_pages(
        snapshot,
        settings,
        selection,
        slots=slots,
    )
    if supplemental_group_pages:
        sections.append(LayoutSection(name="補足の集団授業", pages=supplemental_group_pages))

    return LayoutDocument(
        report_code="overall",
        title="夏期講習時間割",
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


def _build_page(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    dates: Sequence[DateRecord],
    teachers: Sequence[TeacherRecord],
    slots: Sequence[SlotRecord],
    selection: OutputSelection,
) -> LayoutPage:
    requests = {row.id: row for row in snapshot.lesson_requests}
    students = {row.id: row for row in snapshot.students}
    subjects = {row.id: row for row in snapshot.subjects}
    assignments_by_cell: dict[tuple[object, int, int], list[AssignmentRecord]] = defaultdict(list)
    allowed_students = set(selection.student_ids)
    for assignment in snapshot.assignments:
        request = requests[assignment.lesson_request_id]
        if allowed_students and request.student_id not in allowed_students:
            continue
        assignments_by_cell[
            (assignment.day, assignment.time_slot_id, assignment.teacher_id)
        ].append(assignment)
    groups_by_cell: dict[tuple[object, int, int], list[GroupLessonRecord]] = defaultdict(list)
    for group in snapshot.group_lessons if "group" in settings.visible_fields else ():
        if group.teacher_id_optional is None:
            continue
        if allowed_students and not (set(group.student_ids) & allowed_students):
            continue
        for slot in slots:
            if group_overlaps_slot(
                group_start=group.start_time,
                group_end=group.end_time,
                slot_start=slot.start_time,
                slot_end=slot.end_time,
            ):
                groups_by_cell[(group.day, slot.id, group.teacher_id_optional)].append(group)

    rows = [
        LayoutRow(
            cells=(
                LayoutCell("日付", role="header", alignment="center"),
                LayoutCell("コマ・時刻", role="header", alignment="center"),
                *(
                    LayoutCell(teacher.name, role="header", alignment="center")
                    for teacher in teachers
                ),
            )
        )
    ]
    for date_row in dates:
        if not date_row.is_open:
            note = f"　{date_row.note}" if date_row.note else ""
            rows.append(
                LayoutRow(
                    cells=(
                        LayoutCell(
                            f"{settings.style('closed').marker} {format_day(date_row.day)}{note}",
                            role="closed",
                            column_span=2 + len(teachers),
                            style_codes=("closed",),
                            alignment="center",
                        ),
                    ),
                    height_points_optional=26,
                )
            )
            continue
        for slot_index, slot in enumerate(slots):
            day_cell = (
                (
                    LayoutCell(
                        format_day(date_row.day)
                        + (
                            f"\n特記事項: {date_row.note}"
                            if date_row.note and "note" in settings.visible_fields
                            else ""
                        ),
                        role="metadata",
                        row_span=max(1, len(slots)),
                        alignment="center",
                    ),
                )
                if slot_index == 0
                else ()
            )
            cells: list[LayoutCell] = [
                *day_cell,
                LayoutCell(
                    f"{slot.code} {slot.start_time:%H:%M}–{slot.end_time:%H:%M}",
                    role="metadata",
                    alignment="center",
                ),
            ]
            for teacher in teachers:
                key = (date_row.day, slot.id, teacher.id)
                assignments = assignments_by_cell.get(key, ())
                text, codes = _cell_content(
                    assignments,
                    groups_by_cell.get(key, ()),
                    requests=requests,
                    students=students,
                    subjects=subjects,
                    settings=settings,
                    project_confirmed=snapshot.project.status == "confirmed",
                    warnings=_matching_warnings(
                        snapshot.warnings,
                        day=date_row.day,
                        slot_code=slot.code,
                        teacher=teacher,
                        assignments=assignments,
                        requests=requests,
                        students=students,
                    ),
                )
                cells.append(
                    LayoutCell(
                        text or "—",
                        style_codes=codes,
                        alignment="left",
                    )
                )
            rows.append(LayoutRow(cells=tuple(cells), height_points_optional=42))

    legend = "　".join(
        f"{rule.marker} {rule.label}"
        for rule in settings.style_rules
        if rule.code in {"unconfirmed", "closed"} or rule.code in settings.visible_fields
    )
    rows.append(
        LayoutRow(
            cells=(
                LayoutCell(
                    f"凡例　{legend}",
                    role="legend",
                    column_span=2 + len(teachers),
                ),
            )
        )
    )
    column_widths = (13.0, 13.0, *(19.0 for _ in teachers))
    date_text = (
        f"{format_day(dates[0].day)} ～ {format_day(dates[-1].day)}" if dates else "対象日なし"
    )
    teacher_text = "、".join(row.name for row in teachers) or "対象講師なし"
    return LayoutPage(
        heading="夏期講習時間割",
        subheading=f"{date_text}／講師: {teacher_text}",
        tables=(
            LayoutTable(
                rows=tuple(rows),
                column_widths=column_widths,
                repeat_header_rows=1,
            ),
        ),
        footer_note="個別授業は各講師・各コマ最大2名。色と文字記号を併記しています。",
    )


def _cell_content(
    assignments: Sequence[AssignmentRecord],
    groups: Sequence[GroupLessonRecord],
    *,
    requests: dict[int, LessonRequestRecord],
    students: dict[int, StudentRecord],
    subjects: dict[int, SubjectRecord],
    settings: OutputSettings,
    project_confirmed: bool,
    warnings: Sequence[WarningRecord],
) -> tuple[str, tuple[str, ...]]:
    lines: list[str] = []
    style_codes: list[str] = []
    for group in groups:
        subject = subjects[group.subject_id]
        details = [
            group.course_name or group.group_code,
            f"{group.start_time:%H:%M}–{group.end_time:%H:%M}",
        ]
        if "grade" in settings.visible_fields:
            details.append(group.grade)
        if "subject" in settings.visible_fields:
            details.append(subject.name)
        if "note" in settings.visible_fields:
            details.extend(value for value in (group.room, group.note) if value)
        lines.append(f"{settings.style('group').marker} {'／'.join(details)}")
        style_codes.append("group")
    ordered = sorted(assignments, key=lambda row: (row.lesson_request_id, row.session_index))
    for index, assignment in enumerate(ordered, start=1):
        request = requests[assignment.lesson_request_id]
        student = students[request.student_id]
        subject = subjects[request.subject_id]
        markers: list[str] = []
        if request.one_to_one_required and "one_to_one" in settings.visible_fields:
            markers.append(settings.style("one_to_one").marker)
            style_codes.append("one_to_one")
        if assignment.is_locked and "locked" in settings.visible_fields:
            markers.append(settings.style("locked").marker)
            style_codes.append("locked")
        if assignment.is_manual and "manual" in settings.visible_fields:
            markers.append(settings.style("manual").marker)
            style_codes.append("manual")
        if not project_confirmed:
            markers.append(settings.style("unconfirmed").marker)
            style_codes.append("unconfirmed")
        prefix = "".join(markers)
        details = [f"{index}. {prefix}{student.name}"]
        if "grade" in settings.visible_fields:
            details.append(student.grade)
        if "subject" in settings.visible_fields:
            details.append(subject.name)
        if "note" in settings.visible_fields:
            note = "／".join(value for value in (request.note, assignment.note) if value)
            if note:
                details.append(f"備考: {note}")
        lines.append("／".join(details))
    if len(ordered) > 2 and "warning" in settings.visible_fields:
        lines.append(f"{settings.style('warning').marker} 3名以上の割当を検出")
        style_codes.append("warning")
    if warnings and "warning" in settings.visible_fields:
        unique_contents = tuple(dict.fromkeys(row.content for row in warnings if row.content))
        detail = f" {'／'.join(unique_contents[:2])}" if unique_contents else ""
        lines.append(f"{settings.style('warning').marker}{detail}")
        style_codes.append("warning")
    return "\n".join(lines), tuple(dict.fromkeys(style_codes))


def _supplemental_group_pages(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection,
    *,
    slots: Sequence[SlotRecord],
) -> tuple[LayoutPage, ...]:
    if "group" not in settings.visible_fields:
        return ()
    dates = selected_dates(snapshot, selection)
    dates_by_day = {row.day: row for row in dates}
    allowed_dates = set(dates_by_day)
    allowed_teachers = {row.id for row in selected_teachers(snapshot, selection)}
    allowed_students = set(selection.student_ids)
    supplemental: list[tuple[GroupLessonRecord, str]] = []
    for row in snapshot.group_lessons:
        if row.day not in allowed_dates:
            continue
        if allowed_students and not (set(row.student_ids) & allowed_students):
            continue
        if row.teacher_id_optional is not None and row.teacher_id_optional not in allowed_teachers:
            continue
        date_row = dates_by_day[row.day]
        if row.teacher_id_optional is None:
            if selection.teacher_ids:
                continue
            reason = "担当講師未設定"
        elif not date_row.is_open:
            reason = "休校日の固定授業"
        elif any(
            group_overlaps_slot(
                group_start=row.start_time,
                group_end=row.end_time,
                slot_start=slot.start_time,
                slot_end=slot.end_time,
            )
            for slot in slots
        ):
            continue
        else:
            reason = "標準コマ外"
        supplemental.append((row, reason))
    if not supplemental:
        return ()

    subjects = {row.id: row for row in snapshot.subjects}
    teachers = {row.id: row for row in snapshot.teachers}
    row_chunks = chunks(tuple(supplemental), _GROUP_ROWS_PER_PAGE)
    return tuple(
        _supplemental_group_page(
            group,
            total_count=len(supplemental),
            subjects=subjects,
            teachers=teachers,
        )
        for group in row_chunks
    )


def _supplemental_group_page(
    rows: Sequence[tuple[GroupLessonRecord, str]],
    *,
    total_count: int,
    subjects: dict[int, SubjectRecord],
    teachers: dict[int, TeacherRecord],
) -> LayoutPage:
    table_rows = [
        LayoutRow(
            cells=tuple(
                LayoutCell(value, role="header", alignment="center")
                for value in (
                    "日付",
                    "実時刻",
                    "コード",
                    "講座",
                    "学年",
                    "科目",
                    "講師",
                    "理由",
                    "教室・備考",
                )
            )
        )
    ]
    table_rows.extend(
        LayoutRow(
            cells=(
                LayoutCell(format_day(group.day)),
                LayoutCell(f"{group.start_time:%H:%M}–{group.end_time:%H:%M}"),
                LayoutCell(group.group_code),
                LayoutCell(group.course_name),
                LayoutCell(group.grade),
                LayoutCell(subjects[group.subject_id].name),
                LayoutCell(
                    teachers[group.teacher_id_optional].name
                    if group.teacher_id_optional in teachers
                    else "未設定"
                ),
                LayoutCell(reason),
                LayoutCell("／".join(value for value in (group.room, group.note) if value)),
            )
        )
        for group, reason in rows
    )
    return LayoutPage(
        heading="補足の集団授業",
        subheading=f"標準コマ表へ表示できない固定授業 {total_count}件",
        tables=(
            LayoutTable(
                rows=tuple(table_rows),
                column_widths=(13, 12, 11, 18, 10, 12, 14, 15, 24),
                repeat_header_rows=1,
            ),
        ),
        footer_note=(
            "担当講師未設定、標準コマ外、または休校日の固定授業です。実時刻を確認してください。"
        ),
    )


def _matching_warnings(
    warnings: Sequence[WarningRecord],
    *,
    day: date,
    slot_code: str,
    teacher: TeacherRecord,
    assignments: Sequence[AssignmentRecord],
    requests: dict[int, LessonRequestRecord],
    students: dict[int, StudentRecord],
) -> tuple[WarningRecord, ...]:
    student_names = {
        students[requests[row.lesson_request_id].student_id].name for row in assignments
    }
    student_ids = {requests[row.lesson_request_id].student_id for row in assignments}
    return tuple(
        row
        for row in warnings
        if row.teacher_id_optional is not None
        or row.teacher_name
        or row.student_ids
        or row.student_name
        if row.day_optional == day
        and (not row.slot_code or row.slot_code == slot_code)
        and (
            row.teacher_id_optional == teacher.id
            if row.teacher_id_optional is not None
            else not row.teacher_name or row.teacher_name == teacher.name
        )
        and (
            bool(set(row.student_ids) & student_ids)
            if row.student_ids
            else not row.student_name or row.student_name in student_names
        )
    )


__all__ = ["build_timetable_document"]
