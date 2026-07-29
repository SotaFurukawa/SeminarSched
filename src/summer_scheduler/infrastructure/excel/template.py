"""master_data.xlsxテンプレートの生成。"""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Final, cast

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule, Rule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from summer_scheduler.infrastructure.excel.schema import (
    LESSON_REQUEST_SHEET,
    MASTER_DATA_SHEETS,
    QUALIFICATION_SHEET,
    SHEET_NAMES,
    STUDENT_SHEET,
    SUBJECT_SHEET,
    TEACHER_SHEET,
    ColumnSpec,
    SheetSpec,
    ValueKind,
)

_HEADER_FILL: Final = PatternFill(fill_type="solid", fgColor="1F4E78")
_EXAMPLE_FILL: Final = PatternFill(fill_type="solid", fgColor="FFF2CC")
_INACTIVE_FILL: Final = PatternFill(fill_type="solid", fgColor="E7E6E6")
_HEADER_FONT: Final = Font(color="FFFFFF", bold=True)
_HEADER_ALIGNMENT: Final = Alignment(horizontal="center", vertical="center", wrap_text=True)
_MAX_INPUT_ROW: Final = 10_000
_formula_rule = cast(Callable[..., Rule], FormulaRule)


def write_master_data_workbook(
    path: Path,
    rows_by_sheet: Mapping[str, Sequence[Mapping[str, object]]],
) -> None:
    """5シートのマスターデータブックを原子的に保存する。"""
    destination = path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    workbook.properties.title = "夏期講習時間割 マスターデータ"
    workbook.properties.subject = "生徒・講師・科目・講師対応科目・受講希望"
    workbook.properties.creator = "夏期講習時間割作成アプリ"

    for sheet_spec in MASTER_DATA_SHEETS:
        worksheet = workbook.create_sheet(sheet_spec.name)
        _write_sheet(
            worksheet,
            sheet_spec,
            rows_by_sheet.get(sheet_spec.name, ()),
        )

    _add_cross_sheet_validations(workbook)

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            prefix=f".{destination.stem}_",
            suffix=".xlsx.tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        workbook.save(temporary_path)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        workbook.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_sheet(
    worksheet: Any,
    sheet_spec: SheetSpec,
    rows: Sequence[Mapping[str, object]],
) -> None:
    worksheet.sheet_view.showGridLines = False
    worksheet.freeze_panes = "A2"
    worksheet.row_dimensions[1].height = 34

    worksheet.append(list(sheet_spec.headers))
    worksheet.append(_row_values(sheet_spec, sheet_spec.example))
    for row in rows:
        actual_row = dict(row)
        actual_row["is_example"] = False
        worksheet.append(_row_values(sheet_spec, actual_row))

    for column_number, column in enumerate(sheet_spec.columns, start=1):
        cell = worksheet.cell(row=1, column=column_number)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _HEADER_ALIGNMENT
        cell.comment = Comment(column.comment, "夏期講習時間割作成アプリ")
        worksheet.column_dimensions[get_column_letter(column_number)].width = column.width
        _add_column_validation(worksheet, column_number, column)

    last_column = get_column_letter(len(sheet_spec.columns))
    last_row = max(worksheet.max_row, 2)
    worksheet.auto_filter.ref = f"A1:{last_column}{last_row}"
    worksheet.auto_filter.add_filter_column(0, ["いいえ"])

    for cell in worksheet[2]:
        cell.fill = _EXAMPLE_FILL
        cell.alignment = Alignment(vertical="top", wrap_text=True)
    for row in worksheet.iter_rows(min_row=3, max_row=last_row):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    worksheet.conditional_formatting.add(
        f"A2:{last_column}{_MAX_INPUT_ROW}",
        _formula_rule(formula=['$A2="はい"'], fill=_EXAMPLE_FILL),
    )
    active_header = next(
        (
            index
            for index, column in enumerate(sheet_spec.columns, start=1)
            if column.key == "active"
        ),
        None,
    )
    if active_header is not None:
        active_letter = get_column_letter(active_header)
        worksheet.conditional_formatting.add(
            f"A2:{last_column}{_MAX_INPUT_ROW}",
            _formula_rule(
                formula=[f'${active_letter}2="いいえ"'],
                fill=_INACTIVE_FILL,
            ),
        )


def _row_values(sheet_spec: SheetSpec, row: Mapping[str, object]) -> list[object]:
    return [_excel_value(row.get(column.key)) for column in sheet_spec.columns]


def _excel_value(value: object) -> object:
    if isinstance(value, bool):
        return "はい" if value else "いいえ"
    return value


def _add_column_validation(
    worksheet: Any,
    column_number: int,
    column: ColumnSpec,
) -> None:
    column_letter = get_column_letter(column_number)
    target = f"{column_letter}2:{column_letter}{_MAX_INPUT_ROW}"
    validation: DataValidation | None = None

    if column.kind is ValueKind.BOOLEAN:
        validation = DataValidation(
            type="list",
            formula1='"はい,いいえ"',
            allow_blank=not column.required,
        )
        validation.error = "「はい」または「いいえ」を選択してください。"
    elif column.kind is ValueKind.INTEGER:
        if column.minimum is not None and column.maximum is not None:
            validation = DataValidation(
                type="whole",
                operator="between",
                formula1=str(column.minimum),
                formula2=str(column.maximum),
                allow_blank=not column.required,
            )
        elif column.minimum is not None:
            validation = DataValidation(
                type="whole",
                operator="greaterThanOrEqual",
                formula1=str(column.minimum),
                allow_blank=not column.required,
            )
        if validation is not None:
            validation.error = "指定された範囲内の整数を入力してください。"
    elif column.key == "school_level":
        validation = DataValidation(
            type="list",
            formula1='"小学校,中学校,高校"',
            allow_blank=False,
        )
        validation.error = "小学校・中学校・高校から選択してください。"

    if validation is not None:
        validation.errorTitle = "入力値を確認してください"
        validation.showErrorMessage = True
        validation.promptTitle = column.header
        validation.prompt = column.comment
        validation.showInputMessage = True
        worksheet.add_data_validation(validation)
        validation.add(target)


def _add_cross_sheet_validations(workbook: Any) -> None:
    student_ids = "=INDIRECT(\"'生徒'!$B$2:$B$10000\")"
    teacher_ids = "=INDIRECT(\"'講師'!$B$2:$B$10000\")"
    subject_codes = "=INDIRECT(\"'科目'!$B$2:$B$10000\")"

    _add_list_validation(workbook[QUALIFICATION_SHEET.name], "B", teacher_ids, False)
    _add_list_validation(workbook[QUALIFICATION_SHEET.name], "C", subject_codes, False)

    request_sheet = workbook[LESSON_REQUEST_SHEET.name]
    _add_list_validation(request_sheet, "B", student_ids, False)
    _add_list_validation(request_sheet, "C", subject_codes, False)
    for column_letter in ("E", "G", "H", "I"):
        _add_list_validation(request_sheet, column_letter, teacher_ids, True)

    # 定義変更時にシート名の取りこぼしを即座に検出する。
    if tuple(workbook.sheetnames) != SHEET_NAMES:
        raise AssertionError("master_data.xlsxのシート順が定義と一致しません。")
    if workbook[STUDENT_SHEET.name] is None:
        raise AssertionError
    if workbook[TEACHER_SHEET.name] is None:
        raise AssertionError
    if workbook[SUBJECT_SHEET.name] is None:
        raise AssertionError


def _add_list_validation(
    worksheet: Any,
    column_letter: str,
    formula: str,
    allow_blank: bool,
) -> None:
    validation = DataValidation(
        type="list",
        formula1=formula,
        allow_blank=allow_blank,
    )
    validation.errorTitle = "参照IDを確認してください"
    validation.error = "対応するマスターシートに存在するIDを選択してください。"
    validation.showErrorMessage = True
    worksheet.add_data_validation(validation)
    validation.add(f"{column_letter}2:{column_letter}{_MAX_INPUT_ROW}")
