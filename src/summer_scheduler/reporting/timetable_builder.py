"""全体時間割を共通ページレイアウトへ変換する。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

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
from summer_scheduler.reporting.person_names import compact_person_name_map
from summer_scheduler.reporting.settings import OutputSettings

_GROUP_ROWS_PER_PAGE = 24
_TEACHERS_PER_DATE_PANEL = 4
_PANEL_COLUMN_COUNT = 1 + _TEACHERS_PER_DATE_PANEL
_WEEK_TABLE_COLUMN_COUNT = _PANEL_COLUMN_COUNT * 2 + 1


@dataclass(frozen=True, slots=True)
class _PanelContext:
    slots: Sequence[SlotRecord]
    availability: dict[tuple[date, int, int], int]
    assignments_by_cell: dict[tuple[date, int, int], list[AssignmentRecord]]
    groups_by_cell: dict[tuple[date, int, int], list[GroupLessonRecord]]
    requests: dict[int, LessonRequestRecord]
    students: dict[int, StudentRecord]
    student_display_names: dict[int, str]
    teacher_display_names: dict[int, str]
    subjects: dict[int, SubjectRecord]
    settings: OutputSettings
    snapshot: OutputSnapshot


def build_timetable_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    """日曜始まりの週ごとに、日別の出勤講師だけを載せた時間割を作る。"""
    settings.validate()
    dates = selected_dates(snapshot, selection)
    slots = tuple(row for row in snapshot.slots if row.enabled)
    weeks: dict[date, list[DateRecord]] = defaultdict(list)
    for row in dates:
        weeks[_sunday_of_week(row.day)].append(row)
    if not weeks:
        weeks[snapshot.project.start_date] = []

    sections = [
        LayoutSection(
            name=f"週_{week_start:%Y%m%d}",
            pages=(
                _build_week_page(
                    snapshot,
                    settings,
                    tuple(week_dates),
                    slots,
                    selection,
                    week_start=week_start,
                ),
            ),
        )
        for week_start, week_dates in sorted(weeks.items())
    ]

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
        title="季節講習時間割",
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


def _build_week_page(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    dates: Sequence[DateRecord],
    slots: Sequence[SlotRecord],
    selection: OutputSelection,
    *,
    week_start: date,
) -> LayoutPage:
    requests = {row.id: row for row in snapshot.lesson_requests}
    students = {row.id: row for row in snapshot.students}
    student_display_names = compact_person_name_map(snapshot.students)
    teacher_display_names = compact_person_name_map(snapshot.teachers)
    teachers = selected_teachers(snapshot, selection)
    teachers_by_id = {row.id: row for row in teachers}
    allowed_teacher_ids = set(teachers_by_id)
    subjects = {row.id: row for row in snapshot.subjects}
    assignments_by_cell: dict[tuple[date, int, int], list[AssignmentRecord]] = defaultdict(list)
    allowed_students = set(selection.student_ids)
    for assignment in snapshot.assignments:
        request = requests[assignment.lesson_request_id]
        if allowed_students and request.student_id not in allowed_students:
            continue
        assignments_by_cell[
            (assignment.day, assignment.time_slot_id, assignment.teacher_id)
        ].append(assignment)
    groups_by_cell: dict[tuple[date, int, int], list[GroupLessonRecord]] = defaultdict(list)
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

    availability = {
        (row.day, row.time_slot_id, row.teacher_id): row.level
        for row in snapshot.teacher_availabilities
        if row.teacher_id in allowed_teacher_ids
    }
    has_availability_source = bool(snapshot.teacher_availabilities)
    scheduled_teacher_ids_by_day: dict[date, set[int]] = defaultdict(set)
    for assignment in snapshot.assignments:
        if assignment.teacher_id in allowed_teacher_ids:
            scheduled_teacher_ids_by_day[assignment.day].add(assignment.teacher_id)
    for group in snapshot.group_lessons:
        if group.teacher_id_optional in allowed_teacher_ids:
            scheduled_teacher_ids_by_day[group.day].add(group.teacher_id_optional)

    panels: list[tuple[DateRecord, tuple[TeacherRecord, ...]]] = []
    for date_row in dates:
        available_ids = {
            teacher_id
            for (day, _slot_id, teacher_id), level in availability.items()
            if day == date_row.day and level > 0
        }
        teacher_ids = available_ids | scheduled_teacher_ids_by_day[date_row.day]
        if not has_availability_source:
            teacher_ids = scheduled_teacher_ids_by_day[date_row.day]
        day_teachers = tuple(row for row in teachers if row.id in teacher_ids)
        teacher_chunks = chunks(day_teachers, _TEACHERS_PER_DATE_PANEL) if day_teachers else ((),)
        panels.extend((date_row, teacher_chunk) for teacher_chunk in teacher_chunks)

    panel_context = _PanelContext(
        slots=slots,
        availability=availability,
        assignments_by_cell=assignments_by_cell,
        groups_by_cell=groups_by_cell,
        requests=requests,
        students=students,
        student_display_names=student_display_names,
        teacher_display_names=teacher_display_names,
        subjects=subjects,
        settings=settings,
        snapshot=snapshot,
    )

    rows: list[LayoutRow] = []
    if not panels:
        rows.append(
            LayoutRow(
                cells=(
                    LayoutCell(
                        "対象日がありません",
                        role="metadata",
                        column_span=_WEEK_TABLE_COLUMN_COUNT,
                        alignment="center",
                    ),
                ),
                height_points_optional=30,
            )
        )
    else:
        for panel_pair in chunks(tuple(panels), 2):
            left = panel_pair[0]
            right = panel_pair[1] if len(panel_pair) > 1 else None
            rows.extend(
                _paired_panel_rows(
                    left,
                    right,
                    context=panel_context,
                )
            )

    legend = "　".join(
        f"{rule.marker} {rule.label}"
        for rule in settings.style_rules
        if rule.code in {"unconfirmed", "closed"} or rule.code in settings.visible_fields
    )
    rows.append(
        LayoutRow(
            cells=(
                LayoutCell(
                    f"凡例　灰色: 勤務不可コマ　{legend}",
                    role="legend",
                    column_span=_WEEK_TABLE_COLUMN_COUNT,
                ),
            )
        )
    )
    week_end = week_start + timedelta(days=6)
    return LayoutPage(
        heading="季節講習時間割",
        subheading=f"{format_day(week_start)} ～ {format_day(week_end)}",
        tables=(
            LayoutTable(
                rows=tuple(rows),
                column_widths=(11.0, 18.0, 18.0, 18.0, 18.0, 2.0, 11.0, 18.0, 18.0, 18.0, 18.0),
            ),
        ),
        footer_note=(
            "日曜始まり・土曜終わりの週単位です。各日には出勤予定の講師だけを表示し、"
            "勤務不可コマを灰色で示します。"
        ),
    )


def _paired_panel_rows(
    left: tuple[DateRecord, tuple[TeacherRecord, ...]],
    right: tuple[DateRecord, tuple[TeacherRecord, ...]] | None,
    *,
    context: _PanelContext,
) -> tuple[LayoutRow, ...]:
    left_rows = _date_panel_rows(left, context=context)
    right_rows = _date_panel_rows(right, context=context) if right is not None else None
    result: list[LayoutRow] = []
    for index, left_cells in enumerate(left_rows):
        right_cells = (
            right_rows[index]
            if right_rows is not None
            else (LayoutCell("", column_span=_PANEL_COLUMN_COUNT),)
        )
        height = 25 if index < 2 else 42
        result.append(
            LayoutRow(
                cells=(
                    *left_cells,
                    LayoutCell("", role="legend"),
                    *right_cells,
                ),
                height_points_optional=height,
            )
        )
    result.append(
        LayoutRow(
            cells=(LayoutCell("", role="legend", column_span=_WEEK_TABLE_COLUMN_COUNT),),
            height_points_optional=5,
        )
    )
    return tuple(result)


def _date_panel_rows(
    panel: tuple[DateRecord, tuple[TeacherRecord, ...]],
    *,
    context: _PanelContext,
) -> tuple[tuple[LayoutCell, ...], ...]:
    slots = context.slots
    availability = context.availability
    assignments_by_cell = context.assignments_by_cell
    groups_by_cell = context.groups_by_cell
    requests = context.requests
    students = context.students
    student_display_names = context.student_display_names
    teacher_display_names = context.teacher_display_names
    subjects = context.subjects
    settings = context.settings
    snapshot = context.snapshot
    date_row, teachers = panel
    note = (
        f"　特記事項: {date_row.note}"
        if date_row.note and "note" in settings.visible_fields
        else ""
    )
    date_role = "header" if date_row.is_open else "closed"
    date_codes: tuple[str, ...] = () if date_row.is_open else ("closed",)
    rows: list[tuple[LayoutCell, ...]] = [
        (
            LayoutCell(
                f"{format_day(date_row.day)}{note}",
                role=date_role,  # type: ignore[arg-type]
                column_span=_PANEL_COLUMN_COUNT,
                style_codes=date_codes,
                alignment="center",
            ),
        )
    ]
    if not date_row.is_open:
        rows.append(
            (
                LayoutCell(
                    f"{settings.style('closed').marker} 休校日",
                    role="closed",
                    column_span=_PANEL_COLUMN_COUNT,
                    style_codes=("closed",),
                    alignment="center",
                ),
            )
        )
        rows.extend(
            (
                LayoutCell(
                    "",
                    role="closed",
                    column_span=_PANEL_COLUMN_COUNT,
                    style_codes=("closed",),
                ),
            )
            for _slot in slots
        )
        return tuple(rows)

    if teachers:
        header_cells: list[LayoutCell] = [LayoutCell("コマ", role="metadata", alignment="center")]
        header_cells.extend(
            LayoutCell(
                teacher_display_names[teacher.id],
                role="header",
                alignment="center",
            )
            for teacher in teachers
        )
        header_cells.extend(
            LayoutCell("", role="header", alignment="center")
            for _ in range(_TEACHERS_PER_DATE_PANEL - len(teachers))
        )
        rows.append(tuple(header_cells))
    else:
        rows.append(
            (
                LayoutCell("コマ", role="metadata", alignment="center"),
                LayoutCell(
                    "出勤予定の講師はいません",
                    role="unavailable",
                    column_span=_TEACHERS_PER_DATE_PANEL,
                    alignment="center",
                ),
            )
        )

    for slot in slots:
        cells: list[LayoutCell] = [
            LayoutCell(
                f"{slot.code}\n{slot.start_time:%H:%M}–{slot.end_time:%H:%M}",
                role="metadata",
                alignment="center",
            )
        ]
        for teacher in teachers:
            key = (date_row.day, slot.id, teacher.id)
            assignments = assignments_by_cell.get(key, ())
            groups = groups_by_cell.get(key, ())
            text, codes = _cell_content(
                assignments,
                groups,
                requests=requests,
                students=students,
                student_display_names=student_display_names,
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
            available = availability.get(key, 0) > 0
            if not snapshot.teacher_availabilities:
                available = bool(assignments or groups)
            cells.append(
                LayoutCell(
                    text or "—",
                    role="data" if available else "unavailable",
                    style_codes=codes,
                    alignment="left",
                )
            )
        cells.extend(
            LayoutCell("", role="unavailable")
            for _ in range(_TEACHERS_PER_DATE_PANEL - len(teachers))
        )
        rows.append(tuple(cells))
    return tuple(rows)


def _sunday_of_week(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _cell_content(
    assignments: Sequence[AssignmentRecord],
    groups: Sequence[GroupLessonRecord],
    *,
    requests: dict[int, LessonRequestRecord],
    students: dict[int, StudentRecord],
    student_display_names: dict[int, str],
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
        details = [f"{index}. {prefix}{student_display_names[student.id]}"]
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
