"""Qtのローカル描画機能だけを使うPDFレンダラー。"""

from __future__ import annotations

import gc
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QMarginsF, QRectF
from PySide6.QtGui import (
    QFont,
    QFontDatabase,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QTextDocument,
)
from PySide6.QtPdf import QPdfDocument

from summer_scheduler.infrastructure.exporting.atomic_output import atomic_output_path
from summer_scheduler.infrastructure.exporting.errors import (
    OutputDestinationExistsError,
    OutputRenderError,
)
from summer_scheduler.infrastructure.exporting.html_renderer import HtmlRenderer
from summer_scheduler.reporting.layout import LayoutDocument
from summer_scheduler.reporting.settings import OutputSettings


class PdfRenderError(OutputRenderError):
    """利用者へ明示するPDF生成・保存失敗。"""


class PdfOverwriteConfirmationRequired(OutputDestinationExistsError):
    """既存PDFを明示確認なしに上書きしようとした。"""


class QtPdfRenderer:
    """物理ページ分割済みレイアウトをA3/A4 PDFへ描く。"""

    def __init__(self, html_renderer: HtmlRenderer | None = None) -> None:
        self._html = html_renderer or HtmlRenderer()

    def render(
        self,
        document: LayoutDocument,
        settings: OutputSettings,
        target: Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        settings.validate()
        if document.page_count < 1:
            raise PdfRenderError("PDFへ出力するページがありません")
        target = target.expanduser().resolve()
        if target.suffix.casefold() != ".pdf":
            target = target.with_suffix(".pdf")
        if target.exists() and not overwrite:
            raise PdfOverwriteConfirmationRequired(f"同名のPDFが既にあります: {target.name}")
        try:
            with atomic_output_path(target, overwrite=overwrite) as temporary:
                self._render_temporary(document, settings, temporary)
                _validate_pdf(temporary, expected_pages=document.page_count)
        except OutputDestinationExistsError as exc:
            raise PdfOverwriteConfirmationRequired(str(exc)) from exc
        return target

    def _render_temporary(
        self,
        document: LayoutDocument,
        settings: OutputSettings,
        temporary: Path,
    ) -> None:
        writer = QPdfWriter(str(temporary))
        writer.setCreator("Summer Scheduler")
        writer.setTitle(document.title)
        writer.setResolution(144)
        if not writer.setPageLayout(_page_layout(document)):
            raise PdfRenderError("PDFの用紙サイズまたは余白を設定できません")
        painter = QPainter()
        if not painter.begin(writer):
            raise PdfRenderError("PDFの描画を開始できません")
        font_family = _japanese_font_family()
        page_number = 0
        try:
            for section in document.sections:
                for page in section.pages:
                    if page_number and not writer.newPage():
                        raise PdfRenderError("PDFの改ページに失敗しました")
                    page_number += 1
                    html = self._html.render_page(
                        document,
                        page,
                        settings,
                        page_number=page_number,
                        total_pages=document.page_count,
                        font_family=font_family,
                    )
                    _draw_html_page(
                        painter,
                        writer,
                        html,
                        font_family=font_family,
                        font_size=settings.font_size,
                    )
        finally:
            if painter.isActive() and not painter.end():
                raise PdfRenderError("PDFの描画終了処理に失敗しました")
        del writer


def _page_layout(document: LayoutDocument) -> QPageLayout:
    page_size_id = (
        QPageSize.PageSizeId.A3 if document.page_size == "A3" else QPageSize.PageSizeId.A4
    )
    orientation = (
        QPageLayout.Orientation.Landscape
        if document.orientation == "landscape"
        else QPageLayout.Orientation.Portrait
    )
    margins = QMarginsF(
        document.margin_mm,
        document.margin_mm,
        document.margin_mm,
        document.margin_mm,
    )
    return QPageLayout(
        QPageSize(page_size_id),
        orientation,
        margins,
        QPageLayout.Unit.Millimeter,
    )


def _draw_html_page(
    painter: QPainter,
    writer: QPdfWriter,
    html: str,
    *,
    font_family: str,
    font_size: float,
) -> None:
    paint_rect = writer.pageLayout().paintRectPixels(writer.resolution())
    document = QTextDocument()
    document.setDefaultFont(QFont(font_family, max(5, round(font_size))))
    document.setDocumentMargin(0)
    document.setHtml(html)
    document.setTextWidth(float(paint_rect.width()))
    content_size = document.documentLayout().documentSize()
    scale = min(
        1.0,
        paint_rect.width() / max(1.0, content_size.width()),
        paint_rect.height() / max(1.0, content_size.height()),
    )
    if scale < 0.62:
        raise PdfRenderError(
            "1ページの情報量が多すぎて読める大きさでPDF化できません。"
            "対象件数や1ページ当たりの項目数を減らすか、余白・文字サイズを調整してください"
        )
    painter.save()
    try:
        painter.translate(paint_rect.left(), paint_rect.top())
        painter.scale(scale, scale)
        document.drawContents(
            painter,
            QRectF(
                0,
                0,
                paint_rect.width() / scale,
                paint_rect.height() / scale,
            ),
        )
    finally:
        painter.restore()


def _japanese_font_family() -> str:
    available = set(QFontDatabase.families())
    for family in ("Yu Gothic UI", "Yu Gothic", "Meiryo UI", "Meiryo", "MS Gothic"):
        if family in available:
            return family
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


def _validate_pdf(path: Path, *, expected_pages: int) -> None:
    if not path.is_file() or path.stat().st_size < 512:
        raise PdfRenderError("生成したPDFが空または不完全です")
    document = QPdfDocument()
    try:
        error = document.load(str(path))
        if error != QPdfDocument.Error.None_:
            raise PdfRenderError("生成したPDFを検証できません")
        if document.pageCount() != expected_pages:
            raise PdfRenderError("生成したPDFのページ数がプレビュー用レイアウトと一致しません")
        for index in range(document.pageCount()):
            size = document.pagePointSize(index)
            if not size.isValid() or size.width() <= 0 or size.height() <= 0:
                raise PdfRenderError("生成したPDFに不正なページがあります")
    finally:
        document.close()
        del document
        QCoreApplication.processEvents()
        gc.collect()


__all__ = [
    "PdfOverwriteConfirmationRequired",
    "PdfRenderError",
    "QtPdfRenderer",
]
