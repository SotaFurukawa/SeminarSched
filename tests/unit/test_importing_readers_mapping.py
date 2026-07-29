"""Phase 3のファイル読取り・列マッピング・基礎検証テスト。"""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from summer_scheduler.infrastructure.importing import (
    CsvEncoding,
    ImportSourceError,
    IssueSeverity,
    inspect_source,
    map_table,
    preview_source_table,
    read_source_table,
    student_availability_schema,
    suggest_column_mapping,
)


@pytest.mark.parametrize(
    ("encoding", "expected"),
    [
        ("utf-8-sig", CsvEncoding.UTF_8_SIG),
        ("utf-8", CsvEncoding.UTF_8),
        ("cp932", CsvEncoding.CP932),
    ],
)
def test_csv_encoding_detection_and_manual_mapping(
    tmp_path: Path,
    encoding: str,
    expected: CsvEncoding,
) -> None:
    destination = tmp_path / f"希望回答_{encoding}.csv"
    content = (
        "生徒番号,お名前,対象科目,受講日,Y枠,自由記入,校内管理_優先度5\n"
        "S001,架空 青空,JH_MATH,2026/08/04,2,希望します,変更禁止\n"
    )
    destination.write_bytes(content.encode(encoding))

    inspection = inspect_source(destination)
    table = read_source_table(destination)
    result = map_table(
        table,
        student_availability_schema(("Y",)),
        {
            "student_id": "生徒番号",
            "student_name": "お名前",
            "subject_code": "対象科目",
            "date": "受講日",
            "slot:Y": "Y枠",
            "note": "自由記入",
        },
    )

    assert inspection.detected_encoding is expected
    assert table.detected_encoding is expected
    assert not result.has_errors
    assert result.rows[0].values["date"] == date(2026, 8, 4)
    assert result.rows[0].values["slot:Y"] == 2
    assert result.unmapped_headers == ("校内管理_優先度5",)
    assert result.rows[0].unmapped_values["校内管理_優先度5"] == "変更禁止"
    assert result.rows[0].raw_values["お名前"] == "架空 青空"


def test_xlsx_multiple_sheets_can_be_enumerated_selected_and_previewed(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "複数シート.xlsx"
    workbook = Workbook()
    first = workbook.worksheets[0]
    first.title = "回答A"
    first.append(["生徒ID", "日付"])
    first.append(["S001", "2026-08-01"])
    first.append(["S002", "2026-08-02"])
    second = workbook.create_sheet("回答B")
    second.append(["講師ID", "日付"])
    second.append(["T001", "2026-08-01"])
    workbook.save(destination)
    workbook.close()

    inspection = inspect_source(destination)
    assert tuple(sheet.name for sheet in inspection.sheets) == ("回答A", "回答B")
    with pytest.raises(ImportSourceError, match="選択"):
        read_source_table(destination)

    preview = preview_source_table(destination, sheet_name="回答A", row_limit=1)
    assert preview.headers == ("生徒ID", "日付")
    assert len(preview.rows) == 1
    assert preview.rows[0].row_number == 2


def test_mapping_skips_example_and_reports_invalid_values_and_duplicate(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "入力値検証.csv"
    destination.write_text(
        "例示行,生徒ID,生徒名,科目コード,日付,Y,備考\n"
        "はい,SAMPLE,架空 例,JH_MATH,不正,9,取込対象外\n"
        "いいえ,S001,架空 一郎,JH_MATH,不正日付,3,不正\n"
        "いいえ,S002,架空 二郎,JH_MATH,2026-08-04,2,正常\n"
        "いいえ,S002,架空 二郎,JH_ENGLISH,2026-08-04,1,重複\n",
        encoding="utf-8",
    )

    table = read_source_table(destination)
    result = map_table(table, student_availability_schema(("Y",)))
    issue_codes = {issue.code for issue in result.issues}

    assert result.skipped_example_rows == (2,)
    assert len(result.rows) == 3
    assert result.has_errors
    assert {"invalid_date", "invalid_availability", "duplicate_row"} <= issue_codes
    assert all(issue.severity is IssueSeverity.ERROR for issue in result.issues)
    assert result.rows[0].has_errors
    assert result.rows[1].values["slot:Y"] == 2


def test_missing_required_column_is_reported_once_at_header_level(tmp_path: Path) -> None:
    destination = tmp_path / "列不足.csv"
    destination.write_text(
        "生徒ID,生徒名,日付,Y\nS001,架空 青空,2026-08-01,1\n",
        encoding="utf-8",
    )

    result = map_table(
        read_source_table(destination),
        student_availability_schema(("Y",)),
    )

    missing = [issue for issue in result.issues if issue.code == "required_mapping_missing"]
    assert len(missing) == 1
    assert missing[0].column_key == "subject_code"
    assert missing[0].row_number == 1


def test_group_time_order_is_a_basic_mapping_error(tmp_path: Path) -> None:
    destination = tmp_path / "集団.csv"
    destination.write_text(
        "集団授業ID,学年,科目コード,日付,開始時刻,終了時刻\n"
        "G001,中3,JH_MATH,2026-08-01,18:30,17:10\n",
        encoding="utf-8",
    )
    from summer_scheduler.infrastructure.importing import group_lesson_schema

    result = map_table(read_source_table(destination), group_lesson_schema())

    assert any(issue.code == "invalid_time_order" for issue in result.issues)


def test_suggest_mapping_normalizes_width_case_and_spaces() -> None:
    schema = student_availability_schema(("Y",))

    mapping = suggest_column_mapping(
        schema,
        (" 生徒ＩＤ ", "氏 名", "科目", "受講日", "ｙコマ"),
    )

    assert mapping["student_id"] == " 生徒ＩＤ "
    assert mapping["student_name"] == "氏 名"
    assert mapping["slot:Y"] == "ｙコマ"
