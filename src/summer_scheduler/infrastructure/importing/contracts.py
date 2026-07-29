"""アンケート・集団授業のファイル取込みで共有する公開契約。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType


class SourceFormat(StrEnum):
    """対応する入力ファイル形式。"""

    XLSX = "xlsx"
    CSV = "csv"


class CsvEncoding(StrEnum):
    """CSVで利用できる文字コード。"""

    AUTO = "auto"
    UTF_8_SIG = "utf-8-sig"
    UTF_8 = "utf-8"
    CP932 = "cp932"


class IssueSeverity(StrEnum):
    """ファイル構造・セル検証の重大度。"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ImportIssue:
    """入力元の位置と値を伴う、DB非依存の検証結果。"""

    severity: IssueSeverity
    code: str
    message: str
    sheet_name: str | None = None
    row_number: int | None = None
    column_key: str | None = None
    source_header: str | None = None
    raw_value: object = None

    @property
    def location(self) -> str:
        """利用者向けの日本語位置表現を返す。"""
        parts: list[str] = []
        if self.sheet_name:
            parts.append(f"シート「{self.sheet_name}」")
        if self.row_number is not None:
            parts.append(f"{self.row_number}行")
        if self.source_header:
            parts.append(f"列「{self.source_header}」")
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class SheetSummary:
    """ブック内の1シート、またはCSV全体の構造情報。"""

    name: str
    headers: tuple[str, ...]
    data_row_count: int


@dataclass(frozen=True, slots=True)
class SourceInspection:
    """ファイル選択直後にウィザードへ表示する構造情報。"""

    source_path: Path
    source_format: SourceFormat
    sheets: tuple[SheetSummary, ...]
    detected_encoding: CsvEncoding | None = None


@dataclass(frozen=True, slots=True)
class SourceRow:
    """列マッピング前の元セル値を保持する1行。"""

    row_number: int
    raw_values: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class SourceTable:
    """選択済みシートまたはCSVの表データ。"""

    source_path: Path
    source_format: SourceFormat
    sheet_name: str
    headers: tuple[str, ...]
    rows: tuple[SourceRow, ...]
    detected_encoding: CsvEncoding | None = None


@dataclass(frozen=True, slots=True)
class NormalizedRow:
    """canonical keyへマッピングし、型を正規化した行。"""

    sheet_name: str
    row_number: int
    values: Mapping[str, object]
    raw_values: Mapping[str, object]
    unmapped_values: Mapping[str, object]
    issues: tuple[ImportIssue, ...] = ()

    @property
    def has_errors(self) -> bool:
        """この行に反映を禁止すべきエラーがあるか。"""
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)


@dataclass(frozen=True, slots=True)
class MappingResult:
    """列マッピングと基礎検証の結果。"""

    rows: tuple[NormalizedRow, ...]
    issues: tuple[ImportIssue, ...]
    applied_mapping: Mapping[str, str]
    unmapped_headers: tuple[str, ...]
    skipped_example_rows: tuple[int, ...] = ()

    @property
    def has_errors(self) -> bool:
        """エラーが1件以上あるか。"""
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def error_count(self) -> int:
        """エラー件数。"""
        return sum(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def warning_count(self) -> int:
        """警告件数。"""
        return sum(issue.severity is IssueSeverity.WARNING for issue in self.issues)


class ImportSourceError(ValueError):
    """入力ファイルを安全に読めない場合の例外。"""


class MappingConfigurationError(ValueError):
    """呼出側が矛盾する列マッピングを指定した場合の例外。"""


def immutable_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    """セル辞書を呼出側から変更できない形にする。"""
    return MappingProxyType(dict(values))


def immutable_string_mapping(values: Mapping[str, str]) -> Mapping[str, str]:
    """列マッピングを呼出側から変更できない形にする。"""
    return MappingProxyType(dict(values))
