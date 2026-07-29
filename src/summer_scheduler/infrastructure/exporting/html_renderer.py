"""共通レイアウトをQt rich text互換の印刷用HTMLへ変換する。"""

from __future__ import annotations

import base64
import html
from pathlib import Path

from PySide6.QtGui import QImageReader

from summer_scheduler.infrastructure.exporting.errors import OutputRenderError
from summer_scheduler.reporting.layout import (
    LayoutCell,
    LayoutDocument,
    LayoutPage,
    LayoutTable,
)
from summer_scheduler.reporting.settings import (
    STYLE_RULE_PRIORITY,
    OutputSettings,
    StyleRule,
)

_MAX_LOGO_BYTES = 5 * 1024 * 1024
_LOGO_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


class HtmlRenderError(OutputRenderError):
    """HTML生成に必要なローカル資源を安全に読めない場合の例外。"""


class HtmlRenderer:
    """ブラウザ固有機能に依存しないtable中心のHTMLを生成する。"""

    def render_page(
        self,
        document: LayoutDocument,
        page: LayoutPage,
        settings: OutputSettings,
        *,
        page_number: int,
        total_pages: int,
        font_family: str,
    ) -> str:
        settings.validate()
        logo = _logo_html(document.logo_path_optional)
        tables = "".join(self._table(table, settings) for table in page.tables)
        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            f"<style>{_css(document, font_family)}</style></head><body>"
            '<table class="page-header"><tr>'
            f'<td class="logo">{logo}</td>'
            '<td class="heading">'
            f'<div class="document-title">{_text(page.heading)}</div>'
            f'<div class="subheading">{_text(page.subheading)}</div>'
            "</td>"
            '<td class="metadata">'
            f"{_text(document.campus_name)}<br>{_text(document.course_name)}"
            f"<br>更新: {_text(document.updated_text)}</td>"
            "</tr></table>"
            f"{tables}"
            '<table class="page-footer"><tr>'
            f"<td>{_text(page.footer_note)}</td>"
            f'<td class="page-number">ページ {page_number} / {total_pages}</td>'
            "</tr></table>"
            "</body></html>"
        )

    def _table(self, table: LayoutTable, settings: OutputSettings) -> str:
        total_width = sum(table.column_widths)
        columns = "".join(
            f'<col width="{max(1, round(width / total_width * 100))}%">'
            for width in table.column_widths
        )
        rows = "".join(
            "<tr>" + "".join(self._cell(cell, settings) for cell in row.cells) + "</tr>"
            for row in table.rows
        )
        return f'<table class="report-table"><colgroup>{columns}</colgroup>{rows}</table>'

    def _cell(self, cell: LayoutCell, settings: OutputSettings) -> str:
        attributes: list[str] = []
        if cell.column_span > 1:
            attributes.append(f'colspan="{cell.column_span}"')
        if cell.row_span > 1:
            attributes.append(f'rowspan="{cell.row_span}"')
        rule = _highest_priority_rule(cell, settings)
        styles = [f"text-align:{cell.alignment}"]
        if rule is not None:
            styles.extend(
                (
                    f"background-color:{rule.fill_color}",
                    f"color:{rule.text_color}",
                )
            )
        attributes.append(f'class="role-{cell.role}"')
        attributes.append(f'style="{";".join(styles)}"')
        return f"<td {' '.join(attributes)}>{_text(cell.text) or '&nbsp;'}</td>"


def _highest_priority_rule(
    cell: LayoutCell,
    settings: OutputSettings,
) -> StyleRule | None:
    codes = set(cell.style_codes)
    for code in STYLE_RULE_PRIORITY:
        if code in codes:
            return settings.style(code)
    return None


def _css(document: LayoutDocument, font_family: str) -> str:
    family = font_family.replace("\\", "").replace('"', "")
    font_size = max(5.0, document.font_size)
    return (
        f'body{{font-family:"{family}";font-size:{font_size}pt;color:#18212f;'
        "margin:0;padding:0;}"
        "table{border-collapse:collapse;width:100%;}"
        ".page-header{margin-bottom:6px;border-bottom:1px solid #687386;}"
        ".page-header td{border:0;padding:2px 4px;vertical-align:middle;}"
        ".logo{width:12%;}.logo img{max-width:72px;max-height:34px;}"
        ".heading{width:58%;text-align:center;}.metadata{width:30%;text-align:right;"
        "font-size:7pt;color:#475467;}.document-title{font-size:15pt;font-weight:700;}"
        ".subheading{font-size:8pt;color:#475467;margin-top:2px;}"
        ".report-table{margin:0 0 7px 0;page-break-inside:avoid;}"
        ".report-table td{border:0.7px solid #596579;padding:3px;"
        "vertical-align:middle;white-space:normal;}"
        ".role-title{font-size:14pt;font-weight:700;}"
        ".role-subtitle{font-size:10pt;font-weight:700;background:#f2f5f9;}"
        ".role-header{font-weight:700;background:#e6edf7;text-align:center;}"
        ".role-metadata{font-weight:600;background:#f7f9fc;}"
        ".role-legend{font-size:6.5pt;background:#ffffff;}"
        ".role-closed{font-weight:700;}"
        ".page-footer{margin-top:5px;border-top:1px solid #687386;font-size:6.5pt;"
        "color:#475467;}.page-footer td{border:0;padding-top:3px;}"
        ".page-number{text-align:right;white-space:nowrap;}"
    )


def _logo_html(path_value: str | None) -> str:
    if not path_value:
        return ""
    path = Path(path_value).expanduser()
    suffix = path.suffix.casefold()
    mime = _LOGO_MIME_TYPES.get(suffix)
    if mime is None:
        raise HtmlRenderError("ロゴはPNG、JPEG、GIF、BMP形式を指定してください")
    try:
        size = path.stat().st_size
        if size > _MAX_LOGO_BYTES:
            raise HtmlRenderError("ロゴ画像は5MB以下にしてください")
        payload = path.read_bytes()
    except OSError as exc:
        raise HtmlRenderError("設定されたロゴ画像を読み込めません") from exc
    reader = QImageReader(str(path))
    reader.setDecideFormatFromContent(True)
    if not payload or not reader.canRead():
        raise HtmlRenderError("設定されたロゴ画像を画像として読み込めません")
    encoded = base64.b64encode(payload).decode("ascii")
    return f'<img alt="校舎ロゴ" src="data:{mime};base64,{encoded}">'


def _text(value: str) -> str:
    return html.escape(value, quote=True).replace("\n", "<br>")


__all__ = ["HtmlRenderError", "HtmlRenderer"]
