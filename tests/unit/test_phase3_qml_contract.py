"""Phase 3画面とQML/ViewModel境界の契約テスト。"""

from __future__ import annotations

from pathlib import Path

QML_DIRECTORY = Path(__file__).parents[2] / "src" / "summer_scheduler" / "ui" / "qml"


def _qml_source(name: str) -> str:
    return (QML_DIRECTORY / name).read_text(encoding="utf-8")


def test_main_connects_phase3_navigation_to_real_pages() -> None:
    source = _qml_source("Main.qml")

    assert "readonly property var phase3: phase3ViewModel" in source
    assert "GroupLessonPage {" not in source
    assert "AvailabilityImportPage {" in source
    assert "ValidationIssuesPage {" in source
    assert "? availabilityImportComponent" in source
    assert "? validationIssuesComponent" in source


def test_availability_import_page_exposes_complete_safe_workflow() -> None:
    source = _qml_source("AvailabilityImportPage.qml")

    required_calls = {
        "setCombinedStudentSource(",
        "setCombinedTeacherSource(",
        "validateCombinedSurvey()",
        "setCombinedStudentTrialResolution(",
        "applyCombinedSurvey()",
        "exportCombinedSurvey(",
    }
    assert all(call in source for call in required_calls)
    assert "生徒・講師回答をまとめて取り込む" in source
    assert "2ファイルを検証" in source
    assert "カンマ区切り形式（csv）" in source
    assert "enabled: root.viewModel.canApplyCombinedSurvey" in source
    assert "Dialogs.MessageDialog" in source


def test_group_import_requires_validation_and_explicit_delete_confirmation() -> None:
    source = _qml_source("GroupLessonPage.qml")

    required_calls = {
        "inspectGroupSource(",
        "validateGroupImport()",
        "applyGroupImport(groupIncludeDeletes.checked)",
        "clearGroupImport()",
        "exportGroupTemplate(",
    }
    assert all(call in source for call in required_calls)
    assert "root.viewModel.groupSourcePath" in source
    assert "root.viewModel.sourcePath" not in source
    assert "enabled: root.viewModel.canApplyGroupImport" in source
    assert "削除候補も反映" in source
    assert "groupApplyConfirmation.open()" in source
    assert "区間重複" in source


def test_validation_page_stops_at_phase3_input_validation() -> None:
    source = _qml_source("ValidationIssuesPage.qml")

    assert "runProjectValidation()" in source
    assert "refreshPhase3()" in source
    assert "createAnonymousSample(" in source
    assert "Phase 3で扱う入力範囲にエラーはありません" in source
    assert "エラーを解消するまで最適化を開始できません" in source
    assert "Assignment依存の検証、OR-Tools実行、未配置理由はPhase 4で扱います" in source
    assert "startOptimization" not in source
    assert "runOptimization" not in source
