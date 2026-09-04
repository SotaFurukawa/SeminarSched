"""利用者向け6段階フローと自動保存導線のQML契約。"""

from pathlib import Path

QML = Path(__file__).resolve().parents[2] / "src" / "summer_scheduler" / "ui" / "qml"


def test_home_exposes_six_step_workflow_and_automatic_project_creation() -> None:
    source = (QML / "ProjectHomePage.qml").read_text(encoding="utf-8")

    for label in (
        "授業日を決める",
        "アンケートを作る",
        "回答を取込む",
        "事前確定する",
        "時間割を配置する",
        "時間割を完成させる",
    ):
        assert label in source
    assert "createProjectInWorkspace" in source
    assert "保存先はアプリが自動管理します" in source
    assert "currentFolder: root.viewModel.projectsDirectoryUrl" in source
    assert "新規で基本情報を作成" in source
    assert "作成した基本情報を反映" in source
    assert "Excelで基本情報を編集" in source
    assert 'model: [qsTr("春期"), qsTr("夏期"), qsTr("冬期")]' in source
    assert "for (let year = 2020; year <= 2070; ++year)" in source
    assert source.count("DateDropdownField {") >= 2
    assert "ScrollBar.vertical.policy: ScrollBar.AlwaysOn" in source
    assert 'hasEnabledRow(viewModel.openDates, "isOpen")' in source
    assert 'hasEnabledRow(viewModel.timeSlots, "enabled")' in source
    assert "collectionCount(viewModel.students) > 0" not in source
    assert "collectionCount(viewModel.teachers) > 0" not in source


def test_group_lesson_page_supports_calendar_entry() -> None:
    source = (QML / "GroupLessonPage.qml").read_text(encoding="utf-8")

    assert "＋ カレンダーに追加" in source
    assert "createCalendarGroupLesson" in source
    assert "groupDates" in source
    assert "groupSubjects" in source
    assert "groupTeachers" in source


def test_availability_page_explains_embedded_source_replacement() -> None:
    source = (QML / "AvailabilityImportPage.qml").read_text(encoding="utf-8")

    assert "storedSourceName" in source
    assert ".jukuschedule内に保管" in source
    assert "次回反映時に差し替えます" in source
    assert "おすすめ：" not in source
    assert "カンマ区切り形式（.csv）" in source
    assert "Z・A・B・Cなど複数のチェックが1セル" in source
