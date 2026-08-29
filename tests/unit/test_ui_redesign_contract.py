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
        "GoogleFormsGuideDialog.qml",
        "DateDropdownField.qml",
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
        '{"index": 9, "prefix": "②"}',
        '{"index": 4, "prefix": "③"}',
        '{"index": 10, "prefix": "④"}',
        '{"index": 5, "prefix": "⑤"}',
        '{"index": 7, "prefix": "⑥"}',
    ):
        assert route in sidebar

    home = _qml("ProjectHomePage.qml")
    assert "delegate: StepCard {" in home
    for title in (
        "授業日を決める",
        "アンケートを作る",
        "回答を取込む",
        "事前確定する",
        "時間割を配置する",
        "個人時間割を作る",
    ):
        assert title in home
    assert "次に行うこと" in home


def test_initial_roster_and_questionnaire_follow_guided_flow() -> None:
    students = _qml("StudentPage.qml")
    teachers = _qml("TeacherPage.qml")
    questionnaire = _qml("AvailabilityImportPage.qml")
    questionnaire_creation = _qml("QuestionnaireCreationPage.qml")

    for source in (students, teachers):
        assert "Excel一括追加・更新" in source
        assert "WizardStep" in source
        assert "確認" in source
        assert "previewMasterImport" in source
        assert "applyMasterImport" in source
    assert "この画面にもメール欄はありません" in teachers
    assert "生徒ID（自動）" in students
    assert "保存時にS-0001形式で自動採番" in students
    assert "生徒ID（必須）" not in students
    assert "講師ID（自動）" in teachers
    assert "保存時にT-0001形式で自動採番" in teachers
    assert "講師ID（必須）" not in teachers

    for label in ("1　回答ファイルを選ぶ", "2　内容を確認する", "3　反映完了"):
        assert label in questionnaire
    assert "列名が合わない場合の設定" in questionnaire
    for label in (
        "Googleフォーム作成キット",
        "フォーム作成キットを保存…",
        "開校日 %1日／有効コマ %2件",
        "画像つき手順",
    ):
        assert label in questionnaire_creation
    assert (
        'Layout.preferredWidth: 110\n                        text: qsTr("生徒回答")'
        in questionnaire
    )
    assert (
        'Layout.preferredWidth: 110\n                        text: qsTr("講師回答")'
        in questionnaire
    )
    assert "workspace: root.workspace" in _qml("Main.qml")
    assert "Googleフォーム作成キット" not in questionnaire
    preconfirmation = _qml("PreconfirmationPage.qml")
    assert "個別指導" in preconfirmation
    assert "集団授業" in preconfirmation
    assert "individualGrades" in preconfirmation
    assert "individualStudents" in preconfirmation
    assert "individualSubjects" in preconfirmation
    assert "この個別枠を固定" in preconfirmation
    assert "この集団授業を固定" in preconfirmation
    assert "createPreconfirmedAssignment" in preconfirmation
    assert "createCalendarGroupLesson" in preconfirmation
    assert "groupViewModel: root.phase3" in _qml("Main.qml")
    guide = _qml("GoogleFormsGuideDialog.qml")
    for label in (
        "アプリで作成キットを保存",
        "Apps Scriptを3つ用意",
        "Code.gsへ全内容を貼り付け",
        "作成関数を選んで実行",
        "実行ログのURLを確認",
    ):
        assert label in guide
    assert "Google Apps Scriptの「デプロイ」は不要" in guide
    assert "赤枠と赤い矢印" in guide
    assert "assets/google_forms_authorization_and_csv.png" in guide
    assert "実画面：初回承認からCSVダウンロードまで" in guide
    assert "権限を確認" in guide
    assert "カンマ区切り形式（.csv）" in guide


def test_date_dropdowns_and_settings_tabs_have_explicit_visual_state() -> None:
    date_field = _qml("DateDropdownField.qml")
    home = _qml("ProjectHomePage.qml")
    questionnaire = _qml("QuestionnaireCreationPage.qml")
    settings = _qml("SettingsPage.qml")
    slots = _qml("TimeSlotSettingsTab.qml")
    subjects = _qml("SubjectSettingsTab.qml")

    assert "property int fromYear: 2020" in date_field
    assert "property int toYear: 2070" in date_field
    assert "readonly property string dateText" in date_field
    assert home.count("DateDropdownField {") >= 2
    assert "questionnaireDeadline.dateText" in questionnaire
    assert "component SettingsTabButton: TabButton" in settings
    assert 'color: tabButton.checked ? "#0f6cbd"' in settings
    assert "implicitWidth: 16" in slots
    assert "leftPadding: 10" in slots
    assert "implicitWidth: 16" in subjects
    assert "leftPadding: 10" in subjects


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
