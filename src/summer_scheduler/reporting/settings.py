"""プロジェクト単位で保存する出力設定の純粋モデル。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from string import Formatter
from typing import Final, Literal

PaperSize = Literal["A3", "A4"]
PageOrientation = Literal["landscape", "portrait"]
StudentPageMode = Literal["one_per_page", "combined"]

_HEX_COLOR: Final = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ALLOWED_FILENAME_FIELDS: Final = frozenset({"project", "report", "date"})
_ALLOWED_VISIBLE_FIELDS: Final = frozenset(
    {
        "grade",
        "subject",
        "one_to_one",
        "locked",
        "manual",
        "warning",
        "note",
        "group",
    }
)


class OutputSettingsValidationError(ValueError):
    """保存または出力に使えない設定を表す。"""


@dataclass(frozen=True, slots=True)
class StyleRule:
    """色だけに依存しない、表示色と文字記号の組。"""

    code: str
    label: str
    marker: str
    fill_color: str
    text_color: str = "#18212F"

    def validate(self) -> None:
        if not self.code.strip() or not self.label.strip():
            raise OutputSettingsValidationError("表示ルールのコードと名称は必須です")
        if not self.marker.strip() or len(self.marker) > 20:
            raise OutputSettingsValidationError(
                f"「{self.label}」の記号は1～20文字で指定してください"
            )
        for value in (self.fill_color, self.text_color):
            if not _HEX_COLOR.fullmatch(value):
                raise OutputSettingsValidationError(
                    f"「{self.label}」の色は#RRGGBB形式で指定してください"
                )


DEFAULT_STYLE_RULES: Final = (
    StyleRule("one_to_one", "1対1", "[1対1]", "#FFF1CC"),
    StyleRule("group", "集団授業", "[集団]", "#303846", "#FFFFFF"),
    StyleRule("locked", "ロック", "[固定]", "#DCEBFF"),
    StyleRule("warning", "警告", "[警告]", "#FFE0E0"),
    StyleRule("unconfirmed", "未確定", "[未確定]", "#E8E8E8"),
    StyleRule("manual", "手動変更", "[手]", "#EADFFF"),
    StyleRule("closed", "休校", "[休校]", "#333333", "#FFFFFF"),
)
STYLE_RULE_PRIORITY: Final = (
    "warning",
    "closed",
    "group",
    "one_to_one",
    "locked",
    "manual",
    "unconfirmed",
)


@dataclass(frozen=True, slots=True)
class OutputSettings:
    """レンダラーへ渡す、DBやQMLに依存しない出力設定。"""

    project_id: int
    paper_size: PaperSize = "A3"
    orientation: PageOrientation = "landscape"
    logo_path_optional: str | None = None
    visible_fields: tuple[str, ...] = tuple(sorted(_ALLOWED_VISIBLE_FIELDS))
    days_per_page: int = 2
    teacher_columns_per_page: int = 8
    font_size: float = 8.0
    margin_mm: float = 8.0
    file_name_pattern: str = "{report}"
    default_output_directory_optional: str | None = None
    student_page_mode: StudentPageMode = "one_per_page"
    csv_with_bom: bool = True
    style_rules: tuple[StyleRule, ...] = DEFAULT_STYLE_RULES

    def validate(self) -> None:
        if self.project_id < 1:
            raise OutputSettingsValidationError("出力設定のプロジェクトIDが不正です")
        if self.paper_size not in ("A3", "A4"):
            raise OutputSettingsValidationError("用紙はA3またはA4を指定してください")
        if self.orientation not in ("landscape", "portrait"):
            raise OutputSettingsValidationError("向きは横または縦を指定してください")
        if not 1 <= self.days_per_page <= 7:
            raise OutputSettingsValidationError("1ページの日数は1～7で指定してください")
        if not 1 <= self.teacher_columns_per_page <= 20:
            raise OutputSettingsValidationError("講師列数は1～20で指定してください")
        if not 5.0 <= self.font_size <= 18.0:
            raise OutputSettingsValidationError("文字サイズは5～18ptで指定してください")
        if not 0.0 <= self.margin_mm <= 30.0:
            raise OutputSettingsValidationError("余白は0～30mmで指定してください")
        if self.student_page_mode not in ("one_per_page", "combined"):
            raise OutputSettingsValidationError("生徒別の改ページ設定が不正です")
        unknown_fields = set(self.visible_fields) - _ALLOWED_VISIBLE_FIELDS
        if unknown_fields:
            names = "、".join(sorted(unknown_fields))
            raise OutputSettingsValidationError(f"未対応の表示項目です: {names}")
        style_codes = [rule.code for rule in self.style_rules]
        if len(set(style_codes)) != len(style_codes):
            raise OutputSettingsValidationError("表示ルールが重複しています")
        required_codes = {rule.code for rule in DEFAULT_STYLE_RULES}
        missing = required_codes - set(style_codes)
        if missing:
            names = "、".join(sorted(missing))
            raise OutputSettingsValidationError(f"必須の表示ルールがありません: {names}")
        for rule in self.style_rules:
            rule.validate()
        _validate_filename_pattern(self.file_name_pattern)

    def style(self, code: str) -> StyleRule:
        try:
            return next(rule for rule in self.style_rules if rule.code == code)
        except StopIteration as exc:
            raise OutputSettingsValidationError(f"表示ルールが見つかりません: {code}") from exc


@dataclass(frozen=True, slots=True)
class OutputSettingsDefaults:
    """設定ファイルから読み込む、プロジェクト非依存の帳票既定値。"""

    paper_size: PaperSize
    orientation: PageOrientation
    visible_fields: tuple[str, ...]
    days_per_page: int
    teacher_columns_per_page: int
    font_size: float
    margin_mm: float
    file_name_pattern: str
    default_output_directory_optional: str | None
    student_page_mode: StudentPageMode
    csv_with_bom: bool
    style_rules: tuple[StyleRule, ...]

    def for_project(
        self,
        project_id: int,
        *,
        logo_path_optional: str | None = None,
    ) -> OutputSettings:
        """校舎ロゴを合わせ、検証済みのプロジェクト設定へ変換する。"""
        settings = OutputSettings(
            project_id=project_id,
            paper_size=self.paper_size,
            orientation=self.orientation,
            logo_path_optional=logo_path_optional,
            visible_fields=self.visible_fields,
            days_per_page=self.days_per_page,
            teacher_columns_per_page=self.teacher_columns_per_page,
            font_size=self.font_size,
            margin_mm=self.margin_mm,
            file_name_pattern=self.file_name_pattern,
            default_output_directory_optional=self.default_output_directory_optional,
            student_page_mode=self.student_page_mode,
            csv_with_bom=self.csv_with_bom,
            style_rules=self.style_rules,
        )
        settings.validate()
        return settings


def _validate_filename_pattern(value: str) -> None:
    if not value.strip():
        raise OutputSettingsValidationError("ファイル名規則は空にできません")
    if any(character in value for character in '<>:"/\\|?*'):
        raise OutputSettingsValidationError("ファイル名規則に使用できない記号があります")
    if value.rstrip(" .") != value or value in {".", ".."}:
        raise OutputSettingsValidationError("ファイル名規則がWindowsで使用できません")
    try:
        parsed = tuple(Formatter().parse(value))
    except ValueError as exc:
        raise OutputSettingsValidationError("ファイル名規則の波括弧が不正です") from exc
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in _ALLOWED_FILENAME_FIELDS or format_spec or conversion:
            raise OutputSettingsValidationError(
                "ファイル名規則では{project}、{report}、{date}だけを使用できます"
            )


__all__ = [
    "DEFAULT_STYLE_RULES",
    "OutputSettings",
    "OutputSettingsDefaults",
    "OutputSettingsValidationError",
    "PageOrientation",
    "PaperSize",
    "StudentPageMode",
    "StyleRule",
    "STYLE_RULE_PRIORITY",
]
