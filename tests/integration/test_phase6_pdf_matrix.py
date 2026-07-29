"""Phase 6のQt PDF実体生成を帳票横断で検証する。"""

from __future__ import annotations

import base64
import json
import os
import pickle
import subprocess
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

from summer_scheduler.reporting.data import (
    AssignmentRecord,
    DateRecord,
    GroupLessonRecord,
    LessonRequestRecord,
    OutputSnapshot,
    ProjectRecord,
    SlotRecord,
    StudentRecord,
    SubjectRecord,
    TeacherRecord,
    UnassignedRecord,
    WarningRecord,
)
from summer_scheduler.reporting.issue_builder import build_issues_document
from summer_scheduler.reporting.layout import (
    LayoutCell,
    LayoutDocument,
    LayoutPage,
    LayoutRow,
    LayoutSection,
    LayoutTable,
)
from summer_scheduler.reporting.settings import OutputSettings
from summer_scheduler.reporting.student_builder import build_student_document
from summer_scheduler.reporting.teacher_builder import build_teacher_document
from summer_scheduler.reporting.timetable_builder import build_timetable_document

_PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
_LONG_STUDENT_NAME = "架空の非常に長い生徒氏名・表示折返し確認用・一番"
_LONG_TEACHER_NAME = "架空の非常に長い講師氏名・表示折返し確認用・担当"

_PDF_MATRIX_SCRIPT = r"""
import gc
import json
import pickle
import sys

from PySide6.QtCore import QCoreApplication, QSize
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtPdf import QPdfDocument

from summer_scheduler.infrastructure.exporting.pdf_renderer import QtPdfRenderer

app = QGuiApplication(["phase6-pdf-matrix", "-platform", "offscreen"])
documents, settings, output_directory, logo_path = pickle.loads(
    open(sys.argv[1], "rb").read()
)
renderer = QtPdfRenderer()
results = {}
for report_code, document in documents.items():
    target = output_directory / f"{report_code}.pdf"
    rendered = renderer.render(document, settings, target)
    reader = QPdfDocument()
    error = reader.load(str(rendered))
    page_count = reader.pageCount()
    page_sizes = [
        [reader.pagePointSize(index).width(), reader.pagePointSize(index).height()]
        for index in range(page_count)
    ]
    rendered_page = reader.render(0, QSize(256, 256))
    results[report_code] = {
        "error": int(error.value),
        "pages": page_count,
        "page_sizes": page_sizes,
        "first_page_raster_valid": not rendered_page.isNull(),
        "size_bytes": rendered.stat().st_size,
    }
    reader.close()
    del reader
    QCoreApplication.processEvents()
    gc.collect()
results["logo_is_valid_image"] = not QImage(str(logo_path)).isNull()
print(json.dumps(results, ensure_ascii=False))
"""

_PDF_DENSITY_SCRIPT = r"""
import json
import pickle
import sys

from PySide6.QtGui import QGuiApplication

from summer_scheduler.infrastructure.exporting.pdf_renderer import (
    PdfRenderError,
    QtPdfRenderer,
)

app = QGuiApplication(["phase6-pdf-density", "-platform", "offscreen"])
document, settings, target = pickle.loads(open(sys.argv[1], "rb").read())
message = ""
try:
    QtPdfRenderer().render(document, settings, target)
except PdfRenderError as exc:
    message = str(exc)
print(json.dumps({"message": message, "target_exists": target.exists()}, ensure_ascii=True))
"""


def test_qt_pdf_report_matrix_supports_a4_portrait_boundary_layout_and_logo(
    tmp_path: Path,
) -> None:
    """最大の有効余白・文字サイズでも、少量の各帳票は欠落なく出力できる。"""

    logo = _write_test_logo(tmp_path)
    snapshot = _small_snapshot(logo)
    settings = _settings(
        logo_path_optional=str(logo),
        font_size=18.0,
        margin_mm=30.0,
    )
    documents = {
        "students": build_student_document(snapshot, settings),
        "teachers": build_teacher_document(snapshot, settings),
        "issues": build_issues_document(snapshot, settings),
    }

    result = _render_matrix(tmp_path, documents, settings, logo)

    assert result["logo_is_valid_image"] is True
    for report_code, document in documents.items():
        report = result[report_code]
        assert report["error"] == 0
        assert report["pages"] == document.page_count
        assert report["size_bytes"] > 1_000
        assert report["first_page_raster_valid"] is True
        for width, height in report["page_sizes"]:
            assert width < height
            assert width == pytest.approx(595, abs=3)
            assert height == pytest.approx(842, abs=3)

    student_text = _without_whitespace(_document_text(documents["students"]))
    teacher_text = _without_whitespace(_document_text(documents["teachers"]))
    issue_text = _without_whitespace(_document_text(documents["issues"]))
    assert "架空の非常に長い生徒氏名" in student_text
    assert "架空の非常に長い講師氏名" in teacher_text
    assert "折返し表示を確認するための長い警告内容" in issue_text


def test_qt_pdf_large_student_and_group_reports_keep_physical_pagination(
    tmp_path: Path,
) -> None:
    """多数生徒と標準コマ外の集団授業を、過密な1ページへ押し込まない。"""

    logo = _write_test_logo(tmp_path)
    snapshot = _large_anonymous_snapshot(logo)
    settings = _settings(
        logo_path_optional=str(logo),
        font_size=7.0,
        margin_mm=8.0,
        days_per_page=2,
        teacher_columns_per_page=2,
    )
    students = build_student_document(snapshot, settings)
    overall = build_timetable_document(snapshot, settings)

    assert students.page_count == 32
    assert overall.page_count == 7
    assert overall.sections[-1].name == "補足の集団授業"
    assert len(overall.sections[-1].pages) == 3

    result = _render_matrix(
        tmp_path,
        {"large_students": students, "large_groups": overall},
        settings,
        logo,
        timeout=120,
    )

    for report_code, document in (
        ("large_students", students),
        ("large_groups", overall),
    ):
        report = result[report_code]
        assert report["error"] == 0
        assert report["pages"] == document.page_count
        assert report["size_bytes"] > 10_000
        assert report["first_page_raster_valid"] is True
        assert all(width < height for width, height in report["page_sizes"])

    student_text = _without_whitespace(_document_text(students))
    group_text = _without_whitespace(_document_text(overall))
    assert "架空生徒001" in student_text
    assert "架空生徒030" in student_text
    assert "架空集団講座055" in group_text


def test_pdf_density_error_guides_every_report_type(tmp_path: Path) -> None:
    """過密時の案内を特定帳票の列設定だけに限定しない。"""

    settings = _settings(
        logo_path_optional="",
        font_size=18.0,
        margin_mm=30.0,
    )
    payload_path = tmp_path / "pdf-density-input.pickle"
    target = tmp_path / "over-density.pdf"
    payload_path.write_bytes(pickle.dumps((_overdense_document(settings), settings, target)))
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-c", _PDF_DENSITY_SCRIPT, str(payload_path)],
        cwd=Path(__file__).parents[2],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert "対象件数や1ページ当たりの項目数" in result["message"]
    assert "余白・文字サイズ" in result["message"]
    assert "日数または講師列数" not in result["message"]
    assert result["target_exists"] is False


def _render_matrix(
    tmp_path: Path,
    documents: dict[str, LayoutDocument],
    settings: OutputSettings,
    logo: Path,
    *,
    timeout: int = 60,
) -> dict[str, Any]:
    output_directory = tmp_path / "日本語PDF出力"
    payload_path = tmp_path / "pdf-matrix-input.pickle"
    payload_path.write_bytes(pickle.dumps((documents, settings, output_directory, logo)))
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-c", _PDF_MATRIX_SCRIPT, str(payload_path)],
        cwd=Path(__file__).parents[2],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )

    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]


def _write_test_logo(directory: Path) -> Path:
    path = directory / "架空校舎ロゴ.png"
    path.write_bytes(base64.b64decode(_PNG_1X1))
    return path


def _settings(
    *,
    logo_path_optional: str,
    font_size: float,
    margin_mm: float,
    days_per_page: int = 1,
    teacher_columns_per_page: int = 1,
) -> OutputSettings:
    settings = OutputSettings(
        project_id=1,
        paper_size="A4",
        orientation="portrait",
        logo_path_optional=logo_path_optional,
        days_per_page=days_per_page,
        teacher_columns_per_page=teacher_columns_per_page,
        font_size=font_size,
        margin_mm=margin_mm,
    )
    settings.validate()
    return settings


def _small_snapshot(logo: Path) -> OutputSnapshot:
    return OutputSnapshot(
        project=ProjectRecord(
            id=1,
            title="2026年度 架空夏期講習・長文レイアウト確認",
            campus_name="架空みらい校舎・日本語帳票確認用",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            status="confirmed",
            generated_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
            logo_path_optional=str(logo),
        ),
        dates=(DateRecord(date(2026, 8, 1), True, "架空の開校日"),),
        slots=(
            SlotRecord(
                1,
                "Y",
                "午前Yコマ",
                time(9),
                time(10, 20),
                1,
                True,
            ),
        ),
        students=(
            StudentRecord(
                1,
                "S-TEST-001",
                _LONG_STUDENT_NAME,
                "中学1年",
                "架空データ",
                True,
            ),
        ),
        teachers=(
            TeacherRecord(
                1,
                "T-TEST-001",
                _LONG_TEACHER_NAME,
                "架空データ",
                True,
            ),
        ),
        subjects=(SubjectRecord(1, "MATH", "数学・思考力演習", "中学"),),
        lesson_requests=(
            LessonRequestRecord(
                1,
                1,
                1,
                2,
                1,
                5,
                True,
                "長い備考もセル内で折り返して判読できることを確認",
            ),
        ),
        assignments=(
            AssignmentRecord(
                1,
                1,
                1,
                date(2026, 8, 1),
                1,
                1,
                True,
                False,
                "架空の配置済み授業",
            ),
        ),
        group_lessons=(),
        unassigned=(
            UnassignedRecord(
                lesson_request_id=1,
                student_id=1,
                subject_id=1,
                required_sessions=2,
                placed_sessions=1,
                missing_sessions=1,
                main_reason="架空の候補枠不足・長文表示確認",
                reason_codes=("test_capacity",),
                resolution_candidates=("2026/08/01 Y 架空代替講師",),
                candidate_count=1,
                priority=5,
                regular_teacher_id_optional=1,
                one_to_one_required=True,
                note="個人情報を含まない架空データ",
            ),
        ),
        warnings=(
            WarningRecord(
                severity="warning",
                issue_type="layout_test",
                day_optional=date(2026, 8, 1),
                slot_code="Y",
                student_name=_LONG_STUDENT_NAME,
                teacher_name=_LONG_TEACHER_NAME,
                content="折返し表示を確認するための長い警告内容・架空データ",
                status="未対応",
                student_ids=(1,),
                teacher_id_optional=1,
            ),
        ),
    )


def _large_anonymous_snapshot(logo: Path) -> OutputSnapshot:
    first_day = date(2026, 8, 1)
    dates = tuple(DateRecord(first_day + timedelta(days=index), True, "") for index in range(4))
    slots = (
        SlotRecord(1, "Y", "Yコマ", time(9), time(10), 1, True),
        SlotRecord(2, "Z", "Zコマ", time(10, 15), time(11, 15), 2, True),
        SlotRecord(3, "A", "Aコマ", time(13), time(14), 3, True),
    )
    students = tuple(
        StudentRecord(
            index,
            f"S-TEST-{index:03d}",
            f"架空生徒{index:03d}",
            f"中学{(index - 1) % 3 + 1}年",
            "",
            True,
        )
        for index in range(1, 31)
    )
    teachers = tuple(
        TeacherRecord(
            index,
            f"T-TEST-{index:03d}",
            f"架空講師{index:03d}",
            "",
            True,
        )
        for index in range(1, 5)
    )
    requests = tuple(
        LessonRequestRecord(
            index,
            index,
            1,
            1,
            (index - 1) % len(teachers) + 1,
            3,
            False,
            "",
        )
        for index in range(1, 31)
    )
    assignments = tuple(
        AssignmentRecord(
            index,
            index,
            1,
            dates[(index - 1) % len(dates)].day,
            slots[(index - 1) % len(slots)].id,
            (index - 1) % len(teachers) + 1,
            False,
            False,
            "",
        )
        for index in range(1, 31)
    )
    group_lessons = tuple(
        GroupLessonRecord(
            id=index,
            group_code=f"G-TEST-{index:03d}",
            course_name=f"架空集団講座{index:03d}",
            grade="中学1年",
            subject_id=1,
            day=dates[(index - 1) % len(dates)].day,
            start_time=time(18),
            end_time=time(19),
            teacher_id_optional=1,
            student_ids=(1, (index - 1) % 29 + 2),
            room="架空教室",
            note="",
        )
        for index in range(1, 56)
    )
    return OutputSnapshot(
        project=ProjectRecord(
            id=1,
            title="2026年度 架空大規模夏期講習",
            campus_name="架空大規模校舎",
            start_date=dates[0].day,
            end_date=dates[-1].day,
            status="confirmed",
            generated_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
            logo_path_optional=str(logo),
        ),
        dates=dates,
        slots=slots,
        students=students,
        teachers=teachers,
        subjects=(SubjectRecord(1, "MATH", "数学", "中学"),),
        lesson_requests=requests,
        assignments=assignments,
        group_lessons=group_lessons,
        unassigned=(),
        warnings=(),
    )


def _overdense_document(settings: OutputSettings) -> LayoutDocument:
    table = LayoutTable(
        rows=(
            LayoutRow(cells=(LayoutCell("内容", role="header", alignment="center"),)),
            *(
                LayoutRow(
                    cells=(
                        LayoutCell(
                            f"架空の過密確認行{index:03d} "
                            "どの帳票にも共通する情報量エラーを確認します"
                        ),
                    )
                )
                for index in range(1, 201)
            ),
        ),
        column_widths=(100,),
        repeat_header_rows=1,
    )
    return LayoutDocument(
        report_code="density_test",
        title="過密確認帳票",
        campus_name="架空校舎",
        course_name="架空講習",
        updated_text="2026/07/29 12:00",
        sections=(
            LayoutSection(
                name="過密確認",
                pages=(
                    LayoutPage(
                        heading="過密確認",
                        subheading="安全な失敗を確認",
                        tables=(table,),
                    ),
                ),
            ),
        ),
        page_size=settings.paper_size,
        orientation=settings.orientation,
        margin_mm=settings.margin_mm,
        font_size=settings.font_size,
    )


def _document_text(document: LayoutDocument) -> str:
    return "\n".join(
        (
            document.title,
            document.campus_name,
            document.course_name,
            *(
                value
                for section in document.sections
                for page in section.pages
                for value in (
                    page.heading,
                    page.subheading,
                    page.footer_note,
                    *(
                        cell.text
                        for table in page.tables
                        for row in table.rows
                        for cell in row.cells
                    ),
                )
            ),
        )
    )


def _without_whitespace(value: str) -> str:
    return "".join(value.split())
