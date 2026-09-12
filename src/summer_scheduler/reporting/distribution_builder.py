"""生徒・講師へ配布する週カレンダー形式の時間割を構築する。"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from summer_scheduler.domain.grades import grade_from_excel
from summer_scheduler.reporting.common import (
    chunks,
    selected_dates,
    selected_students,
    selected_teachers,
)
from summer_scheduler.reporting.data import (
    DEFAULT_OUTPUT_SELECTION,
    AssignmentRecord,
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

_WEEKDAYS = ("日", "月", "火", "水", "木", "金", "土")
_GRADE_ORDER = {
    **{f"小{year}": year for year in range(1, 7)},
    **{f"中{year}": 10 + year for year in range(1, 4)},
    **{f"高{year}": 20 + year for year in range(1, 4)},
}


def build_student_handout_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    """生徒本人向けに担当講師名を伏せたA4時間割を返す。"""
    settings.validate()
    return _grade_ordered_handouts(
        snapshot,
        settings,
        selection,
        include_teacher=False,
        report_code="student_handouts",
        title="生徒配布時間割",
    )


def build_teacher_handout_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    """講師配置を記載し、学年順に並べたA4時間割を返す。"""
    settings.validate()
    return _grade_ordered_handouts(
        snapshot,
        settings,
        selection,
        include_teacher=True,
        report_code="teacher_handouts",
        title="講師配布時間割（学年順）",
    )


def build_teacher_packet_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    """講師ごとに、通常担当・講習担当・その他の順で配布ページを返す。"""
    settings.validate()
    students = tuple(sorted(selected_students(snapshot, selection), key=_student_sort_key))
    teachers = selected_teachers(snapshot, selection)
    requests = {row.id: row for row in snapshot.lesson_requests}
    sections: list[LayoutSection] = []
    for teacher in teachers:
        regular_ids = {
            request.student_id
            for request in snapshot.lesson_requests
            if request.regular_teacher_id_optional == teacher.id
        }
        seasonal_ids = {
            requests[assignment.lesson_request_id].student_id
            for assignment in snapshot.assignments
            if assignment.teacher_id == teacher.id
        }
        regular = tuple(student for student in students if student.id in regular_ids)
        seasonal = tuple(
            student
            for student in students
            if student.id in seasonal_ids and student.id not in regular_ids
        )
        unrelated = tuple(
            student
            for student in students
            if student.id not in regular_ids and student.id not in seasonal_ids
        )
        pages: list[LayoutPage] = [
            _student_page(
                snapshot,
                selection,
                student,
                title=f"講師配布時間割（{teacher.name}用）",
                category="通常授業を担当",
                include_teacher=True,
            )
            for student in regular
        ]
        pages.extend(
            _student_page(
                snapshot,
                selection,
                student,
                title=f"講師配布時間割（{teacher.name}用）",
                category="講習で担当",
                include_teacher=True,
            )
            for student in seasonal
        )
        for group in chunks(unrelated, 4):
            pages.append(
                LayoutPage(
                    heading=f"講師配布時間割（{teacher.name}用）",
                    subheading="その他の生徒（1ページ4人）",
                    tables=tuple(
                        _calendar_table(
                            snapshot,
                            selection,
                            student,
                            include_teacher=True,
                            compact=True,
                        )
                        for student in group
                    ),
                    footer_note="通常授業・講習とも担当しない生徒です。",
                )
            )
        if not pages:
            pages.append(_empty_page(f"講師配布時間割（{teacher.name}用）"))
        sections.append(LayoutSection(name=f"講師_{teacher.name}", pages=tuple(pages)))
    if not sections:
        sections.append(
            LayoutSection(name="講師配布時間割", pages=(_empty_page("講師配布時間割"),))
        )
    return _document(
        snapshot,
        settings,
        report_code="teacher_packets",
        title="講師別配布時間割",
        sections=tuple(sections),
    )


def _grade_ordered_handouts(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection,
    *,
    include_teacher: bool,
    report_code: str,
    title: str,
) -> LayoutDocument:
    students = tuple(sorted(selected_students(snapshot, selection), key=_student_sort_key))
    sections = tuple(
        LayoutSection(
            name=f"{grade_from_excel(student.grade)}_{student.name}",
            pages=(
                _student_page(
                    snapshot,
                    selection,
                    student,
                    title=title,
                    category="学年順",
                    include_teacher=include_teacher,
                ),
            ),
        )
        for student in students
    )
    if not sections:
        sections = (LayoutSection(name=title, pages=(_empty_page(title),)),)
    return _document(
        snapshot,
        settings,
        report_code=report_code,
        title=title,
        sections=sections,
    )


def _student_page(
    snapshot: OutputSnapshot,
    selection: OutputSelection,
    student: StudentRecord,
    *,
    title: str,
    category: str,
    include_teacher: bool,
) -> LayoutPage:
    grade = grade_from_excel(student.grade)
    return LayoutPage(
        heading=title,
        subheading=f"{grade}　{student.name}　｜　{category}",
        tables=(
            _calendar_table(
                snapshot,
                selection,
                student,
                include_teacher=include_teacher,
                compact=False,
            ),
        ),
        footer_note="日時・コマをご確認ください。",
    )


def _calendar_table(
    snapshot: OutputSnapshot,
    selection: OutputSelection,
    student: StudentRecord,
    *,
    include_teacher: bool,
    compact: bool,
) -> LayoutTable:
    dates = selected_dates(snapshot, selection)
    dates_by_day = {row.day: row for row in dates}
    requests = {row.id: row for row in snapshot.lesson_requests}
    subjects = {row.id: row for row in snapshot.subjects}
    slots = {row.id: row for row in snapshot.slots}
    teacher_names = compact_person_name_map(snapshot.teachers)
    assignments_by_day: dict[date, list[AssignmentRecord]] = defaultdict(list)
    for assignment in snapshot.assignments:
        request = requests[assignment.lesson_request_id]
        if request.student_id == student.id and assignment.day in dates_by_day:
            assignments_by_day[assignment.day].append(assignment)
    for day_assignments in assignments_by_day.values():
        day_assignments.sort(
            key=lambda row: (slots[row.time_slot_id].sort_order, row.session_index)
        )

    rows: list[LayoutRow] = [
        LayoutRow(
            cells=(
                LayoutCell(
                    f"{grade_from_excel(student.grade)}　{student.name}",
                    role="subtitle",
                    column_span=8,
                    alignment="center",
                    preserve_grade_notation=True,
                ),
            ),
            height_points_optional=18 if compact else 24,
        ),
        LayoutRow(
            cells=(
                LayoutCell("週", role="header", alignment="center"),
                *(LayoutCell(value, role="header", alignment="center") for value in _WEEKDAYS),
            ),
            height_points_optional=16 if compact else 20,
        ),
    ]
    for week_start in _week_starts(dates):
        day_cells: list[LayoutCell] = []
        for offset in range(7):
            day_value = week_start + timedelta(days=offset)
            date_row = dates_by_day.get(day_value)
            if date_row is None:
                day_cells.append(LayoutCell("", role="unavailable", alignment="center"))
                continue
            lines = [f"{day_value.month}/{day_value.day}"]
            if not date_row.is_open:
                lines.append("休校")
                day_cells.append(LayoutCell("\n".join(lines), role="closed", alignment="center"))
                continue
            for assignment in assignments_by_day.get(day_value, ()):
                request = requests[assignment.lesson_request_id]
                subject = subjects[request.subject_id]
                slot = slots[assignment.time_slot_id]
                short_name = subject.short_name or subject.name[:1]
                teacher_text = (
                    f"({teacher_names.get(assignment.teacher_id, '未定')})"
                    if include_teacher
                    else ""
                )
                lines.append(f"{slot.code} {short_name}{teacher_text}")
            day_cells.append(LayoutCell("\n".join(lines), alignment="center"))
        rows.append(
            LayoutRow(
                cells=(
                    LayoutCell(
                        f"{week_start.month}/{week_start.day}\n～\n"
                        f"{(week_start + timedelta(days=6)).month}/"
                        f"{(week_start + timedelta(days=6)).day}",
                        role="metadata",
                        alignment="center",
                    ),
                    *day_cells,
                ),
                height_points_optional=36 if compact else 62,
            )
        )
    return LayoutTable(
        rows=tuple(rows),
        column_widths=(9, 13, 13, 13, 13, 13, 13, 13),
        repeat_header_rows=2,
    )


def _week_starts(dates: tuple[object, ...]) -> tuple[date, ...]:
    day_values = sorted(row.day for row in dates if hasattr(row, "day"))
    if not day_values:
        return ()
    first = day_values[0] - timedelta(days=(day_values[0].weekday() + 1) % 7)
    last = day_values[-1] - timedelta(days=(day_values[-1].weekday() + 1) % 7)
    return tuple(first + timedelta(days=7 * index) for index in range((last - first).days // 7 + 1))


def _student_sort_key(student: StudentRecord) -> tuple[int, str, int]:
    normalized_grade = grade_from_excel(student.grade)
    return (
        _GRADE_ORDER.get(normalized_grade, 999),
        student.name.replace(" ", "").replace("　", ""),
        student.id,
    )


def _empty_page(title: str) -> LayoutPage:
    return LayoutPage(
        heading=title,
        subheading="対象なし",
        tables=(
            LayoutTable(
                rows=(LayoutRow(cells=(LayoutCell("出力対象がありません", alignment="center"),)),),
                column_widths=(80,),
            ),
        ),
    )


def _document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    *,
    report_code: str,
    title: str,
    sections: tuple[LayoutSection, ...],
) -> LayoutDocument:
    return LayoutDocument(
        report_code=report_code,
        title=title,
        campus_name=snapshot.project.campus_name,
        course_name=snapshot.project.title,
        updated_text=snapshot.project.generated_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        sections=sections,
        page_size="A4",
        orientation="portrait",
        margin_mm=max(6.0, min(settings.margin_mm, 12.0)),
        font_size=min(settings.font_size, 8.5),
        logo_path_optional=settings.logo_path_optional or snapshot.project.logo_path_optional,
    )


__all__ = [
    "build_student_handout_document",
    "build_teacher_handout_document",
    "build_teacher_packet_document",
]
