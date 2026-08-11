"""UI刷新で追加した操作導線の静的な回帰契約。"""

from __future__ import annotations

from pathlib import Path

QML_ROOT = Path("src/summer_scheduler/ui/qml")


def _qml(name: str) -> str:
    return (QML_ROOT / name).read_text(encoding="utf-8")


def test_shared_visual_components_and_workflow_navigation_exist() -> None:
    expected_components = {
        "UiTheme.qml",
        "AppButton.qml",
        "StatusBadge.qml",
        "InlineMessage.qml",
        "SectionHeader.qml",
        "EmptyState.qml",
        "StepCard.qml",
        "SidebarNavButton.qml",
    }
    assert expected_components <= {path.name for path in QML_ROOT.glob("*.qml")}

    sidebar = _qml("Sidebar.qml")
    for route in (
        '{"index": 8, "prefix": "①"}',
        '{"index": 4, "prefix": "②"}',
        '{"index": 5, "prefix": "③"}',
        '{"index": 7, "prefix": "④"}',
    ):
        assert route in sidebar

    home = _qml("ProjectHomePage.qml")
    assert "delegate: StepCard {" in home
    for title in ("授業日を決める", "アンケートを取込む", "時間割を配置する", "個人時間割を作る"):
        assert title in home
    assert "次に行うこと" in home


def test_initial_roster_and_questionnaire_follow_guided_flow() -> None:
    students = _qml("StudentPage.qml")
    teachers = _qml("TeacherPage.qml")
    questionnaire = _qml("AvailabilityImportPage.qml")

    for source in (students, teachers):
        assert "Excel一括追加・更新" in source
        assert "WizardStep" in source
        assert "確認" in source
        assert "previewMasterImport" in source
        assert "applyMasterImport" in source
    assert "この画面にもメール欄はありません" in teachers

    for label in ("1　回答ファイルを選ぶ", "2　内容を確認する", "3　反映完了"):
        assert label in questionnaire
    assert "列名が合わない場合の設定" in questionnaire


def test_calendar_timetable_issues_and_output_keep_operational_routes() -> None:
    open_dates = _qml("OpenDateSettingsTab.qml")
    for label in ("すべて選択", "選択解除", "選択日を休校", "選択日を開校"):
        assert label in open_dates
    assert "root.viewModel.setOpenDates(root.checkedDateValues, isOpen)" in open_dates

    group = _qml("GroupLessonPage.qml")
    assert "calendarWeekOffset" in group
    assert "weeklyCalendar" in group
    assert "＋ 授業を追加" in group
    assert "createCalendarGroupLesson(" in group
    assert "validateGroupImport()" in group

    schedule = _qml("ScheduleEditorPage.qml")
    assert "id: unassignedRail" in schedule
    assert 'Drag.keys: ["scheduleLesson"]' in schedule
    assert "root.viewModel.dropMove(" in schedule
    assert "root.viewModel.undo()" in schedule
    assert "root.viewModel.redo()" in schedule

    issues = _qml("ValidationIssuesPage.qml")
    assert "signal navigateRequested(int pageIndex)" in issues
    assert "該当画面を開く" in issues

    output = _qml("OutputPage.qml")
    for label in ("1. 出力対象", "2. 形式", "3. 保存先"):
        assert label in output
    assert "未配置・警告を確認" in output
    assert "openLastOutputFolder()" in output
    assert "advancedSettingsVisible" in output
