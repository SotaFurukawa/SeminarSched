"""master_data.xlsxのシート・列定義とセル値の正規化。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Final


class ValueKind(StrEnum):
    """Excelセルの期待型。"""

    TEXT = "text"
    INTEGER = "integer"
    BOOLEAN = "boolean"


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """1列の契約。"""

    key: str
    header: str
    kind: ValueKind
    required: bool
    comment: str
    width: float
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True, slots=True)
class SheetSpec:
    """1シートの契約。"""

    name: str
    columns: tuple[ColumnSpec, ...]
    unique_keys: tuple[str, ...]
    example: dict[str, object]

    @property
    def headers(self) -> tuple[str, ...]:
        """定義順の日本語ヘッダー。"""
        return tuple(column.header for column in self.columns)

    @property
    def columns_by_header(self) -> dict[str, ColumnSpec]:
        """日本語ヘッダーをキーとする列定義。"""
        return {column.header: column for column in self.columns}


EXAMPLE_COLUMN: Final = ColumnSpec(
    "is_example",
    "例示行",
    ValueKind.BOOLEAN,
    False,
    "「はい」の行は説明用の架空データです。再取込み時には反映されません。",
    11,
)

STUDENT_SHEET: Final = SheetSpec(
    name="生徒",
    unique_keys=("external_id",),
    columns=(
        EXAMPLE_COLUMN,
        ColumnSpec(
            "external_id",
            "生徒ID",
            ValueKind.TEXT,
            True,
            "ファイル内で重複しない安定したID。先頭ゼロを保つため文字列で入力します。",
            17,
        ),
        ColumnSpec("name", "氏名", ValueKind.TEXT, True, "生徒の氏名。", 18),
        ColumnSpec("grade", "学年", ValueKind.TEXT, True, "例：中学2年。", 14),
        ColumnSpec(
            "default_max_consecutive_slots",
            "標準最大連続コマ数",
            ValueKind.INTEGER,
            True,
            "通常許可する最大連続コマ数。1以上。",
            20,
            minimum=1,
        ),
        ColumnSpec(
            "allow_gap",
            "空きコマ許可",
            ValueKind.BOOLEAN,
            True,
            "「はい」または「いいえ」。",
            14,
        ),
        ColumnSpec("note", "備考", ValueKind.TEXT, False, "任意の備考。", 28),
        ColumnSpec(
            "active",
            "有効",
            ValueKind.BOOLEAN,
            True,
            "使用中は「はい」、使用停止は「いいえ」。",
            11,
        ),
    ),
    example={
        "is_example": True,
        "external_id": "S-EXAMPLE",
        "name": "架空 花子",
        "grade": "中学2年",
        "default_max_consecutive_slots": 2,
        "allow_gap": False,
        "note": "この行は架空の例示行で、取込み時に無視されます。",
        "active": True,
    },
)

TEACHER_SHEET: Final = SheetSpec(
    name="講師",
    unique_keys=("external_id",),
    columns=(
        EXAMPLE_COLUMN,
        ColumnSpec(
            "external_id",
            "講師ID",
            ValueKind.TEXT,
            True,
            "ファイル内で重複しない安定したID。",
            17,
        ),
        ColumnSpec("name", "氏名", ValueKind.TEXT, True, "講師の氏名。", 18),
        ColumnSpec(
            "allow_gap",
            "空きコマ許可",
            ValueKind.BOOLEAN,
            True,
            "「はい」または「いいえ」。",
            14,
        ),
        ColumnSpec("note", "備考", ValueKind.TEXT, False, "任意の備考。", 28),
        ColumnSpec(
            "active",
            "有効",
            ValueKind.BOOLEAN,
            True,
            "使用中は「はい」、使用停止は「いいえ」。",
            11,
        ),
    ),
    example={
        "is_example": True,
        "external_id": "T-EXAMPLE",
        "name": "架空 太郎",
        "allow_gap": False,
        "note": "この行は架空の例示行で、取込み時に無視されます。",
        "active": True,
    },
)

SUBJECT_SHEET: Final = SheetSpec(
    name="科目",
    unique_keys=("code",),
    columns=(
        EXAMPLE_COLUMN,
        ColumnSpec(
            "code",
            "科目コード",
            ValueKind.TEXT,
            True,
            "重複しない安定した英数字コード。",
            18,
        ),
        ColumnSpec("display_name", "表示名", ValueKind.TEXT, True, "日本語の科目名。", 22),
        ColumnSpec(
            "school_level",
            "学校段階",
            ValueKind.TEXT,
            True,
            "小学校・中学校・高校のいずれか。",
            14,
        ),
        ColumnSpec(
            "sort_order",
            "並び順",
            ValueKind.INTEGER,
            True,
            "一覧で使用する並び順。1以上。",
            11,
            minimum=1,
        ),
        ColumnSpec(
            "active",
            "有効",
            ValueKind.BOOLEAN,
            True,
            "使用中は「はい」、使用停止は「いいえ」。",
            11,
        ),
    ),
    example={
        "is_example": True,
        "code": "JH-MATH",
        "display_name": "中学校・数学（例）",
        "school_level": "中学校",
        "sort_order": 1,
        "active": True,
    },
)

QUALIFICATION_SHEET: Final = SheetSpec(
    name="講師対応科目",
    unique_keys=("teacher_external_id", "subject_code"),
    columns=(
        EXAMPLE_COLUMN,
        ColumnSpec(
            "teacher_external_id",
            "講師ID",
            ValueKind.TEXT,
            True,
            "講師シートに存在する講師ID。",
            17,
        ),
        ColumnSpec(
            "subject_code",
            "科目コード",
            ValueKind.TEXT,
            True,
            "科目シートに存在する科目コード。",
            18,
        ),
        ColumnSpec(
            "can_teach",
            "指導可能",
            ValueKind.BOOLEAN,
            True,
            "指導可能なら「はい」、不可なら「いいえ」。自動推定しません。",
            14,
        ),
        ColumnSpec("note", "備考", ValueKind.TEXT, False, "任意の備考。", 28),
    ),
    example={
        "is_example": True,
        "teacher_external_id": "T-EXAMPLE",
        "subject_code": "JH-MATH",
        "can_teach": True,
        "note": "この行は架空の例示行で、取込み時に無視されます。",
    },
)

LESSON_REQUEST_SHEET: Final = SheetSpec(
    name="受講希望",
    unique_keys=("student_external_id", "subject_code"),
    columns=(
        EXAMPLE_COLUMN,
        ColumnSpec(
            "student_external_id",
            "生徒ID",
            ValueKind.TEXT,
            True,
            "生徒シートに存在する生徒ID。",
            17,
        ),
        ColumnSpec(
            "subject_code",
            "科目コード",
            ValueKind.TEXT,
            True,
            "科目シートに存在する科目コード。",
            18,
        ),
        ColumnSpec(
            "required_sessions",
            "必要授業回数",
            ValueKind.INTEGER,
            True,
            "1以上の必要授業回数。",
            16,
            minimum=1,
        ),
        ColumnSpec(
            "regular_teacher_external_id",
            "通常担当講師ID",
            ValueKind.TEXT,
            False,
            "任意。優先度5の場合は必須です。",
            18,
        ),
        ColumnSpec(
            "regular_teacher_priority",
            "担当講師優先度",
            ValueKind.INTEGER,
            True,
            "1～5。5は通常担当講師に固定するハード制約です。",
            18,
            minimum=1,
            maximum=5,
        ),
        ColumnSpec(
            "preferred_teacher_1_external_id",
            "第1希望講師ID",
            ValueKind.TEXT,
            False,
            "任意の第1希望講師ID。",
            18,
        ),
        ColumnSpec(
            "preferred_teacher_2_external_id",
            "第2希望講師ID",
            ValueKind.TEXT,
            False,
            "任意の第2希望講師ID。",
            18,
        ),
        ColumnSpec(
            "preferred_teacher_3_external_id",
            "第3希望講師ID",
            ValueKind.TEXT,
            False,
            "任意の第3希望講師ID。",
            18,
        ),
        ColumnSpec(
            "one_to_one_required",
            "1対1必須",
            ValueKind.BOOLEAN,
            True,
            "「はい」は1対1を必須とするハード制約です。",
            13,
        ),
        ColumnSpec(
            "max_consecutive_slots_override",
            "最大連続コマ数上書き",
            ValueKind.INTEGER,
            False,
            "任意。生徒の標準値を上書きする場合は1以上。",
            22,
            minimum=1,
        ),
        ColumnSpec(
            "allow_gap_override",
            "空きコマ許可上書き",
            ValueKind.BOOLEAN,
            False,
            "任意。空欄なら生徒の標準設定を使用します。",
            20,
        ),
        ColumnSpec("note", "備考", ValueKind.TEXT, False, "任意の備考。", 28),
    ),
    example={
        "is_example": True,
        "student_external_id": "S-EXAMPLE",
        "subject_code": "JH-MATH",
        "required_sessions": 4,
        "regular_teacher_external_id": "T-EXAMPLE",
        "regular_teacher_priority": 3,
        "preferred_teacher_1_external_id": "T-EXAMPLE",
        "preferred_teacher_2_external_id": None,
        "preferred_teacher_3_external_id": None,
        "one_to_one_required": False,
        "max_consecutive_slots_override": None,
        "allow_gap_override": None,
        "note": "この行は架空の例示行で、取込み時に無視されます。",
    },
)

MASTER_DATA_SHEETS: Final = (
    STUDENT_SHEET,
    TEACHER_SHEET,
    SUBJECT_SHEET,
    QUALIFICATION_SHEET,
    LESSON_REQUEST_SHEET,
)
SHEETS_BY_NAME: Final = {sheet.name: sheet for sheet in MASTER_DATA_SHEETS}
SHEET_NAMES: Final = tuple(sheet.name for sheet in MASTER_DATA_SHEETS)


class CellValueError(ValueError):
    """セル値が列定義に合わない場合の例外。"""


def normalize_cell_value(value: object, column: ColumnSpec) -> object:
    """セル値をDBへ反映できるPython値へ正規化する。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        if column.required:
            raise CellValueError("必須項目です。")
        return None

    if column.kind is ValueKind.TEXT:
        if not isinstance(value, str):
            raise CellValueError("文字列で入力してください。")
        normalized = value.strip()
        if column.required and not normalized:
            raise CellValueError("空文字は使用できません。")
        return normalized or None

    if column.kind is ValueKind.INTEGER:
        normalized_integer = _normalize_integer(value)
        if column.minimum is not None and normalized_integer < column.minimum:
            raise CellValueError(f"{column.minimum}以上で入力してください。")
        if column.maximum is not None and normalized_integer > column.maximum:
            raise CellValueError(f"{column.maximum}以下で入力してください。")
        return normalized_integer

    if column.kind is ValueKind.BOOLEAN:
        return _normalize_boolean(value)

    raise AssertionError(f"未対応の値種別です: {column.kind}")


def _normalize_integer(value: object) -> int:
    if isinstance(value, bool):
        raise CellValueError("整数で入力してください。")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if isfinite(value) and value.is_integer():
            return int(value)
        raise CellValueError("整数で入力してください。")
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError as exc:
            raise CellValueError("整数で入力してください。") from exc
    raise CellValueError("整数で入力してください。")


def _normalize_boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, float) and value in (0.0, 1.0):
        return bool(int(value))
    if isinstance(value, str):
        normalized = value.strip().casefold()
        true_values = {"はい", "true", "1", "有効", "可", "○"}
        false_values = {"いいえ", "false", "0", "無効", "不可", "×"}
        if normalized in true_values:
            return True
        if normalized in false_values:
            return False
    raise CellValueError("「はい」または「いいえ」で入力してください。")
