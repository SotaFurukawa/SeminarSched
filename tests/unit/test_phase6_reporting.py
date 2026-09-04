"""Phase 6共通レイアウト・HTML・Qt PDFの回帰テスト。"""

from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from summer_scheduler.infrastructure.exporting.html_renderer import (
    HtmlRenderer,
    HtmlRenderError,
)
from summer_scheduler.reporting.data import (
    AssignmentRecord,
    DateRecord,
    GroupLessonRecord,
    LessonRequestRecord,
    OutputSelection,
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
from summer_scheduler.reporting.settings import (
    OutputSettings,
    OutputSettingsValidationError,
    StyleRule,
)
from summer_scheduler.reporting.student_builder import build_student_document
from summer_scheduler.reporting.teacher_builder import build_teacher_document
from summer_scheduler.reporting.timetable_builder import build_timetable_document


def test_overall_layout_paginates_dates_teachers_and_preserves_semantics() -> None:
    snapshot = _snapshot()
    settings = _settings()

    document = build_timetable_document(snapshot, settings)

    assert document.page_count == 5
    assert len(document.sections) == 3
    texts = _document_texts(document)
    assert "とても長い架空の生徒名一号" in texts
    assert "[1対1]" in texts
    assert "[固定]" in texts
    assert "[手]" in texts
    assert "[集団]" in texts
    assert "13:00–14:20" in texts
    assert "[休校]" in texts
    assert "特記事項: 持参物確認" in texts
    assert document.sections[-1].name == "補足の集団授業"
    first_table = document.sections[0].pages[0].tables[0]
    assert first_table.repeat_header_rows == 1
    assert any(cell.row_span == 3 for row in first_table.rows for cell in row.cells)


def test_student_teacher_and_issue_reports_cover_required_fields() -> None:
    snapshot = _snapshot()
    one_per_page = build_student_document(snapshot, _settings())
    combined = build_student_document(
        snapshot,
        _settings(student_page_mode="combined"),
    )
    teacher = build_teacher_document(snapshot, _settings())
    issues = build_issues_document(snapshot, _settings())

    assert one_per_page.page_count == 3
    assert combined.page_count == 2
    assert "未配置残数: 1" in _document_texts(one_per_page)
    assert "1対2" in _document_texts(one_per_page)
    assert "個別備考／手動" in _document_texts(one_per_page)
    assert teacher.page_count == 6
    assert "合計稼働コマ数" in _document_texts(teacher)
    assert "Y–Z" in _document_texts(teacher)
    assert "13:00–14:20" in _document_texts(teacher)
    issue_text = _document_texts(issues)
    assert "主な理由" in issue_text
    assert "解決候補" in issue_text
    assert "対応状況" in issue_text
    assert "未対応" in issue_text


def test_timetable_uses_family_name_unless_the_family_name_is_duplicated() -> None:
    snapshot = _snapshot()
    renamed = replace(
        snapshot,
        students=(
            replace(snapshot.students[0], name="山田 太郎"),
            replace(snapshot.students[1], name="山田 花子"),
            replace(snapshot.students[2], name="佐藤 次郎"),
        ),
        teachers=(
            replace(snapshot.teachers[0], name="鈴木 一郎"),
            replace(snapshot.teachers[1], name="鈴木 花子"),
            replace(snapshot.teachers[2], name="高橋 次郎"),
        ),
    )

    overall_text = _document_texts(build_timetable_document(renamed, _settings()))
    teacher_text = _document_texts(build_teacher_document(renamed, _settings()))
    student_text = _document_texts(build_student_document(renamed, _settings()))

    assert "山田 太郎" in overall_text
    assert "山田 花子" in overall_text
    assert "佐藤" in overall_text
    assert "佐藤 次郎" not in overall_text
    assert "鈴木 一郎" in overall_text
    assert "鈴木 花子" in overall_text
    assert "高橋" in overall_text
    assert "高橋 次郎" not in overall_text
    assert "山田 太郎" in teacher_text
    assert "佐藤" in teacher_text
    assert "鈴木 一郎" in student_text


def test_output_selection_filters_dates_teachers_and_students() -> None:
    snapshot = _snapshot()
    selection = OutputSelection(
        dates=(date(2026, 8, 1),),
        teacher_ids=(1,),
        student_ids=(1,),
    )

    overall = build_timetable_document(snapshot, _settings(), selection)
    student = build_student_document(snapshot, _settings(), selection)
    teacher = build_teacher_document(snapshot, _settings(), selection)
    issues = build_issues_document(
        snapshot,
        _settings(),
        OutputSelection(teacher_ids=(2,)),
    )

    assert overall.page_count == 1
    assert "架空講師一" in _document_texts(overall)
    assert "架空講師二" not in _document_texts(overall)
    assert "架空生徒二" not in _document_texts(overall)
    assert "架空生徒三" not in _document_texts(overall)
    assert "とても長い架空の生徒名一号" in _document_texts(student)
    assert "架空生徒二" not in _document_texts(student)
    assert "2026/08/02" not in _document_texts(teacher)
    assert "他の授業との全体的な競合" not in _document_texts(issues)
    assert "手動変更を確認してください" not in _document_texts(issues)


def test_visible_fields_control_optional_content_without_losing_warning_or_note() -> None:
    document = build_timetable_document(
        _snapshot(),
        _settings(visible_fields=("note", "warning")),
    )

    text = _document_texts(document)
    assert "備考: 個別備考／手動" in text
    assert "[警告] 手動変更を確認してください" in text
    assert "[1対1]" not in text
    assert "[固定]" not in text
    assert "[手]" not in text
    assert "[集団]" not in text
    assert "中学1年" not in text
    assert "数学" not in text


def test_arbitrary_time_groups_are_never_lost_and_supplements_are_paginated() -> None:
    base = _snapshot().group_lessons[0]
    outside_groups = tuple(
        replace(
            base,
            id=100 + index,
            group_code=f"OUT-{index:02d}",
            course_name=f"標準コマ外講座{index:02d}",
            start_time=time(12),
            end_time=time(12, 30),
            teacher_id_optional=1,
        )
        for index in range(25)
    )
    snapshot = replace(_snapshot(), group_lessons=outside_groups)

    overall = build_timetable_document(snapshot, _settings())
    teacher = build_teacher_document(snapshot, _settings())

    assert overall.sections[-1].name == "補足の集団授業"
    assert len(overall.sections[-1].pages) == 2
    assert teacher.sections[-1].name == "標準コマ外の集団授業"
    assert len(teacher.sections[-1].pages) == 2
    overall_supplement = "\n".join(
        cell.text
        for page in overall.sections[-1].pages
        for table in page.tables
        for row in table.rows
        for cell in row.cells
    )
    teacher_supplement = "\n".join(
        cell.text
        for page in teacher.sections[-1].pages
        for table in page.tables
        for row in table.rows
        for cell in row.cells
    )
    matrix_text = "\n".join(
        cell.text
        for section in overall.sections[:-1]
        for page in section.pages
        for table in page.tables
        for row in table.rows
        for cell in row.cells
    )
    assert "OUT-00" not in matrix_text
    for index in range(25):
        assert overall_supplement.count(f"OUT-{index:02d}") == 1
        assert teacher_supplement.count(f"OUT-{index:02d}") == 1
    assert "12:00–12:30" in overall_supplement
    assert "12:00–12:30" in teacher_supplement
    assert "標準コマ外" in overall_supplement


def test_long_student_schedule_is_split_without_dropping_rows() -> None:
    snapshot = _snapshot()
    base = snapshot.assignments[0]
    assignments = tuple(
        replace(
            base,
            id=1_000 + index,
            session_index=index,
            note=f"匿名授業-{index:03d}",
        )
        for index in range(1, 82)
    )
    large = replace(snapshot, assignments=assignments, group_lessons=(), warnings=())
    selection = OutputSelection(student_ids=(1,))

    one_per_page = build_student_document(large, _settings(), selection)
    combined = build_student_document(
        large,
        _settings(student_page_mode="combined"),
        selection,
    )

    assert one_per_page.page_count == 5
    assert combined.page_count == 5
    assert all(
        len(table.rows) <= 22
        for section in one_per_page.sections
        for page in section.pages
        for table in page.tables
    )
    assert all(
        len(table.rows) <= 11
        for section in combined.sections
        for page in section.pages
        for table in page.tables
    )
    one_per_text = _document_texts(one_per_page)
    combined_text = _document_texts(combined)
    for index in range(1, 82):
        marker = f"匿名授業-{index:03d}"
        assert one_per_text.count(marker) == 1
        assert combined_text.count(marker) == 1


def test_issue_selection_uses_warning_relation_ids_for_multi_student_groups() -> None:
    snapshot = replace(
        _snapshot(),
        warnings=(
            WarningRecord(
                "warning",
                "group_conflict",
                date(2026, 8, 1),
                "A",
                "とても長い架空の生徒名一号、架空生徒二",
                "架空講師二",
                "集団授業の参加者を確認してください",
                "未対応",
                student_ids=(1, 2),
                teacher_id_optional=2,
            ),
        ),
    )

    issues = build_issues_document(
        snapshot,
        _settings(),
        OutputSelection(student_ids=(2,), teacher_ids=(2,)),
    )

    assert "集団授業の参加者を確認してください" in _document_texts(issues)


def test_settings_reject_invalid_filename_color_and_page_values() -> None:
    with pytest.raises(OutputSettingsValidationError, match="講師列数"):
        _settings(teacher_columns_per_page=0).validate()
    with pytest.raises(OutputSettingsValidationError, match="ファイル名規則"):
        _settings(file_name_pattern="../{report}").validate()
    bad_rules = (
        StyleRule("one_to_one", "1対1", "[1対1]", "yellow"),
        *_settings().style_rules[1:],
    )
    with pytest.raises(OutputSettingsValidationError, match="#RRGGBB"):
        _settings(style_rules=bad_rules).validate()


def test_html_escapes_user_text_and_embeds_color_plus_marker() -> None:
    snapshot = replace(
        _snapshot(campus_name="<校舎&本部>"),
        warnings=(),
    )
    settings = _settings()
    document = build_timetable_document(snapshot, settings)
    page = document.sections[0].pages[0]

    html = HtmlRenderer().render_page(
        document,
        page,
        settings,
        page_number=1,
        total_pages=document.page_count,
        font_family="Meiryo",
    )

    assert "&lt;校舎&amp;本部&gt;" in html
    assert "<校舎&本部>" not in html
    assert "[1対1]" in html
    assert settings.style("one_to_one").fill_color in html
    assert "ページ 1 / 5" in html


def test_html_reports_missing_local_logo_as_user_facing_output_error(
    tmp_path: Path,
) -> None:
    settings = _settings()
    document = replace(
        build_timetable_document(_snapshot(), settings),
        logo_path_optional=str(tmp_path / "存在しないロゴ.png"),
    )

    with pytest.raises(HtmlRenderError, match="ロゴ画像を読み込めません"):
        HtmlRenderer().render_page(
            document,
            document.sections[0].pages[0],
            settings,
            page_number=1,
            total_pages=document.page_count,
            font_family="Meiryo",
        )


def test_html_rejects_corrupt_logo_without_silently_omitting_it(tmp_path: Path) -> None:
    logo = tmp_path / "壊れた匿名ロゴ.png"
    logo.write_bytes(b"not a png image")
    settings = _settings()
    document = replace(
        build_timetable_document(_snapshot(), settings),
        logo_path_optional=str(logo),
    )

    with pytest.raises(HtmlRenderError, match="画像として読み込めません"):
        HtmlRenderer().render_page(
            document,
            document.sections[0].pages[0],
            settings,
            page_number=1,
            total_pages=document.page_count,
            font_family="Meiryo",
        )


def test_qt_pdf_generates_a3_landscape_multiple_pages_on_japanese_path(
    tmp_path: Path,
) -> None:
    target = tmp_path / "日本語出力先" / "季節講習時間割.pdf"
    document = build_timetable_document(_snapshot(), _settings())
    payload_path = tmp_path / "pdf-input.pickle"
    payload_path.write_bytes(pickle.dumps((document, _settings(), target)))
    script = r"""
import json
import pickle
import sys
from PySide6.QtGui import QGuiApplication
from PySide6.QtPdf import QPdfDocument
from summer_scheduler.infrastructure.exporting.pdf_renderer import (
    PdfOverwriteConfirmationRequired,
    QtPdfRenderer,
)

app = QGuiApplication(["phase6-pdf-test", "-platform", "offscreen"])
document, settings, target = pickle.loads(open(sys.argv[1], "rb").read())
renderer = QtPdfRenderer()
result = renderer.render(document, settings, target)
overwrite_blocked = False
try:
    renderer.render(document, settings, target)
except PdfOverwriteConfirmationRequired:
    overwrite_blocked = True
renderer.render(document, settings, target, overwrite=True)
reader = QPdfDocument()
error = reader.load(str(target))
size = reader.pagePointSize(0)
print(json.dumps({
    "path": str(result),
    "error": int(error.value),
    "pages": reader.pageCount(),
    "width": size.width(),
    "height": size.height(),
    "overwrite_blocked": overwrite_blocked,
}))
reader.close()
"""
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-c", script, str(payload_path)],
        cwd=Path(__file__).parents[2],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert Path(result["path"]) == target.resolve()
    assert target.stat().st_size > 1_000
    assert result["error"] == 0
    assert result["pages"] == document.page_count
    assert result["width"] > result["height"]
    assert result["width"] == pytest.approx(1191, abs=3)
    assert result["height"] == pytest.approx(842, abs=3)
    assert result["overwrite_blocked"] is True


def _settings(**changes: object) -> OutputSettings:
    values: dict[str, object] = {
        field: getattr(OutputSettings(project_id=1), field)
        for field in OutputSettings.__dataclass_fields__
    }
    values.update(
        {
            "project_id": 1,
            "days_per_page": 2,
            "teacher_columns_per_page": 2,
            "font_size": 7.0,
        }
    )
    values.update(changes)
    return OutputSettings(**values)  # type: ignore[arg-type]


def _snapshot(*, campus_name: str = "架空みらい校") -> OutputSnapshot:
    students = (
        StudentRecord(1, "S001", "とても長い架空の生徒名一号", "中学1年", "", True),
        StudentRecord(2, "S002", "架空生徒二", "中学2年", "", True),
        StudentRecord(3, "S003", "架空生徒三", "高校1年", "", True),
    )
    teachers = (
        TeacherRecord(1, "T001", "架空講師一", "", True),
        TeacherRecord(2, "T002", "架空講師二", "", True),
        TeacherRecord(3, "T003", "架空講師三", "", True),
    )
    subjects = (
        SubjectRecord(1, "MATH", "数学", "中学"),
        SubjectRecord(2, "ENG", "英語", "中学"),
    )
    requests = (
        LessonRequestRecord(1, 1, 1, 1, 1, 5, True, "個別備考"),
        LessonRequestRecord(2, 2, 1, 2, 1, 3, False, "未配置あり"),
        LessonRequestRecord(3, 3, 2, 1, 1, 2, False, ""),
    )
    assignments = (
        AssignmentRecord(1, 1, 1, date(2026, 8, 1), 1, 1, True, True, "手動"),
        AssignmentRecord(2, 2, 1, date(2026, 8, 1), 2, 1, False, False, ""),
        AssignmentRecord(3, 3, 1, date(2026, 8, 1), 2, 1, False, False, ""),
    )
    return OutputSnapshot(
        project=ProjectRecord(
            id=1,
            title="2026年度 夏期講習",
            campus_name=campus_name,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 3),
            status="draft",
            generated_at=datetime(2026, 7, 29, 12, 34, tzinfo=UTC),
        ),
        dates=(
            DateRecord(date(2026, 8, 1), True, "持参物確認"),
            DateRecord(date(2026, 8, 2), True, ""),
            DateRecord(date(2026, 8, 3), False, "設備点検"),
        ),
        slots=(
            SlotRecord(1, "Y", "Yコマ", time(9), time(10, 20), 1, True),
            SlotRecord(2, "Z", "Zコマ", time(10, 30), time(11, 50), 2, True),
            SlotRecord(3, "A", "Aコマ", time(13), time(14, 20), 3, True),
        ),
        students=students,
        teachers=teachers,
        subjects=subjects,
        lesson_requests=requests,
        assignments=assignments,
        group_lessons=(
            GroupLessonRecord(
                1,
                "G001",
                "中1英語特講",
                "中学1年",
                2,
                date(2026, 8, 1),
                time(13),
                time(14, 20),
                2,
                (1,),
                "第1教室",
                "持ち物あり",
            ),
            GroupLessonRecord(
                2,
                "G002",
                "担当未設定講座",
                "高校1年",
                2,
                date(2026, 8, 2),
                time(13),
                time(14, 20),
                None,
                (3,),
                "",
                "",
            ),
        ),
        unassigned=(
            UnassignedRecord(
                2,
                2,
                1,
                2,
                1,
                1,
                "他の授業との全体的な競合により未配置です",
                ("global_competition",),
                ("2026/08/02 A 架空講師二（候補）",),
                1,
                3,
                1,
                False,
                "未配置あり",
            ),
        ),
        warnings=(
            WarningRecord(
                "warning",
                "assignment_review",
                date(2026, 8, 1),
                "Y",
                students[0].name,
                teachers[0].name,
                "手動変更を確認してください",
                "未対応",
            ),
        ),
    )


def _document_texts(document: object) -> str:
    return "\n".join(
        cell.text
        for section in document.sections  # type: ignore[attr-defined]
        for page in section.pages
        for table in page.tables
        for row in table.rows
        for cell in row.cells
    )
