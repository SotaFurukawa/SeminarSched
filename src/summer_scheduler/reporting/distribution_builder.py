"""生徒・講師へ配布する見本準拠の週カレンダー時間割を構築する。"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, timedelta

from summer_scheduler.domain.grades import grade_from_excel
from summer_scheduler.reporting.common import selected_students, selected_teachers
from summer_scheduler.reporting.data import (
    DEFAULT_OUTPUT_SELECTION,
    AssignmentRecord,
    DateRecord,
    LessonRequestRecord,
    OutputSelection,
    OutputSnapshot,
    SlotRecord,
    StudentRecord,
    SubjectRecord,
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
_DISTRIBUTION_COLUMNS = (
    9.0,
    12.125,
    9.875,
    9.875,
    9.875,
    9.875,
    9.875,
    9.875,
    9.875,
)
_COURSE_LABEL = re.compile(r"(?:春期|夏期|冬期|季節)講習")
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


def build_student_schedule_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    """通常の生徒別出力も、確認済みの週カレンダー形式で返す。"""
    settings.validate()
    return _grade_ordered_handouts(
        snapshot,
        settings,
        selection,
        include_teacher=False,
        report_code="student_schedules",
        title="生徒別時間割",
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
    """講師ごとに通常担当・講習担当・その他の順で同じ様式のページを返す。"""
    settings.validate()
    students = tuple(sorted(selected_students(snapshot, selection), key=_student_sort_key))
    participating_ids = _participating_student_ids(snapshot)
    participating_students = tuple(row for row in students if row.id in participating_ids)
    absent_students = tuple(row for row in students if row.id not in participating_ids)
    teachers = selected_teachers(snapshot, selection)
    requests = {row.id: row for row in snapshot.lesson_requests}
    teacher_file_names = compact_person_name_map(teachers)
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
            if assignment.teacher_id == teacher.id and assignment.lesson_request_id in requests
        }
        ordered_students = (
            *(student for student in participating_students if student.id in regular_ids),
            *(
                student
                for student in participating_students
                if student.id in seasonal_ids and student.id not in regular_ids
            ),
            *(
                student
                for student in participating_students
                if student.id not in regular_ids and student.id not in seasonal_ids
            ),
        )
        pages = (
            *((_absence_page(absent_students),) if absent_students else ()),
            *(
                _student_page(
                    snapshot,
                    selection,
                    student,
                    title=f"講師配布時間割（{teacher.name}用）",
                    category="講師別",
                    include_teacher=True,
                )
                for student in ordered_students
            ),
        )
        if not pages:
            pages = (_empty_page(f"講師配布時間割（{teacher.name}用）"),)
        sections.append(
            LayoutSection(
                name=f"{teacher_file_names.get(teacher.id, teacher.name)}t",
                pages=pages,
            )
        )
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
    participating_ids = _participating_student_ids(snapshot)
    participating_students = tuple(row for row in students if row.id in participating_ids)
    absent_students = tuple(row for row in students if row.id not in participating_ids)
    sections = (
        *(
            (LayoutSection(name="講習欠席一覧", pages=(_absence_page(absent_students),)),)
            if absent_students
            else ()
        ),
        *(
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
            for student in participating_students
        ),
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


def _participating_student_ids(snapshot: OutputSnapshot) -> set[int]:
    """受講申込または集団授業への参加がある生徒IDを返す。"""
    participating = {
        row.student_id for row in snapshot.lesson_requests if row.required_sessions > 0
    }
    participating.update(
        student_id for row in snapshot.group_lessons for student_id in row.student_ids
    )
    return participating


def _absence_page(students: tuple[StudentRecord, ...]) -> LayoutPage:
    """講習へ参加しない生徒を、配布帳票の先頭へ載せる。"""
    rows: list[LayoutRow] = [
        LayoutRow(
            cells=(
                LayoutCell(
                    "講習欠席一覧",
                    role="title",
                    column_span=9,
                    alignment="center",
                    style_codes=("dist_title",),
                    preserve_grade_notation=True,
                ),
            ),
            height_points_optional=45.0,
        ),
        _blank_row(),
        LayoutRow(
            cells=(
                LayoutCell(
                    "学年",
                    role="header",
                    column_span=3,
                    alignment="center",
                    style_codes=("dist_profile",),
                ),
                LayoutCell(
                    "生徒名",
                    role="header",
                    column_span=6,
                    alignment="center",
                    style_codes=("dist_profile",),
                ),
            ),
            height_points_optional=24.0,
        ),
    ]
    if students:
        rows.extend(
            LayoutRow(
                cells=(
                    LayoutCell(
                        grade_from_excel(student.grade),
                        column_span=3,
                        alignment="center",
                        style_codes=("dist_profile",),
                    ),
                    LayoutCell(
                        student.name,
                        column_span=6,
                        alignment="center",
                        style_codes=("dist_name",),
                        preserve_grade_notation=True,
                    ),
                ),
                height_points_optional=24.0,
            )
            for student in students
        )
    else:
        rows.append(
            LayoutRow(
                cells=(
                    LayoutCell(
                        "該当者はいません",
                        column_span=9,
                        alignment="center",
                        style_codes=("dist_blank",),
                    ),
                ),
                height_points_optional=24.0,
            )
        )
    return LayoutPage(
        heading="講習欠席一覧",
        subheading="講習欠席一覧",
        tables=(LayoutTable(rows=tuple(rows), column_widths=_DISTRIBUTION_COLUMNS),),
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
        subheading=f"{grade}_{student.name}_{category}",
        tables=(
            _calendar_table(
                snapshot,
                selection,
                student,
                include_teacher=include_teacher,
            ),
        ),
    )


def _calendar_table(
    snapshot: OutputSnapshot,
    selection: OutputSelection,
    student: StudentRecord,
    *,
    include_teacher: bool,
) -> LayoutTable:
    start_date = snapshot.project.start_date
    end_date = snapshot.project.end_date
    dates = tuple(row for row in snapshot.dates if start_date <= row.day <= end_date)
    dates_by_day = {row.day: row for row in dates}
    requests = {row.id: row for row in snapshot.lesson_requests}
    subjects = {row.id: row for row in snapshot.subjects}
    slots = tuple(
        sorted((row for row in snapshot.slots if row.enabled), key=lambda row: row.sort_order)
    )
    teacher_names = compact_person_name_map(snapshot.teachers)
    assignments: dict[tuple[date, int], list[AssignmentRecord]] = defaultdict(list)
    for assignment in snapshot.assignments:
        request = requests.get(assignment.lesson_request_id)
        if (
            request is None
            or request.student_id != student.id
            or assignment.day not in dates_by_day
        ):
            continue
        assignments[(assignment.day, assignment.time_slot_id)].append(assignment)
    for assignment_rows in assignments.values():
        assignment_rows.sort(key=lambda row: row.session_index)

    grade_school, grade_year = _grade_parts(student.grade)
    rows: list[LayoutRow] = [
        LayoutRow(
            cells=(
                LayoutCell(
                    _document_title(snapshot),
                    role="title",
                    column_span=9,
                    alignment="center",
                    style_codes=("dist_title",),
                    preserve_grade_notation=True,
                ),
            ),
            height_points_optional=45.0,
        ),
        _blank_row(),
        _blank_row(),
        LayoutRow(
            cells=(
                LayoutCell("", style_codes=("dist_blank",)),
                LayoutCell(grade_school, alignment="center", style_codes=("dist_profile",)),
                LayoutCell(grade_year, alignment="center", style_codes=("dist_profile",)),
                LayoutCell("年生", alignment="center", style_codes=("dist_profile",)),
                LayoutCell("", style_codes=("dist_blank",)),
                LayoutCell(
                    student.name,
                    column_span=2,
                    alignment="center",
                    style_codes=("dist_name",),
                    preserve_grade_notation=True,
                ),
                LayoutCell("様", alignment="center", style_codes=("dist_profile",)),
                LayoutCell("", style_codes=("dist_blank",)),
            ),
            height_points_optional=24.0,
        ),
    ]
    if include_teacher:
        rows.append(
            LayoutRow(
                cells=(
                    LayoutCell(
                        _regular_teacher_summary(
                            student.id,
                            requests,
                            subjects,
                            teacher_names,
                        ),
                        column_span=9,
                        alignment="center",
                        style_codes=("dist_profile",),
                        preserve_grade_notation=True,
                    ),
                ),
                height_points_optional=24.0,
            )
        )
    else:
        rows.append(_blank_row())
    rows.append(_blank_row())
    for week_start in _week_starts(start_date, end_date):
        week_days = tuple(week_start + timedelta(days=offset) for offset in range(7))
        if _is_fully_closed_week(week_days, dates_by_day):
            rows.append(
                LayoutRow(
                    cells=(
                        LayoutCell(
                            f"{week_days[0].month}/{week_days[0].day} ~ "
                            f"{week_days[-1].month}/{week_days[-1].day}　休校日",
                            column_span=9,
                            alignment="center",
                            style_codes=("dist_closed_week",),
                            preserve_grade_notation=True,
                        ),
                    )
                )
            )
            continue
        rows.extend(
            _week_rows(
                week_days,
                dates_by_day,
                slots,
                assignments,
                requests,
                subjects,
                teacher_names,
                include_teacher=include_teacher,
            )
        )
    rows.append(
        LayoutRow(
            cells=(
                LayoutCell(
                    f"学力テスト　　{grade_from_excel(student.grade)}　　日時：",
                    column_span=4,
                    alignment="center",
                    style_codes=("dist_final_left",),
                    preserve_grade_notation=True,
                ),
                LayoutCell(
                    "受験する・受験しない",
                    column_span=5,
                    alignment="center",
                    style_codes=("dist_final_right",),
                    preserve_grade_notation=True,
                ),
            )
        )
    )
    return LayoutTable(rows=tuple(rows), column_widths=_DISTRIBUTION_COLUMNS)


def _regular_teacher_summary(
    student_id: int,
    requests: Mapping[int, LessonRequestRecord],
    subjects: Mapping[int, SubjectRecord],
    teacher_names: Mapping[int, str],
) -> str:
    """科目略称と通常担当講師を、講師配布用の1行へまとめる。"""
    values: list[str] = []
    seen: set[tuple[int, int]] = set()
    for request in sorted(requests.values(), key=lambda row: (row.subject_id, row.id)):
        teacher_id = request.regular_teacher_id_optional
        key = (request.subject_id, teacher_id or 0)
        if request.student_id != student_id or teacher_id is None or key in seen:
            continue
        subject = subjects.get(request.subject_id)
        teacher_name = teacher_names.get(teacher_id)
        if subject is None or not teacher_name:
            continue
        seen.add(key)
        short_name = subject.short_name or subject.name[:1]
        values.append(f"{short_name} {teacher_name}t")
    return "　".join(values) if values else "通常担当：―"


def _week_rows(
    week_days: tuple[date, ...],
    dates_by_day: Mapping[date, DateRecord],
    slots: tuple[SlotRecord, ...],
    assignments: dict[tuple[date, int], list[AssignmentRecord]],
    requests: Mapping[int, LessonRequestRecord],
    subjects: Mapping[int, SubjectRecord],
    teacher_names: dict[int, str],
    *,
    include_teacher: bool,
) -> tuple[LayoutRow, ...]:
    month_cells: list[LayoutCell] = [
        LayoutCell("", column_span=2, row_span=3, style_codes=("dist_week_corner",))
    ]
    offset = 0
    while offset < 7:
        month = week_days[offset].month
        span = 1
        while offset + span < 7 and week_days[offset + span].month == month:
            span += 1
        month_cells.append(
            LayoutCell(
                f"{month}月",
                column_span=span,
                alignment="center",
                style_codes=("dist_month",),
                preserve_grade_notation=True,
            )
        )
        offset += span

    rows = [
        LayoutRow(cells=tuple(month_cells)),
        LayoutRow(
            cells=tuple(
                LayoutCell(day, alignment="center", style_codes=("dist_day",)) for day in _WEEKDAYS
            )
        ),
        LayoutRow(
            cells=tuple(
                LayoutCell(
                    str(day.day),
                    alignment="center",
                    style_codes=("dist_day",),
                    preserve_grade_notation=True,
                )
                for day in week_days
            )
        ),
    ]
    slot_count = max(1, len(slots))
    closed_or_outside = _closed_or_outside_runs(week_days, dates_by_day)
    for slot_index in range(slot_count):
        slot = slots[slot_index] if slot_index < len(slots) else None
        cells: list[LayoutCell] = [
            LayoutCell(
                f"{getattr(slot, 'code', '')}タイム",
                alignment="center",
                style_codes=("dist_slot",),
                preserve_grade_notation=True,
            ),
            LayoutCell(
                _slot_time(slot),
                alignment="center",
                style_codes=("dist_slot",),
                preserve_grade_notation=True,
            ),
        ]
        day_index = 0
        while day_index < 7:
            run = closed_or_outside.get(day_index)
            if run is not None:
                run_length, label, style_code = run
                if slot_index == 0:
                    cells.append(
                        LayoutCell(
                            label,
                            column_span=run_length,
                            row_span=slot_count,
                            alignment="center",
                            style_codes=(style_code,),
                        )
                    )
                day_index += run_length
                continue
            cells.append(
                LayoutCell(
                    _assignment_text(
                        week_days[day_index],
                        slot,
                        assignments,
                        requests,
                        subjects,
                        teacher_names,
                        include_teacher=include_teacher,
                    ),
                    alignment="center",
                    style_codes=("dist_lesson",),
                    preserve_grade_notation=True,
                )
            )
            day_index += 1
        rows.append(LayoutRow(cells=tuple(cells)))
    return tuple(rows)


def _closed_or_outside_runs(
    week_days: tuple[date, ...],
    dates_by_day: Mapping[date, DateRecord],
) -> dict[int, tuple[int, str, str]]:
    result: dict[int, tuple[int, str, str]] = {}
    index = 0
    while index < 7:
        row = dates_by_day.get(week_days[index])
        kind = "outside" if row is None else ("closed" if not row.is_open else "open")
        if kind == "open":
            index += 1
            continue
        run = 1
        if kind == "outside":
            while index + run < 7 and dates_by_day.get(week_days[index + run]) is None:
                run += 1
        result[index] = (
            run,
            "指定範囲外" if kind == "outside" else "休校日",
            "dist_outside" if kind == "outside" else "dist_closed",
        )
        index += run
    return result


def _assignment_text(
    day: date,
    slot: SlotRecord | None,
    assignments: dict[tuple[date, int], list[AssignmentRecord]],
    requests: Mapping[int, LessonRequestRecord],
    subjects: Mapping[int, SubjectRecord],
    teacher_names: dict[int, str],
    *,
    include_teacher: bool,
) -> str:
    if slot is None:
        return ""
    values: list[str] = []
    for assignment in assignments.get((day, slot.id), ()):
        request = requests.get(assignment.lesson_request_id)
        subject = subjects.get(request.subject_id) if request is not None else None
        if subject is None:
            continue
        short_name = subject.short_name or subject.name[:1]
        teacher = f"　{teacher_names.get(assignment.teacher_id, '未定')}" if include_teacher else ""
        values.append(f"{short_name}{teacher}")
    return "／".join(values)


def _slot_time(slot: SlotRecord | None) -> str:
    if slot is None:
        return ""
    start = slot.start_time
    end = slot.end_time
    return f"{start.strftime('%H:%M')}～{end.strftime('%H:%M')}"


def _is_fully_closed_week(
    week_days: tuple[date, ...], dates_by_day: Mapping[date, DateRecord]
) -> bool:
    return all((row := dates_by_day.get(day)) is not None and not row.is_open for day in week_days)


def _blank_row() -> LayoutRow:
    return LayoutRow(cells=(LayoutCell("", column_span=9, style_codes=("dist_blank",)),))


def _document_title(snapshot: OutputSnapshot) -> str:
    match = _COURSE_LABEL.search(snapshot.project.title)
    course = match.group(0) if match else snapshot.project.title.strip()
    return f"{snapshot.project.start_date.year}　{course}　個別指導　受講日のご案内"


def _grade_parts(raw_grade: str) -> tuple[str, str]:
    grade = grade_from_excel(raw_grade)
    school = {"小": "小学", "中": "中学", "高": "高校"}.get(grade[:1], "")
    return school, grade[1:] if len(grade) > 1 else grade


def _week_starts(start_date: date, end_date: date) -> tuple[date, ...]:
    """設定期間に重なる日曜始まり・土曜終わりの週を返す。"""
    if end_date < start_date:
        return ()
    first = start_date - timedelta(days=(start_date.weekday() + 1) % 7)
    last = end_date - timedelta(days=(end_date.weekday() + 1) % 7)
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
                rows=(
                    LayoutRow(
                        cells=(
                            LayoutCell(
                                "出力対象がありません",
                                column_span=9,
                                alignment="center",
                                style_codes=("dist_title",),
                            ),
                        ),
                        height_points_optional=45.0,
                    ),
                ),
                column_widths=_DISTRIBUTION_COLUMNS,
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
        margin_mm=12.0,
        font_size=11.0,
        logo_path_optional=None,
    )


__all__ = [
    "build_student_handout_document",
    "build_student_schedule_document",
    "build_teacher_handout_document",
    "build_teacher_packet_document",
]
