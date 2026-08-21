"""Phase 3 ViewModelとApplication Serviceの接続テスト。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook
from PySide6.QtCore import QUrl
from PySide6.QtTest import QSignalSpy

from summer_scheduler.application.availability_import_service import (
    AvailabilityImportService,
)
from summer_scheduler.application.group_lesson_service import GroupLessonService
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.application.project_validation_service import (
    ProjectValidationService,
)
from summer_scheduler.application.sample_project_service import SampleProjectService
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.ui.viewmodels.phase3_view_model import Phase3ViewModel


@pytest.fixture
def project_service(tmp_path: Path) -> Iterator[ProjectService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    service = ProjectService(registry, tmp_path / "バックアップ")
    yield service
    service.close_project()
    registry.dispose()


def test_availability_template_inspection_is_exposed_as_qml_primitives(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_service.create_project(
        tmp_path / "画面接続.jukuschedule",
        title="画面接続",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
    )
    view_model = _view_model(project_service)
    template = tmp_path / "日本語 生徒希望.xlsx"

    assert view_model.exportStudentTemplate(str(template))
    assert view_model.inspectAvailabilitySource(str(template), "auto")

    assert view_model._get_has_open_project() is True
    assert view_model._get_source_path() == str(template.resolve())
    assert "生徒ID（必須）" in view_model._get_source_headers()
    assert view_model._get_selected_sheet() == "生徒希望"
    assert any(row["canonicalKey"] == "slot:Y" for row in view_model._get_mapping_rows())
    assert view_model._get_source_preview_rows()

    assert view_model.validateAvailabilityImport()
    assert view_model._get_can_apply_import() is True
    assert view_model._get_import_summary()["errorCount"] == 0

    group_template = tmp_path / "日本語 集団授業.xlsx"
    assert view_model.exportGroupTemplate(str(group_template))
    assert view_model.inspectGroupSource(str(group_template))
    assert view_model._get_group_source_path() == str(group_template.resolve())
    assert view_model._get_source_path() == str(template.resolve())
    view_model.clearGroupImport()
    assert view_model._get_group_source_path() == ""
    assert view_model._get_source_path() == str(template.resolve())


def test_anonymous_sample_refreshes_group_and_validation_state(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    guard_calls = 0

    def guard() -> None:
        nonlocal guard_calls
        guard_calls += 1

    view_model = _view_model(project_service, before_project_change=guard)
    destination = tmp_path / "日本語 匿名サンプル.jukuschedule"

    assert view_model.createAnonymousSample(QUrl.fromLocalFile(str(destination)).toString())

    assert guard_calls == 1
    assert view_model._get_has_open_project() is True
    assert len(view_model._get_group_lessons()) == 1
    summary = view_model._get_validation_summary()
    assert summary["errorCount"] == 0
    warning_count = summary["warningCount"]
    assert isinstance(warning_count, int)
    assert warning_count >= 1
    assert summary["canOptimize"] is True


def test_anonymous_sample_respects_unsaved_draft_guard(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    def reject_switch() -> None:
        raise ProjectFileError("未保存の変更があります")

    view_model = _view_model(project_service, before_project_change=reject_switch)
    destination = tmp_path / "作成禁止.jukuschedule"

    assert not view_model.createAnonymousSample(str(destination))
    assert view_model._get_error_message() == "未保存の変更があります"
    assert not destination.exists()


def test_google_forms_script_export_is_exposed_to_qml(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_service.create_project(
        tmp_path / "フォーム作成.jukuschedule",
        title="2026年 夏期講習",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
    )
    view_model = _view_model(project_service)
    output = tmp_path / "フォーム出力"
    output.mkdir()
    signal_spy = QSignalSpy(view_model.questionnaireScriptsChanged)

    assert view_model.exportGoogleFormsScripts(
        QUrl.fromLocalFile(str(output)).toString(),
        "2026夏期講習 個別指導受講申込",
        "2026夏期講習 非常勤勤務アンケート",
        "2026年6月25日",
        "担当者へお問い合わせください",
    )

    destination = Path(view_model._get_last_questionnaire_script_directory())
    assert destination.parent == output.resolve()
    assert (destination / "create_student_questionnaire.gs").is_file()
    assert (destination / "create_teacher_questionnaire.gs").is_file()
    assert (destination / "create_teacher_subject_questionnaire.gs").is_file()
    assert (destination / "Googleフォーム作成手順.txt").is_file()
    assert signal_spy.count() == 1


def test_xlsx_sheet_selection_manual_mapping_and_apply_emit_state_changes(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    SampleProjectService(project_service).create_anonymous_sample(tmp_path / "画面用サンプル")
    view_model = _view_model(project_service)
    workbook_path = tmp_path / "複数シート_手動マッピング.xlsx"
    workbook = Workbook()
    ignored = workbook.active
    assert ignored is not None
    ignored.title = "先頭シート"
    ignored.append(["このシートは選択しない"])
    response = workbook.create_sheet("回答シート")
    headers = (
        "ID列",
        "氏名列",
        "科目列",
        "日付列",
        "Y列",
        "Z列",
        "A列",
        "B列",
        "C列",
        "希望1列",
    )
    response.append(headers)
    response.append(("S-001", "架空 青空", "JH_ENG", "2026-08-03", 1, 1, 1, 1, 1, "T-001"))
    workbook.save(workbook_path)
    workbook.close()

    assert view_model.inspectAvailabilitySource(str(workbook_path), "auto")
    assert view_model._get_selected_sheet() == "先頭シート"
    assert view_model.selectSourceSheet("回答シート")
    assert view_model._get_selected_sheet() == "回答シート"
    for canonical_key, source_header in zip(
        (
            "student_id",
            "student_name",
            "subject_code",
            "date",
            "slot:Y",
            "slot:Z",
            "slot:A",
            "slot:B",
            "slot:C",
            "preferred_teacher_1",
        ),
        headers,
        strict=True,
    ):
        view_model.setColumnMapping(canonical_key, source_header)

    assert view_model.validateAvailabilityImport()
    assert view_model._get_can_apply_import() is True
    availability_spy = QSignalSpy(view_model.availabilityStateChanged)
    assert view_model.applyAvailabilityImport(False)
    assert availability_spy.count() == 1
    assert view_model._get_can_apply_import() is False
    assert view_model._get_import_diffs() == []

    group_template = tmp_path / "signal_group.xlsx"
    assert view_model.exportGroupTemplate(str(group_template))
    assert view_model.inspectGroupSource(str(group_template))
    assert view_model.validateGroupImport()
    assert view_model._get_can_apply_group_import() is True
    group_spy = QSignalSpy(view_model.groupStateChanged)
    assert view_model.applyGroupImport(False)
    assert group_spy.count() == 1
    assert view_model._get_can_apply_group_import() is False
    assert view_model._get_group_import_diffs() == []


def test_unexpected_error_log_keeps_location_without_exception_value(
    project_service: ProjectService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    view_model = _view_model(project_service)
    sensitive_value = r"C:\利用者\個人情報\回答.xlsx 生徒氏名"

    def fail_unexpectedly() -> None:
        raise RuntimeError(sensitive_value)

    with caplog.at_level(logging.ERROR):
        assert not view_model._perform(fail_unexpectedly, "")

    assert view_model._get_error_message() == (
        "処理を完了できませんでした。ローカルログを確認してください"
    )
    assert "RuntimeError" in caplog.text
    assert "fail_unexpectedly" in caplog.text
    assert sensitive_value not in caplog.text


def _view_model(
    projects: ProjectService,
    *,
    before_project_change: Callable[[], None] | None = None,
) -> Phase3ViewModel:
    return Phase3ViewModel(
        projects,
        AvailabilityImportService(projects),
        GroupLessonService(projects),
        ProjectValidationService(projects),
        SampleProjectService(projects),
        before_project_change=before_project_change,
    )
