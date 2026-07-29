"""Phase 5時間割編集QMLの表示・操作・仮想化契約。"""

from __future__ import annotations

from pathlib import Path

QML_DIRECTORY = Path(__file__).parents[2] / "src" / "summer_scheduler" / "ui" / "qml"
VIEW_MODEL = (
    Path(__file__).parents[2]
    / "src"
    / "summer_scheduler"
    / "ui"
    / "viewmodels"
    / "schedule_editor_view_model.py"
)
MAIN_QML = QML_DIRECTORY / "Main.qml"
APP_MODULE = Path(__file__).parents[2] / "src" / "summer_scheduler" / "app.py"


def test_schedule_editor_uses_reusable_table_model_for_current_day() -> None:
    qml = (QML_DIRECTORY / "ScheduleEditorPage.qml").read_text(encoding="utf-8")
    python = VIEW_MODEL.read_text(encoding="utf-8")

    assert "TableView {" in qml
    assert "HorizontalHeaderView {" in qml
    assert "VerticalHeaderView {" in qml
    assert qml.count("reuseItems: true") >= 3
    assert "model: root.viewModel.gridModel" in qml
    assert "class ScheduleGridModel(QAbstractTableModel):" in python
    assert "current_date" in python
    assert "for slot in slots:" in python
    assert "for teacher in teachers:" in python


def test_schedule_editor_exposes_date_views_filters_and_required_card_badges() -> None:
    source = (QML_DIRECTORY / "ScheduleEditorPage.qml").read_text(encoding="utf-8")

    assert "‹ 前日" in source
    assert "翌日 ›" in source
    assert "MonthGrid {" in source
    assert "日表示" in source
    assert "複数日サマリー" in source
    assert "dateTabs" in source
    assert "生徒名・講師名を検索" in source
    assert "学年絞込み" in source
    assert "科目絞込み" in source
    assert '"oneToOne"' in source
    assert '"priority5"' in source
    assert '"warning"' in source
    assert '"locked"' in source
    assert '"unassigned"' in source
    assert "未配置のみ" in source
    assert '"studentName"' in source
    assert '"grade"' in source
    assert '"subjectShortName"' in source
    assert '"oneToOneRequired"' in source
    assert '"isPriorityFive"' in source
    assert '"isLocked"' in source
    assert '"isManual"' in source
    assert '"hasWarning"' in source
    assert "集団 ◉" in source


def test_drag_preview_is_not_color_only_and_soft_requires_confirmation() -> None:
    source = (QML_DIRECTORY / "ScheduleEditorPage.qml").read_text(encoding="utf-8")

    assert "DropArea {" in source
    assert 'Drag.keys: ["scheduleLesson"]' in source
    assert "previewMove(" in source
    assert "dropMove(" in source
    assert 'decision === "green"' in source
    assert 'decision === "yellow"' in source
    assert 'decision === "red"' in source
    assert '"icon"' in source
    assert '"message"' in source
    assert '"code"' in VIEW_MODEL.read_text(encoding="utf-8")
    assert '"hardIssueCodes"' in VIEW_MODEL.read_text(encoding="utf-8")
    assert "softWarningDialog" in source
    assert "confirmPendingMove(" in source
    assert '"softDeltas"' in source
    assert '"before"' in source
    assert '"after"' in source

    date_tab_source = source.split("id: dateTab", maxsplit=1)[1].split(
        "SplitView {",
        maxsplit=1,
    )[0]
    assert "dateTabDrop.containsDrag" in date_tab_source
    assert "root.dropColor(" in date_tab_source
    assert "root.dropBorder(" in date_tab_source
    assert "ToolTip.visible: dateTabDrop.containsDrag" in date_tab_source
    assert '"icon"' in date_tab_source
    assert '"message"' in date_tab_source


def test_unassigned_detail_history_diff_undo_lock_and_reoptimization_are_present() -> None:
    source = (QML_DIRECTORY / "ScheduleEditorPage.qml").read_text(encoding="utf-8")

    assert "root.viewModel.unassignedLessons" in source
    assert '"remainingCount"' in source
    assert '"candidateCount"' in source
    assert '"reasonText"' in source
    assert "toggleSelectedLock()" in source
    assert "unassignSelected(" in source
    assert "editSelected(" in source
    assert "root.viewModel.undo()" in source
    assert "root.viewModel.redo()" in source
    assert "root.viewModel.diffRows" in source
    assert "root.viewModel.historyRows" in source
    assert '"beforeSummary"' in source
    assert '"afterSummary"' in source
    assert "変更前: %1" in source
    assert "変更後: %1" in source
    assert "createReoptimizationCheckpoint()" in source
    assert "openOptimizationRequested()" in source
    assert "ロック以外を全体再最適化" in source
    assert "選択日・選択生徒・選択講師だけの部分再最適化" in source


def test_draft_and_pending_changes_are_exposed_as_unsaved_state() -> None:
    source = (QML_DIRECTORY / "ScheduleEditorPage.qml").read_text(encoding="utf-8")
    python = VIEW_MODEL.read_text(encoding="utf-8")

    assert "onAboutToShow:" in source
    assert "setDraftEditing(true)" in source
    assert "onClosed: root.viewModel.setDraftEditing(false)" in source
    assert "hasUnsavedChanges" in source
    assert "saveStateText" in source
    assert "● 編集中・未保存" in python
    assert "△ 確認待ち・未保存" in python
    assert "… 保存処理中" in python
    assert "✓ 自動保存済み" in python
    assert "create_manual_backup()" in python
    assert "バックアップには個人情報が含まれる可能性があります" in python


def test_main_and_application_wire_editor_without_removing_phase4_runner() -> None:
    main = MAIN_QML.read_text(encoding="utf-8")
    app = APP_MODULE.read_text(encoding="utf-8")

    assert "readonly property var scheduleEditor: scheduleEditorViewModel" in main
    assert 'phaseLabel: "Phase 5"' in main
    assert "ScheduleEditorPage {" in main
    assert "OptimizationPage {" in main
    assert "onOpenOptimizationRequested: scheduleWorkspace.currentIndex = 1" in main
    assert "‹ 時間割編集へ戻る" in main
    assert "ScheduleEditorViewModel(" in app
    assert "ScheduleEditService(" in app
    assert '"scheduleEditorViewModel"' in app
    assert "schedule_editor_view_model.scheduleSaved.connect(" in app
