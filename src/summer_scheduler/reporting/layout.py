"""ExcelとPDFが共有する、表ベースのページレイアウトモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CellRole = Literal["title", "subtitle", "metadata", "header", "data", "legend", "closed"]
HorizontalAlignment = Literal["left", "center", "right"]


@dataclass(frozen=True, slots=True)
class LayoutCell:
    text: str
    role: CellRole = "data"
    column_span: int = 1
    row_span: int = 1
    style_codes: tuple[str, ...] = ()
    alignment: HorizontalAlignment = "left"

    def __post_init__(self) -> None:
        if self.column_span < 1 or self.row_span < 1:
            raise ValueError("セル結合数は1以上である必要があります")


@dataclass(frozen=True, slots=True)
class LayoutRow:
    cells: tuple[LayoutCell, ...]
    height_points_optional: float | None = None


@dataclass(frozen=True, slots=True)
class LayoutTable:
    rows: tuple[LayoutRow, ...]
    column_widths: tuple[float, ...]
    repeat_header_rows: int = 0

    def __post_init__(self) -> None:
        if not self.column_widths or any(width <= 0 for width in self.column_widths):
            raise ValueError("表の列幅は正の値で指定してください")
        if self.repeat_header_rows < 0:
            raise ValueError("繰り返し見出し行数は0以上で指定してください")


@dataclass(frozen=True, slots=True)
class LayoutPage:
    heading: str
    subheading: str
    tables: tuple[LayoutTable, ...]
    footer_note: str = ""


@dataclass(frozen=True, slots=True)
class LayoutSection:
    name: str
    pages: tuple[LayoutPage, ...]


@dataclass(frozen=True, slots=True)
class LayoutDocument:
    report_code: str
    title: str
    campus_name: str
    course_name: str
    updated_text: str
    sections: tuple[LayoutSection, ...]
    page_size: str
    orientation: str
    margin_mm: float
    font_size: float
    logo_path_optional: str | None = None

    @property
    def page_count(self) -> int:
        return sum(len(section.pages) for section in self.sections)


__all__ = [
    "CellRole",
    "HorizontalAlignment",
    "LayoutCell",
    "LayoutDocument",
    "LayoutPage",
    "LayoutRow",
    "LayoutSection",
    "LayoutTable",
]
