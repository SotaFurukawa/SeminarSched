"""未配置・警告一覧を共通ページレイアウトへ変換する。"""

from __future__ import annotations

from collections.abc import Sequence

from summer_scheduler.reporting.common import chunks, format_day, updated_text
from summer_scheduler.reporting.data import (
    DEFAULT_OUTPUT_SELECTION,
    OutputSelection,
    OutputSnapshot,
    StudentRecord,
    SubjectRecord,
    TeacherRecord,
    UnassignedRecord,
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

_ROWS_PER_PAGE = 24


def build_issues_document(
    snapshot: OutputSnapshot,
    settings: OutputSettings,
    selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
) -> LayoutDocument:
    settings.validate()
    allowed_students = set(selection.student_ids)
    allowed_teachers = set(selection.teacher_ids)
    allowed_dates = set(selection.dates)
    students = {row.id: row for row in snapshot.students}
    subjects = {row.id: row for row in snapshot.subjects}
    teachers = {row.id: row for row in snapshot.teachers}
    unassigned = tuple(
        row
        for row in snapshot.unassigned
        if not allowed_students or row.student_id in allowed_students
        if not allowed_teachers or row.regular_teacher_id_optional in allowed_teachers
    )
    teacher_names = {teachers[value].name for value in allowed_teachers if value in teachers}
    student_names = {students[value].name for value in allowed_students if value in students}
    warnings = tuple(
        row
        for row in snapshot.warnings
        if (not allowed_dates or row.day_optional is None or row.day_optional in allowed_dates)
        and (
            not allowed_teachers
            or (
                row.teacher_id_optional in allowed_teachers
                if row.teacher_id_optional is not None
                else not row.teacher_name or row.teacher_name in teacher_names
            )
        )
        and (
            not allowed_students
            or (
                bool(set(row.student_ids) & allowed_students)
                if row.student_ids
                else not row.student_name or row.student_name in student_names
            )
        )
    )
    unassigned_pages = _unassigned_pages(
        unassigned,
        students=students,
        subjects=subjects,
        teachers=teachers,
    )
    warning_pages = _warning_pages(warnings)
    return LayoutDocument(
        report_code="issues",
        title="未配置・警告一覧",
        campus_name=snapshot.project.campus_name,
        course_name=snapshot.project.title,
        updated_text=updated_text(snapshot),
        sections=(
            LayoutSection(name="未配置一覧", pages=unassigned_pages),
            LayoutSection(name="警告一覧", pages=warning_pages),
        ),
        page_size=settings.paper_size,
        orientation=settings.orientation,
        margin_mm=settings.margin_mm,
        font_size=settings.font_size,
        logo_path_optional=settings.logo_path_optional or snapshot.project.logo_path_optional,
    )


def _unassigned_pages(
    rows: Sequence[UnassignedRecord],
    *,
    students: dict[int, StudentRecord],
    subjects: dict[int, SubjectRecord],
    teachers: dict[int, TeacherRecord],
) -> tuple[LayoutPage, ...]:
    row_chunks = chunks(tuple(rows), _ROWS_PER_PAGE) if rows else ((),)
    return tuple(
        LayoutPage(
            heading="未配置一覧",
            subheading=f"未配置の受講希望 {len(rows)}件",
            tables=(
                LayoutTable(
                    rows=(
                        LayoutRow(
                            cells=tuple(
                                LayoutCell(value, role="header", alignment="center")
                                for value in (
                                    "生徒",
                                    "科目",
                                    "必要",
                                    "配置済",
                                    "不足",
                                    "主な理由",
                                    "解決候補",
                                    "優先度",
                                    "通常担当",
                                    "1対1",
                                    "備考",
                                )
                            )
                        ),
                        *(
                            LayoutRow(
                                cells=(
                                    LayoutCell(students[row.student_id].name),
                                    LayoutCell(subjects[row.subject_id].name),
                                    LayoutCell(str(row.required_sessions), alignment="right"),
                                    LayoutCell(str(row.placed_sessions), alignment="right"),
                                    LayoutCell(str(row.missing_sessions), alignment="right"),
                                    LayoutCell(row.main_reason),
                                    LayoutCell("／".join(row.resolution_candidates) or "候補なし"),
                                    LayoutCell(str(row.priority), alignment="center"),
                                    LayoutCell(
                                        teachers[row.regular_teacher_id_optional].name
                                        if row.regular_teacher_id_optional in teachers
                                        else "未設定"
                                    ),
                                    LayoutCell("必須" if row.one_to_one_required else "通常"),
                                    LayoutCell(row.note),
                                )
                            )
                            for row in group
                        ),
                    ),
                    column_widths=(15, 12, 7, 7, 7, 25, 28, 8, 15, 9, 20),
                    repeat_header_rows=1,
                ),
            ),
        )
        for group in row_chunks
    )


def _warning_pages(rows: Sequence[WarningRecord]) -> tuple[LayoutPage, ...]:
    row_chunks = chunks(tuple(rows), _ROWS_PER_PAGE) if rows else ((),)
    return tuple(
        LayoutPage(
            heading="警告一覧",
            subheading=f"警告・情報 {len(rows)}件",
            tables=(
                LayoutTable(
                    rows=(
                        LayoutRow(
                            cells=tuple(
                                LayoutCell(value, role="header", alignment="center")
                                for value in (
                                    "severity",
                                    "issue type",
                                    "日付",
                                    "コマ",
                                    "生徒",
                                    "講師",
                                    "内容",
                                    "対応状況",
                                )
                            )
                        ),
                        *(
                            LayoutRow(
                                cells=(
                                    LayoutCell(row.severity),
                                    LayoutCell(row.issue_type),
                                    LayoutCell(
                                        format_day(row.day_optional)
                                        if row.day_optional is not None
                                        else "—"
                                    ),
                                    LayoutCell(row.slot_code or "—"),
                                    LayoutCell(row.student_name or "—"),
                                    LayoutCell(row.teacher_name or "—"),
                                    LayoutCell(row.content),
                                    LayoutCell(row.status),
                                )
                            )
                            for row in group
                        ),
                    ),
                    column_widths=(10, 17, 14, 8, 15, 15, 36, 12),
                    repeat_header_rows=1,
                ),
            ),
        )
        for group in row_chunks
    )


__all__ = ["build_issues_document"]
