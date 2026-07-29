"""マスターデータExcel入出力の公開契約。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType


class IssueSeverity(StrEnum):
    """取込み検証結果の重大度。"""

    ERROR = "error"
    WARNING = "warning"


class RowOperation(StrEnum):
    """プレビューで表示する行の反映種別。"""

    NEW = "new"
    UPDATE = "update"


@dataclass(frozen=True, slots=True)
class ImportIssue:
    """利用者へ表示できる、Excel上の位置を伴う検証結果。"""

    severity: IssueSeverity
    message: str
    sheet_name: str | None = None
    row_number: int | None = None
    column_name: str | None = None
    code: str = "validation"

    @property
    def location(self) -> str:
        """日本語の位置表現を返す。"""
        parts: list[str] = []
        if self.sheet_name is not None:
            parts.append(f"シート「{self.sheet_name}」")
        if self.row_number is not None:
            parts.append(f"{self.row_number}行")
        if self.column_name is not None:
            parts.append(f"列「{self.column_name}」")
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class ImportRow:
    """検証・正規化済みの取込み予定行。"""

    sheet_name: str
    row_number: int
    operation: RowOperation
    values: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ImportPreview:
    """利用者の確認画面へ渡す、まだDBへ反映していない取込み内容。"""

    source_path: Path
    project_id: int
    rows: tuple[ImportRow, ...]
    issues: tuple[ImportIssue, ...]
    new_counts: Mapping[str, int]
    update_counts: Mapping[str, int]

    @property
    def has_errors(self) -> bool:
        """反映を禁止すべきエラーが1件以上あるか。"""
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def warning_count(self) -> int:
        """警告件数。"""
        return sum(issue.severity is IssueSeverity.WARNING for issue in self.issues)

    @property
    def error_count(self) -> int:
        """エラー件数。"""
        return sum(issue.severity is IssueSeverity.ERROR for issue in self.issues)


@dataclass(frozen=True, slots=True)
class ImportResult:
    """反映処理がflushまで完了した時点の件数。"""

    new_counts: Mapping[str, int]
    update_counts: Mapping[str, int]
    warning_count: int


class MasterDataImportError(ValueError):
    """検証エラーのあるプレビューを反映しようとした場合の例外。"""


def immutable_counts(counts: Mapping[str, int]) -> Mapping[str, int]:
    """件数辞書を呼出側から変更できない形へ変換する。"""
    return MappingProxyType(dict(counts))
