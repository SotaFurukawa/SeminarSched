"""利用者向け4段階フローと自動保存導線のQML契約。"""

from pathlib import Path

QML = Path(__file__).resolve().parents[2] / "src" / "summer_scheduler" / "ui" / "qml"


def test_home_exposes_four_step_workflow_and_automatic_project_creation() -> None:
    source = (QML / "ProjectHomePage.qml").read_text(encoding="utf-8")

    for label in (
        "授業日を決める",
        "アンケートを取込む",
        "時間割を配置する",
        "個人時間割を作る",
    ):
        assert label in source
    assert "createProjectInWorkspace" in source
    assert "保存先はアプリが自動管理します" in source
    assert "currentFolder: root.viewModel.projectsDirectoryUrl" in source


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
