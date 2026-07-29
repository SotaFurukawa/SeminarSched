"""Phase 6出力QML・ViewModel・アプリ配線の契約テスト。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
QML = ROOT / "src" / "summer_scheduler" / "ui" / "qml" / "OutputPage.qml"
MAIN = ROOT / "src" / "summer_scheduler" / "ui" / "qml" / "Main.qml"
VIEW_MODEL = ROOT / "src" / "summer_scheduler" / "ui" / "viewmodels" / "output_view_model.py"
APP = ROOT / "src" / "summer_scheduler" / "app.py"


def test_output_page_exposes_formats_destination_and_overwrite_confirmation() -> None:
    source = QML.read_text(encoding="utf-8")

    assert "root.viewModel.reportOptions" in source
    assert "root.viewModel.formatOptions" in source
    assert "Dialogs.FileDialog {" in source
    assert "root.viewModel.destinationPath" in source
    assert "generateOutput(false)" in source
    assert "generateOutput(true)" in source
    assert "onOverwriteConfirmationRequested" in source
    assert "Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No" in source


def test_output_page_exposes_all_phase6_settings_and_target_filters() -> None:
    source = QML.read_text(encoding="utf-8")

    for property_name in (
        "paperSize",
        "orientation",
        "daysPerPage",
        "teacherColumnsPerPage",
        "fontSize",
        "marginMm",
        "studentPageMode",
        "csvWithBom",
        "fileNamePattern",
        "logoPath",
        "defaultOutputDirectory",
        "visibleFieldOptions",
        "styleRules",
        "dateOptions",
        "teacherOptions",
        "studentOptions",
    ):
        assert f"root.viewModel.{property_name}" in source
    assert "setLogoPath(" in source
    assert "setVisibleField(" in source
    assert "setDefaultOutputDirectory(" in source
    assert "setStyleRule(" in source
    assert "色だけに依存せず" in source


def test_qtquick_pdf_preview_has_navigation_zoom_and_cleanup_contract() -> None:
    qml = QML.read_text(encoding="utf-8")
    python = VIEW_MODEL.read_text(encoding="utf-8")

    assert "import QtQuick.Pdf" in qml
    assert "PdfDocument {" in qml
    assert "PdfMultiPageView {" in qml
    assert "goToPage(" in qml
    assert "renderScale" in qml
    assert "scaleToWidth(" in qml
    assert "scaleToPage(" in qml
    assert "clearPreview()" in qml
    assert "TemporaryDirectory" in python
    assert "_cleanup_preview_directory" in python
    assert "clearPreview()" in python


def test_worker_is_async_and_preview_is_invalidated_by_draft_changes() -> None:
    source = VIEW_MODEL.read_text(encoding="utf-8")

    assert "class _OutputWorker(QObject):" in source
    assert "class _WorkspaceWorker(QObject):" in source
    assert "moveToThread(thread)" in source
    assert "Qt.ConnectionType.DirectConnection" in source
    assert "thread.wait(30_000)" in source
    assert ".terminate(" not in source
    replace_settings = source.split("def _replace_settings", maxsplit=1)[1].split(
        "def _set_selected",
        maxsplit=1,
    )[0]
    assert "self.clearPreview()" in replace_settings


def test_main_uses_output_page_and_composes_project_switch_guards() -> None:
    main = MAIN.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    assert "readonly property var output: outputViewModel" in main
    assert "root.currentPageIndex === 7" in main
    assert "OutputPage {" in main
    assert "OutputViewModel(" in app
    assert "OutputService(" in app
    assert "output_defaults=runtime.settings.output" in app
    assert '"outputViewModel"' in app
    guard = app.split("def ensure_project_switch_allowed()", maxsplit=1)[1].split(
        "workspace_view_model.set_project_change_guard",
        maxsplit=1,
    )[0]
    assert "optimization_view_model.ensure_project_switch_allowed()" in guard
    assert "output_view_model.ensure_project_switch_allowed()" in guard
    assert "application.aboutToQuit.connect(output_view_model.shutdown)" in app
