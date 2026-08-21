"""年度をまたいで利用する生徒・講師基本情報Excelの入出力。"""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Final, cast

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from summer_scheduler.domain.defaults import DEFAULT_SUBJECTS
from summer_scheduler.domain.grades import (
    EXCEL_GRADE_OPTIONS,
    INTERNAL_GRADE_OPTIONS,
    grade_from_excel,
    grade_to_excel,
)
from summer_scheduler.domain.identifiers import next_person_external_id

SHARED_ROSTER_FILENAME: Final = "生徒・講師_基本情報.xlsx"

_STUDENT_HEADERS: Final = (
    "生徒ID（自動・入力不要）",
    "姓（必須）",
    "名",
    "氏名（確認）",
    "学年（必須）",
    "標準最大連続コマ数",
    "空きコマ許可",
    "在籍",
    "備考",
)
_TEACHER_HEADERS: Final = (
    "講師ID（自動・入力不要）",
    "姓（必須）",
    "名",
    "氏名（確認）",
    "空きコマ許可",
    "在籍",
    "備考",
)
_SUBJECT_HEADERS: Final = (
    "科目コード（必須）",
    "表示名（必須）",
    "学校段階（必須）",
    "並び順（必須）",
    "有効",
)
_QUALIFICATION_HEADERS: Final = (
    "講師ID（自動・入力不要）",
    "講師名から選択",
    "講師名（確認）",
    "科目コード",
    "科目名から選択",
    "科目名（確認）",
    "指導可能",
    "備考",
)
_REGULAR_HEADERS: Final = (
    "生徒ID（自動・入力不要）",
    "生徒名から選択",
    "生徒名（確認）",
    "科目コード",
    "科目名から選択",
    "科目名（確認）",
    "通常担当講師ID（自動・入力不要）",
    "通常担当講師名から選択",
    "通常担当講師名（確認）",
    "担当講師優先度",
    "1対1必須",
    "備考",
)
_SHEETS: Final = ("生徒", "講師", "科目", "講師対応科目", "通常授業")
_HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")
_HELPER_FILL = PatternFill(fill_type="solid", fgColor="5B9BD5")
_INACTIVE_FILL = PatternFill(fill_type="solid", fgColor="E7E6E6")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_THIN_GREY = Side(style="thin", color="D9DEE7")
_MAX_ROW: Final = 10_000
_formula_rule = cast(Callable[..., Any], FormulaRule)


class SharedRosterError(ValueError):
    """共通名簿の形式または参照関係に問題がある。"""


@dataclass(frozen=True, slots=True)
class SharedStudent:
    external_id: str
    surname: str
    given_name: str
    grade: str
    max_consecutive_slots: int = 2
    allow_gap: bool = False
    active: bool = True
    note: str = ""

    @property
    def name(self) -> str:
        return _full_name(self.surname, self.given_name)


@dataclass(frozen=True, slots=True)
class SharedTeacher:
    external_id: str
    surname: str
    given_name: str
    allow_gap: bool = False
    active: bool = True
    note: str = ""

    @property
    def name(self) -> str:
        return _full_name(self.surname, self.given_name)


@dataclass(frozen=True, slots=True)
class SharedSubject:
    code: str
    display_name: str
    school_level: str
    sort_order: int
    active: bool = True


@dataclass(frozen=True, slots=True)
class SharedQualification:
    teacher_external_id: str
    subject_code: str
    can_teach: bool = True
    note: str = ""


@dataclass(frozen=True, slots=True)
class SharedRegularLesson:
    student_external_id: str
    subject_code: str
    regular_teacher_external_id: str = ""
    regular_teacher_priority: int = 3
    one_to_one_required: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class SharedRosterData:
    students: tuple[SharedStudent, ...]
    teachers: tuple[SharedTeacher, ...]
    subjects: tuple[SharedSubject, ...]
    qualifications: tuple[SharedQualification, ...] = ()
    regular_lessons: tuple[SharedRegularLesson, ...] = ()


def empty_shared_roster() -> SharedRosterData:
    """既定科目だけを含む最初の共通名簿を返す。"""
    return SharedRosterData(
        students=(),
        teachers=(),
        subjects=tuple(
            SharedSubject(
                item.code,
                item.display_name,
                item.school_level,
                item.sort_order,
                True,
            )
            for item in DEFAULT_SUBJECTS
        ),
    )


def write_shared_roster(path: Path, data: SharedRosterData) -> None:
    """共通名簿を入力規則・参照表示・退籍行の灰色表示付きで保存する。"""
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    active_sheet = workbook.active
    if active_sheet is not None:
        workbook.remove(active_sheet)
    workbook.properties.title = "生徒・講師 基本情報"
    workbook.properties.subject = "講習に依存しない在籍者・通常授業情報"
    workbook.properties.creator = "夏期講習時間割作成アプリ"
    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True

    student_sheet = workbook.create_sheet("生徒")
    _setup_sheet(student_sheet, _STUDENT_HEADERS, (18, 15, 15, 24, 12, 22, 15, 13, 32))
    _mark_auto_id_header(student_sheet, "生徒", "S-0001")
    for index, student_row in enumerate(
        sorted(data.students, key=lambda item: (not item.active, item.external_id)), start=2
    ):
        student_sheet.append(
            [
                student_row.external_id,
                student_row.surname,
                student_row.given_name,
                f'=IF(COUNTA(B{index}:C{index})=0,"",TRIM(B{index}&" "&C{index}))',
                grade_to_excel(student_row.grade),
                student_row.max_consecutive_slots,
                _yes_no(student_row.allow_gap),
                _membership(student_row.active),
                student_row.note,
            ]
        )
    _add_list(student_sheet, "E2:E10000", f'"{",".join(EXCEL_GRADE_OPTIONS)}"')
    _add_whole(student_sheet, "F2:F10000", 1, 3, allow_blank=True)
    _add_list(student_sheet, "G2:G10000", '"はい,いいえ"', allow_blank=True)
    _add_list(student_sheet, "H2:H10000", '"☑ 在籍,☐ 退籍"', allow_blank=True)
    _grey_inactive(student_sheet, "H", len(_STUDENT_HEADERS))

    teacher_sheet = workbook.create_sheet("講師")
    _setup_sheet(teacher_sheet, _TEACHER_HEADERS, (18, 15, 15, 24, 15, 13, 32))
    _mark_auto_id_header(teacher_sheet, "講師", "T-0001")
    for index, teacher_row in enumerate(
        sorted(data.teachers, key=lambda item: (not item.active, item.external_id)), start=2
    ):
        teacher_sheet.append(
            [
                teacher_row.external_id,
                teacher_row.surname,
                teacher_row.given_name,
                f'=IF(COUNTA(B{index}:C{index})=0,"",TRIM(B{index}&" "&C{index}))',
                _yes_no(teacher_row.allow_gap),
                _membership(teacher_row.active),
                teacher_row.note,
            ]
        )
    _add_list(teacher_sheet, "E2:E10000", '"はい,いいえ"', allow_blank=True)
    _add_list(teacher_sheet, "F2:F10000", '"☑ 在籍,☐ 退籍"', allow_blank=True)
    _grey_inactive(teacher_sheet, "F", len(_TEACHER_HEADERS))

    subject_sheet = workbook.create_sheet("科目")
    _setup_sheet(subject_sheet, _SUBJECT_HEADERS, (20, 28, 15, 13, 12))
    for subject_row in sorted(data.subjects, key=lambda item: (item.sort_order, item.code)):
        subject_sheet.append(
            [
                subject_row.code,
                subject_row.display_name,
                _school_level_label(subject_row.school_level),
                subject_row.sort_order,
                _yes_no(subject_row.active),
            ]
        )
    _add_list(subject_sheet, "C2:C10000", '"小学校,中学校,高校"')
    _add_whole(subject_sheet, "D2:D10000", 1, 9999)
    _add_list(subject_sheet, "E2:E10000", '"はい,いいえ"', allow_blank=True)

    qualification_sheet = workbook.create_sheet("講師対応科目")
    _setup_sheet(
        qualification_sheet,
        _QUALIFICATION_HEADERS,
        (18, 24, 24, 20, 28, 28, 14, 30),
        helper_columns={2, 3, 5, 6},
    )
    for index, qualification_row in enumerate(data.qualifications, start=2):
        qualification_sheet.append(
            [
                qualification_row.teacher_external_id,
                "",
                _lookup_formula(index, "A", "講師", "A", "D", "B"),
                qualification_row.subject_code,
                "",
                _lookup_formula(index, "D", "科目", "A", "B", "E"),
                _yes_no(qualification_row.can_teach),
                qualification_row.note,
            ]
        )
    _add_list(qualification_sheet, "A2:A10000", "=INDIRECT(\"'講師'!$A$2:$A$10000\")", True)
    _add_list(qualification_sheet, "B2:B10000", "=INDIRECT(\"'講師'!$D$2:$D$10000\")", True)
    _add_list(qualification_sheet, "D2:D10000", "=INDIRECT(\"'科目'!$A$2:$A$10000\")", True)
    _add_list(qualification_sheet, "E2:E10000", "=INDIRECT(\"'科目'!$B$2:$B$10000\")", True)
    _add_list(qualification_sheet, "G2:G10000", '"はい,いいえ"', True)

    regular_sheet = workbook.create_sheet("通常授業")
    _setup_sheet(
        regular_sheet,
        _REGULAR_HEADERS,
        (18, 24, 24, 20, 28, 28, 20, 26, 26, 18, 14, 30),
        helper_columns={2, 3, 5, 6, 8, 9},
    )
    for index, lesson_row in enumerate(data.regular_lessons, start=2):
        regular_sheet.append(
            [
                lesson_row.student_external_id,
                "",
                _lookup_formula(index, "A", "生徒", "A", "D", "B"),
                lesson_row.subject_code,
                "",
                _lookup_formula(index, "D", "科目", "A", "B", "E"),
                lesson_row.regular_teacher_external_id,
                "",
                _lookup_formula(index, "G", "講師", "A", "D", "H"),
                lesson_row.regular_teacher_priority,
                _yes_no(lesson_row.one_to_one_required),
                lesson_row.note,
            ]
        )
    _add_list(regular_sheet, "A2:A10000", "=INDIRECT(\"'生徒'!$A$2:$A$10000\")", True)
    _add_list(regular_sheet, "B2:B10000", "=INDIRECT(\"'生徒'!$D$2:$D$10000\")", True)
    _add_list(regular_sheet, "D2:D10000", "=INDIRECT(\"'科目'!$A$2:$A$10000\")", True)
    _add_list(regular_sheet, "E2:E10000", "=INDIRECT(\"'科目'!$B$2:$B$10000\")", True)
    _add_list(regular_sheet, "G2:G10000", "=INDIRECT(\"'講師'!$A$2:$A$10000\")", True)
    _add_list(regular_sheet, "H2:H10000", "=INDIRECT(\"'講師'!$D$2:$D$10000\")", True)
    _add_whole(regular_sheet, "J2:J10000", 1, 5, allow_blank=True)
    _add_list(regular_sheet, "K2:K10000", '"はい,いいえ"', True)

    # 空行までソート対象へ含めない。フィルター範囲は値がある最終行までに限定する。
    for sheet in workbook.worksheets:
        _finish_rows(sheet)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            prefix=f".{destination.stem}_",
            suffix=".xlsx.tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        workbook.save(temporary)
        os.replace(temporary, destination)
        temporary = None
    finally:
        workbook.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_shared_roster(
    path: Path,
    *,
    reserved_student_ids: Iterable[str] = (),
    reserved_teacher_ids: Iterable[str] = (),
) -> SharedRosterData:
    """共通名簿を検証し、名前選択列も解決して正規化したデータを返す。"""
    source = path.expanduser().resolve()
    try:
        workbook = load_workbook(source, data_only=False, read_only=False)
    except (OSError, ValueError) as exc:
        raise SharedRosterError("共通名簿を読み込めませんでした。") from exc
    try:
        missing = [name for name in _SHEETS if name not in workbook.sheetnames]
        if missing:
            raise SharedRosterError(f"必要なシートがありません: {', '.join(missing)}")
        errors: list[str] = []
        students = _read_students(workbook["生徒"], errors, reserved_student_ids)
        teachers = _read_teachers(workbook["講師"], errors, reserved_teacher_ids)
        subjects = _read_subjects(workbook["科目"], errors)
        qualifications = _read_qualifications(
            workbook["講師対応科目"], students, teachers, subjects, errors
        )
        regular_lessons = _read_regular_lessons(
            workbook["通常授業"], students, teachers, subjects, errors
        )
        if errors:
            detail = "\n".join(f"・{message}" for message in errors[:20])
            suffix = "\n（ほかにもエラーがあります）" if len(errors) > 20 else ""
            raise SharedRosterError(f"共通名簿に入力エラーがあります。\n{detail}{suffix}")
        return SharedRosterData(
            tuple(students),
            tuple(teachers),
            tuple(subjects),
            tuple(qualifications),
            tuple(regular_lessons),
        )
    finally:
        workbook.close()


def _read_students(
    sheet: Any,
    errors: list[str],
    reserved_external_ids: Iterable[str] = (),
) -> list[SharedStudent]:
    result: list[SharedStudent] = []
    used: set[str] = set()
    rows = _rows(sheet, len(_STUDENT_HEADERS))
    reserved = {value.strip() for value in reserved_external_ids if value.strip()}
    reserved.update(_text(values[0]) for _row_number, values in rows if _text(values[0]))
    for row_number, values in rows:
        if _empty(values):
            continue
        external_id = _text(values[0])
        if not external_id:
            external_id = next_person_external_id(reserved, prefix="S")
            reserved.add(external_id)
        surname = _text(values[1])
        given_name = _text(values[2])
        grade = grade_from_excel(_text(values[4]))
        if external_id in used:
            errors.append(f"生徒 {row_number}行: 生徒ID「{external_id}」が重複しています")
            continue
        used.add(external_id)
        if not surname:
            errors.append(f"生徒 {row_number}行: 姓は必須です")
        if grade not in INTERNAL_GRADE_OPTIONS:
            errors.append(f"生徒 {row_number}行: 学年はS1～S6、J1～J3、H1～H3から選択してください")
        maximum = _integer(values[5], 2)
        if not 1 <= maximum <= 3:
            errors.append(f"生徒 {row_number}行: 最大連続コマ数は1～3です")
        result.append(
            SharedStudent(
                external_id,
                surname,
                given_name,
                grade,
                maximum,
                _boolean(values[6], False),
                _active(values[7]),
                _text(values[8]),
            )
        )
    return result


def _read_teachers(
    sheet: Any,
    errors: list[str],
    reserved_external_ids: Iterable[str] = (),
) -> list[SharedTeacher]:
    result: list[SharedTeacher] = []
    used: set[str] = set()
    rows = _rows(sheet, len(_TEACHER_HEADERS))
    reserved = {value.strip() for value in reserved_external_ids if value.strip()}
    reserved.update(_text(values[0]) for _row_number, values in rows if _text(values[0]))
    for row_number, values in rows:
        if _empty(values):
            continue
        external_id = _text(values[0])
        if not external_id:
            external_id = next_person_external_id(reserved, prefix="T")
            reserved.add(external_id)
        surname, given_name = _text(values[1]), _text(values[2])
        if external_id in used:
            errors.append(f"講師 {row_number}行: 講師ID「{external_id}」が重複しています")
            continue
        used.add(external_id)
        if not surname:
            errors.append(f"講師 {row_number}行: 姓は必須です")
        result.append(
            SharedTeacher(
                external_id,
                surname,
                given_name,
                _boolean(values[4], False),
                _active(values[5]),
                _text(values[6]),
            )
        )
    return result


def _read_subjects(sheet: Any, errors: list[str]) -> list[SharedSubject]:
    result: list[SharedSubject] = []
    used: set[str] = set()
    for row_number, values in _rows(sheet, len(_SUBJECT_HEADERS)):
        if _empty(values):
            continue
        code, name, level = _text(values[0]), _text(values[1]), _text(values[2])
        level_code = _school_level_code(level)
        if not code or not name or not level_code:
            errors.append(f"科目 {row_number}行: コード・表示名・学校段階は必須です")
            continue
        if code in used:
            errors.append(f"科目 {row_number}行: 科目コード「{code}」が重複しています")
            continue
        used.add(code)
        order = _integer(values[3], len(result) + 1)
        result.append(SharedSubject(code, name, level_code, order, _boolean(values[4], True)))
    return result


def _read_qualifications(
    sheet: Any,
    students: list[SharedStudent],
    teachers: list[SharedTeacher],
    subjects: list[SharedSubject],
    errors: list[str],
) -> list[SharedQualification]:
    del students
    teacher_by_name = _unique_name_map(teachers)
    teacher_ids = {row.external_id for row in teachers}
    subject_by_name = _unique_subject_name_map(subjects)
    subject_codes = {row.code for row in subjects}
    result: list[SharedQualification] = []
    used: set[tuple[str, str]] = set()
    for row_number, values in _rows(sheet, len(_QUALIFICATION_HEADERS)):
        if _empty(values):
            continue
        teacher_id = _text(values[0]) or teacher_by_name.get(_text(values[1]), "")
        subject_code = _text(values[3]) or subject_by_name.get(_text(values[4]), "")
        if teacher_id not in teacher_ids:
            errors.append(f"講師対応科目 {row_number}行: 講師が基本情報にありません")
        if subject_code not in subject_codes:
            errors.append(f"講師対応科目 {row_number}行: 科目が科目シートにありません")
        key = (teacher_id, subject_code)
        if key in used:
            errors.append(f"講師対応科目 {row_number}行: 講師と科目の組が重複しています")
            continue
        used.add(key)
        result.append(
            SharedQualification(
                teacher_id, subject_code, _boolean(values[6], True), _text(values[7])
            )
        )
    return result


def _read_regular_lessons(
    sheet: Any,
    students: list[SharedStudent],
    teachers: list[SharedTeacher],
    subjects: list[SharedSubject],
    errors: list[str],
) -> list[SharedRegularLesson]:
    student_by_name = _unique_name_map(students)
    teacher_by_name = _unique_name_map(teachers)
    subject_by_name = _unique_subject_name_map(subjects)
    student_ids = {row.external_id for row in students}
    teacher_ids = {row.external_id for row in teachers}
    subject_codes = {row.code for row in subjects}
    result: list[SharedRegularLesson] = []
    used: set[tuple[str, str]] = set()
    for row_number, values in _rows(sheet, len(_REGULAR_HEADERS)):
        if _empty(values):
            continue
        student_id = _text(values[0]) or student_by_name.get(_text(values[1]), "")
        subject_code = _text(values[3]) or subject_by_name.get(_text(values[4]), "")
        teacher_id = _text(values[6]) or teacher_by_name.get(_text(values[7]), "")
        if student_id not in student_ids:
            errors.append(f"通常授業 {row_number}行: 生徒が基本情報にありません")
        if subject_code not in subject_codes:
            errors.append(f"通常授業 {row_number}行: 科目が科目シートにありません")
        if teacher_id and teacher_id not in teacher_ids:
            errors.append(f"通常授業 {row_number}行: 通常担当講師が基本情報にありません")
        key = (student_id, subject_code)
        if key in used:
            errors.append(f"通常授業 {row_number}行: 生徒と科目の組が重複しています")
            continue
        used.add(key)
        priority = _integer(values[9], 3)
        if not 1 <= priority <= 5:
            errors.append(f"通常授業 {row_number}行: 優先度は1～5です")
        result.append(
            SharedRegularLesson(
                student_id,
                subject_code,
                teacher_id,
                priority,
                _boolean(values[10], False),
                _text(values[11]),
            )
        )
    return result


def _setup_sheet(
    sheet: Any,
    headers: tuple[str, ...],
    widths: tuple[int, ...],
    *,
    helper_columns: set[int] | None = None,
) -> None:
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A2"
    sheet.row_dimensions[1].height = 34
    sheet.append(headers)
    helpers = helper_columns or set()
    for index, (cell, width) in enumerate(zip(sheet[1], widths, strict=True), start=1):
        cell.fill = _HELPER_FILL if index in helpers else _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.comment = Comment(
            "（必須）は入力必須です。空欄時の既定値は列の入力規則に従います。",
            "夏期講習時間割作成アプリ",
        )
        sheet.column_dimensions[cell.column_letter].width = width


def _finish_rows(sheet: Any) -> None:
    last_row = max(sheet.max_row, 2)
    last_column = sheet.cell(1, sheet.max_column).column_letter
    sheet.auto_filter.ref = f"A1:{last_column}{last_row}"
    for row in sheet.iter_rows(min_row=2, max_row=last_row):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=_THIN_GREY)


def _mark_auto_id_header(sheet: Any, person_label: str, example: str) -> None:
    sheet["A1"].comment = Comment(
        f"入力不要です。{person_label}の姓などを入力し、アプリで反映すると"
        f"{example}形式のIDを自動採番してこの列へ書き戻します。",
        "夏期講習時間割作成アプリ",
    )


def _grey_inactive(sheet: Any, active_column: str, column_count: int) -> None:
    last_column = sheet.cell(1, column_count).column_letter
    sheet.conditional_formatting.add(
        f"A2:{last_column}{_MAX_ROW}",
        _formula_rule(formula=[f'${active_column}2="☐ 退籍"'], fill=_INACTIVE_FILL),
    )


def _add_list(
    sheet: Any,
    cells: str,
    formula: str,
    allow_blank: bool = False,
) -> None:
    validation = DataValidation(type="list", formula1=formula, allow_blank=allow_blank)
    validation.errorTitle = "入力値を確認してください"
    validation.error = "一覧から選択してください。"
    validation.showErrorMessage = True
    sheet.add_data_validation(validation)
    validation.add(cells)


def _add_whole(
    sheet: Any,
    cells: str,
    minimum: int,
    maximum: int,
    allow_blank: bool = False,
) -> None:
    validation = DataValidation(
        type="whole",
        operator="between",
        formula1=str(minimum),
        formula2=str(maximum),
        allow_blank=allow_blank,
    )
    validation.errorTitle = "入力値を確認してください"
    validation.error = f"{minimum}～{maximum}の整数を入力してください。"
    validation.showErrorMessage = True
    sheet.add_data_validation(validation)
    validation.add(cells)


def _lookup_formula(
    row: int,
    id_column: str,
    source_sheet: str,
    source_id_column: str,
    source_name_column: str,
    selected_name_column: str,
) -> str:
    return (
        f"=IF({id_column}{row}<>\"\",IFERROR(INDEX('{source_sheet}'!${source_name_column}:${source_name_column},"
        f"MATCH({id_column}{row},'{source_sheet}'!${source_id_column}:${source_id_column},0)),\"⚠ 未登録\"),"
        f"{selected_name_column}{row})"
    )


def _rows(sheet: Any, width: int) -> list[tuple[int, tuple[object, ...]]]:
    return [
        (row_number, tuple(sheet.cell(row_number, column).value for column in range(1, width + 1)))
        for row_number in range(2, sheet.max_row + 1)
    ]


def _empty(values: tuple[object, ...]) -> bool:
    return all(not _text(value) for value in values if not _is_formula(value))


def _is_formula(value: object) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _text(value: object) -> str:
    if value is None or _is_formula(value):
        return ""
    return str(value).strip()


def _integer(value: object, default: int) -> int:
    text = _text(value)
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return -1


def _boolean(value: object, default: bool) -> bool:
    text = _text(value).casefold()
    if not text:
        return default
    if text in {"はい", "yes", "true", "1", "☑", "可", "在籍"}:
        return True
    if text in {"いいえ", "no", "false", "0", "☐", "不可", "退籍"}:
        return False
    return default


def _active(value: object) -> bool:
    text = _text(value)
    if not text:
        return True
    return text not in {"☐ 退籍", "退籍", "いいえ", "false", "FALSE", "0"}


def _membership(active: bool) -> str:
    return "☑ 在籍" if active else "☐ 退籍"


def _yes_no(value: bool) -> str:
    return "はい" if value else "いいえ"


def _school_level_label(value: str) -> str:
    return {
        "elementary": "小学校",
        "junior_high": "中学校",
        "high_school": "高校",
    }.get(value, value)


def _school_level_code(value: str) -> str:
    return {
        "小学校": "elementary",
        "中学校": "junior_high",
        "高校": "high_school",
        "elementary": "elementary",
        "junior_high": "junior_high",
        "high_school": "high_school",
    }.get(value, "")


def _full_name(surname: str, given_name: str) -> str:
    return " ".join(part for part in (surname.strip(), given_name.strip()) if part)


def _unique_name_map(rows: list[SharedStudent] | list[SharedTeacher]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.name, []).append(row.external_id)
    return {name: ids[0] for name, ids in grouped.items() if name and len(ids) == 1}


def _unique_subject_name_map(rows: list[SharedSubject]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.display_name, []).append(row.code)
    return {name: codes[0] for name, codes in grouped.items() if name and len(codes) == 1}


__all__ = [
    "SHARED_ROSTER_FILENAME",
    "SharedQualification",
    "SharedRegularLesson",
    "SharedRosterData",
    "SharedRosterError",
    "SharedStudent",
    "SharedSubject",
    "SharedTeacher",
    "empty_shared_roster",
    "read_shared_roster",
    "write_shared_roster",
]
