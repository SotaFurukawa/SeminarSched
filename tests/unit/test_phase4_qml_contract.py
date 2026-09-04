"""Phase 4簡易最適化画面のQML/ViewModel契約。"""

from __future__ import annotations

from pathlib import Path

QML_DIRECTORY = Path(__file__).parents[2] / "src" / "summer_scheduler" / "ui" / "qml"
VIEW_MODEL = (
    Path(__file__).parents[2]
    / "src"
    / "summer_scheduler"
    / "ui"
    / "viewmodels"
    / "optimization_view_model.py"
)
MAIN_QML = QML_DIRECTORY / "Main.qml"
APP_MODULE = Path(__file__).parents[2] / "src" / "summer_scheduler" / "app.py"


def test_optimization_page_exposes_presets_run_cancel_and_result_details() -> None:
    source = (QML_DIRECTORY / "OptimizationPage.qml").read_text(encoding="utf-8")

    assert '"value": "fast"' in source
    assert '"value": "standard"' in source
    assert '"value": "high_quality"' in source
    assert "高速（30秒）" in source
    assert "標準（120秒）" in source
    assert "高品質（600秒）" in source
    assert "runOptimization(presetBox.currentValue)" in source
    assert "cancelOptimization()" in source
    assert "elapsedSeconds" in source
    assert "solverStatus" in source
    assert "objectiveBreakdown" in source
    assert "unassignedLessons" in source
    assert "warnings" in source
    assert "logPath" in source
    assert "最適化専用ログ保存先" in source
    assert "本格的な時間割グリッド編集は次Phase" not in source


def test_worker_uses_cooperative_cancellation_without_thread_termination() -> None:
    source = VIEW_MODEL.read_text(encoding="utf-8")

    assert "class _OptimizationWorker(QObject):" in source
    assert "moveToThread(thread)" in source
    assert "Qt.ConnectionType.DirectConnection" in source
    assert "CancellationToken()" in source
    assert ".cancel()" in source
    assert "thread.wait(30_000)" in source
    assert "thread.wait()" in source
    assert ".terminate(" not in source
    assert "QThread.terminate" not in source


def test_view_model_keeps_prepare_finalize_and_mark_outside_worker() -> None:
    source = VIEW_MODEL.read_text(encoding="utf-8")
    worker_source = source.split("class _OptimizationWorker", maxsplit=1)[1].split(
        "class OptimizationViewModel",
        maxsplit=1,
    )[0]

    assert "solve_optimization(" in worker_source
    assert ".prepare(" not in worker_source
    assert ".finalize(" not in worker_source
    assert ".mark_cancelled(" not in worker_source
    assert ".mark_failed(" not in worker_source


def test_main_and_application_wire_phase4_page_and_shutdown_guard() -> None:
    main_source = MAIN_QML.read_text(encoding="utf-8")
    app_source = APP_MODULE.read_text(encoding="utf-8")

    assert "readonly property var optimization: optimizationViewModel" in main_source
    assert "root.currentPageIndex === 4" in main_source
    assert "? optimizationComponent" in main_source
    assert "ScheduleEditorPage {" in main_source
    assert "OptimizationPage {" in main_source
    assert 'phaseLabel: "Phase 5"' in main_source
    assert "ロック済み授業を保持して再最適化" in main_source
    assert '"optimizationViewModel"' in app_source
    assert '"scheduleEditorViewModel"' in app_source
    assert "set_project_change_guard(" in app_source
    assert "application.aboutToQuit.connect(optimization_view_model.shutdown)" in app_source
