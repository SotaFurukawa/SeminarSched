"""UI刷新で追加した操作導線の静的な回帰契約。"""

from __future__ import annotations

from pathlib import Path

QML_ROOT = Path("src/summer_scheduler/ui/qml")
GUIDE_ASSET_ROOT = QML_ROOT / "assets" / "google_forms_guide"


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
        '{"index": 7, "prefix": "①"}',
        '{"index": 8, "prefix": "②"}',
        '{"index": 3, "prefix": "③"}',
        '{"index": 9, "prefix": "④"}',
        '{"index": 4, "prefix": "⑤"}',
        '{"index": 6, "prefix": "⑥"}',
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
        "時間割を完成させる",
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

    for label in ("回答ファイルを選ぶ", "内容を確認する", "反映完了"):
        assert label in questionnaire
    assert "列名が合わない場合の設定" in questionnaire
    for label in (
        "Googleフォーム作成キット",
        "フォーム作成キットを保存…",
        "開校日 %1日／有効コマ %2件",
        "作成手順",
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
    assert "集団授業" not in preconfirmation
    assert "individualGrades" in preconfirmation
    assert "individualStudents" in preconfirmation
    assert "individualSubjects" in preconfirmation
    assert "この個別枠を固定" in preconfirmation
    assert "createPreconfirmedAssignment" in preconfirmation
    assert "createCalendarGroupLesson" not in preconfirmation
    assert "groupViewModel: root.phase3" not in _qml("Main.qml")
    guide = _qml("GoogleFormsGuideDialog.qml")
    for label in (
        "アプリで作成キットを保存",
        "保存先を開く",
        "create_student_questionnaire.gsをメモ帳で開く",
        "Apps Scriptで新しいプロジェクトを作る",
        "メモ帳の内容をコピー＆ペースト",
        "保存して作成関数を実行",
        "権限を確認",
        "詳細を表示し、安全ではないページへ移動",
        "すべて選択して続行",
        "実行ログのリンクからアンケートを開く",
    ):
        assert label in guide
    assert "Google Apps Scriptの「デプロイ」は不要" in guide
    assert "別ウィンドウで表示" in guide
    assert "Window {" in guide
    assert "separateGuideWindow.show()" in guide
    assert guide.count("sourceComponent: guideContentComponent") == 2
    assert "赤い案内" not in guide
    assert "mockScreen" not in guide
    assert "assets/google_forms_authorization_and_csv.png" not in guide
    assert "保存後の手順" not in questionnaire_creation
    expected_assets = {
        "01_save_kit.png",
        "02_open_saved_folder.png",
        "03_open_with_menu.png",
        "03_choose_notepad.png",
        "04_apps_script_home.png",
        "04_blank_code_gs.png",
        "05_paste_script.png",
        "06_select_function.png",
        "07_confirm_permissions.png",
        "08_google_warning.png",
        "08_continue_unsafe.png",
        "09_select_all_continue.png",
        "10_result_links.png",
    }
    assert expected_assets == {path.name for path in GUIDE_ASSET_ROOT.glob("*.png")}
    for asset in expected_assets:
        assert f"assets/google_forms_guide/{asset}" in guide

    for label in (
        "取込み済み回答を編集…",
        "取込み済みの生徒参加可否を編集",
        "表示中をすべて選択",
        "変更しない",
        "参加可",
        "参加不可",
        "休校日は授業を配置しない",
    ):
        assert label in questionnaire
    assert "studentAvailabilityStudents" in questionnaire
    assert "studentAvailabilityDates" in questionnaire
    assert "studentAvailabilityCells" in questionnaire
    assert "loadStudentAvailabilityEditor" in questionnaire
    assert "updateStudentAvailabilityEditor" in questionnaire


def test_date_dropdowns_and_settings_tabs_have_explicit_visual_state() -> None:
    date_field = _qml("DateDropdownField.qml")
    home = _qml("ProjectHomePage.qml")
    questionnaire = _qml("QuestionnaireCreationPage.qml")
    settings = _qml("SettingsPage.qml")
    project_settings = _qml("ProjectSettingsTab.qml")
    slots = _qml("TimeSlotSettingsTab.qml")
    subjects = _qml("SubjectSettingsTab.qml")

    assert "property int fromYear: 2020" in date_field
    assert "property int toYear: 2070" in date_field
    assert "readonly property string dateText" in date_field
    assert home.count("DateDropdownField {") >= 2
    assert project_settings.count("DateDropdownField {") == 2
    assert "startDate.setDateString" in project_settings
    assert "endDate.setDateString" in project_settings
    assert "startDate.dateText" in project_settings
    assert "endDate.dateText" in project_settings
    assert "for (let year = 2020; year <= 2070; ++year)" in project_settings
    assert "TextField {\n                            id: startDate" not in project_settings
    assert "TextField {\n                            id: endDate" not in project_settings
    assert "signal dateEdited" in date_field
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
    assert "root.viewModel.saveOpenDateSchedule(entries)" in open_dates
    assert "変更は自動的に保存されます" in open_dates
    assert "すべての変更を保存" not in open_dates
    assert "function slotCheckState" in open_dates
    assert "Qt.PartiallyChecked" in open_dates
    assert "cellWidth: Math.floor((width - 18) / 7)" in open_dates
    assert "draftRows" in open_dates

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


def test_project_independent_rosters_links_and_equal_import_steps() -> None:
    main = _qml("Main.qml")
    sidebar = _qml("Sidebar.qml")
    students = _qml("StudentPage.qml")
    teachers = _qml("TeacherPage.qml")
    questionnaire = _qml("QuestionnaireCreationPage.qml")
    guide = _qml("GoogleFormsGuideDialog.qml")
    import_page = _qml("AvailabilityImportPage.qml")

    assert "index !== 1 && index !== 2" in main
    assert "model: [1, 2]" in sidebar
    assert "enabled: true" in sidebar
    assert "width: root.width - 10" in sidebar
    assert "visible: true" in students
    assert "visible: true" in teachers
    assert "ListView.view.width - 12" in students
    assert "ListView.view.width - 12" in teachers
    assert 'text: qsTr("Google App Script")' in questionnaire
    assert 'Qt.openUrlExternally("https://script.google.com/home")' in questionnaire
    assert "Text.RichText" in guide
    assert "onLinkActivated" in guide
    assert 'href=\\"https://script.google.com/home\\"' in guide

    step_delegate = import_page[import_page.index("delegate: StatusBadge {") :]
    assert "Layout.preferredWidth: 1" in step_delegate[:700]
