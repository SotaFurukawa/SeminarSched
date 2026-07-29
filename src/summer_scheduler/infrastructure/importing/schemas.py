"""取込みファイルのcanonical field定義。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

DEFAULT_SLOT_CODES = ("Y", "Z", "A", "B", "C")


class FieldKind(StrEnum):
    """セルの基礎変換種別。"""

    TEXT = "text"
    DATE = "date"
    TIME = "time"
    AVAILABILITY = "availability"
    EXAMPLE_MARKER = "example_marker"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """canonical fieldと入力列候補の定義。"""

    key: str
    label: str
    kind: FieldKind = FieldKind.TEXT
    required: bool = False
    aliases: tuple[str, ...] = ()

    @property
    def accepted_headers(self) -> tuple[str, ...]:
        """自動マッピングで受け付ける列名。"""
        return (self.label, *self.aliases)


@dataclass(frozen=True, slots=True)
class ImportSchema:
    """1種類の表に対する列・重複・時刻順序の基礎契約。"""

    name: str
    fields: tuple[FieldSpec, ...]
    unique_keys: tuple[str, ...]
    ordered_time_fields: tuple[str, str] | None = None

    @property
    def fields_by_key(self) -> Mapping[str, FieldSpec]:
        """canonical keyから定義を引く読取り専用辞書。"""
        return MappingProxyType({field.key: field for field in self.fields})


def slot_key(code: str) -> str:
    """コマコードをcanonical keyへ変換する。"""
    normalized = code.strip()
    if not normalized:
        raise ValueError("コマコードは空にできません。")
    return f"slot:{normalized}"


def student_availability_schema(
    slot_codes: Sequence[str] = DEFAULT_SLOT_CODES,
) -> ImportSchema:
    """生徒アンケートの動的コマ列を含むschemaを返す。"""
    slots = _validated_slot_codes(slot_codes)
    return ImportSchema(
        name="student_availability",
        fields=(
            _example_field(),
            FieldSpec("student_id", "生徒ID", required=True, aliases=("生徒番号",)),
            FieldSpec("student_name", "生徒名", required=True, aliases=("氏名", "名前")),
            FieldSpec("subject_code", "科目コード", required=True, aliases=("科目",)),
            FieldSpec("date", "日付", FieldKind.DATE, required=True, aliases=("受講日",)),
            *(
                FieldSpec(
                    slot_key(code),
                    code,
                    FieldKind.AVAILABILITY,
                    required=True,
                    aliases=(f"{code}コマ", f"コマ{code}"),
                )
                for code in slots
            ),
            FieldSpec(
                "preferred_teacher_1",
                "第1希望講師ID",
                aliases=("第一希望講師ID", "第1希望講師"),
            ),
            FieldSpec(
                "preferred_teacher_2",
                "第2希望講師ID",
                aliases=("第二希望講師ID", "第2希望講師"),
            ),
            FieldSpec(
                "preferred_teacher_3",
                "第3希望講師ID",
                aliases=("第三希望講師ID", "第3希望講師"),
            ),
            FieldSpec("note", "備考", aliases=("コメント",)),
        ),
        unique_keys=("student_id", "date"),
    )


def teacher_availability_schema(
    slot_codes: Sequence[str] = DEFAULT_SLOT_CODES,
) -> ImportSchema:
    """講師アンケートの動的コマ列を含むschemaを返す。"""
    slots = _validated_slot_codes(slot_codes)
    return ImportSchema(
        name="teacher_availability",
        fields=(
            _example_field(),
            FieldSpec("teacher_id", "講師ID", required=True, aliases=("講師番号",)),
            FieldSpec("name", "講師名", required=True, aliases=("氏名", "名前")),
            FieldSpec("date", "日付", FieldKind.DATE, required=True, aliases=("出勤日",)),
            *(
                FieldSpec(
                    slot_key(code),
                    code,
                    FieldKind.AVAILABILITY,
                    required=True,
                    aliases=(f"{code}コマ", f"コマ{code}"),
                )
                for code in slots
            ),
            FieldSpec("note", "備考", aliases=("コメント",)),
        ),
        unique_keys=("teacher_id", "date"),
    )


def group_lesson_schema() -> ImportSchema:
    """group_lessons.xlsxの「集団授業」シートschemaを返す。"""
    return ImportSchema(
        name="group_lessons",
        fields=(
            _example_field(),
            FieldSpec(
                "group_lesson_id",
                "集団授業ID",
                required=True,
                aliases=("集団ID", "授業ID"),
            ),
            FieldSpec("grade", "学年", required=True),
            FieldSpec("subject_code", "科目コード", required=True, aliases=("科目",)),
            FieldSpec("course_name", "コース名"),
            FieldSpec("date", "日付", FieldKind.DATE, required=True),
            FieldSpec("start_time", "開始時刻", FieldKind.TIME, required=True),
            FieldSpec("end_time", "終了時刻", FieldKind.TIME, required=True),
            FieldSpec("teacher_id", "担当講師ID", aliases=("講師ID",)),
            FieldSpec("room", "教室"),
            FieldSpec("note", "備考", aliases=("コメント",)),
        ),
        unique_keys=("group_lesson_id",),
        ordered_time_fields=("start_time", "end_time"),
    )


def group_participant_schema() -> ImportSchema:
    """group_lessons.xlsxの「受講者」シートschemaを返す。"""
    return ImportSchema(
        name="group_lesson_participants",
        fields=(
            _example_field(),
            FieldSpec(
                "group_lesson_id",
                "集団授業ID",
                required=True,
                aliases=("集団ID", "授業ID"),
            ),
            FieldSpec("student_id", "生徒ID", required=True, aliases=("生徒番号",)),
        ),
        unique_keys=("group_lesson_id", "student_id"),
    )


def _example_field() -> FieldSpec:
    return FieldSpec(
        "example",
        "例示行",
        FieldKind.EXAMPLE_MARKER,
        aliases=("サンプル行", "取込対象外"),
    )


def _validated_slot_codes(slot_codes: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(code.strip() for code in slot_codes)
    if not normalized or any(not code for code in normalized):
        raise ValueError("コマコードを1件以上指定してください。")
    if len(set(normalized)) != len(normalized):
        raise ValueError("コマコードが重複しています。")
    return normalized
