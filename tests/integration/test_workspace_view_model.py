"""QMLとPhase 2ユースケースを結ぶWorkspaceViewModelの統合テスト。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QUrl

from summer_scheduler.application.master_data_service import MasterDataService
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.ui.viewmodels.workspace_view_model import WorkspaceViewModel


def test_unicode_file_url_project_lifecycle_and_qml_weekday_mapping(
    tmp_path: Path,
) -> None:
    registry = create_database(tmp_path / "管理DB" / "registry.db")
    upgrade_database(registry.engine)
    projects = ProjectService(registry, tmp_path / "バックアップ")
    view_model = WorkspaceViewModel(projects, MasterDataService(projects))
    project_path = tmp_path / "日本語プロジェクト.jukuschedule"

    try:
        assert view_model.createProject(
            QUrl.fromLocalFile(str(project_path)).toString(),
            "2026年 夏期講習",
            "架空校",
            "2026-08-01",
            "2026-08-03",
        )
        assert cast(bool, view_model.hasOpenProject)
        assert cast(str, view_model.currentProjectTitle) == "2026年 夏期講習"
        assert len(cast(list[dict[str, object]], view_model.timeSlots)) == 5
        assert len(cast(list[dict[str, object]], view_model.subjects)) == 23
        assert project_path.is_file()

        # QMLの曜日一覧は日曜=0。Pythonのweekday()へ正しく変換する。
        assert view_model.setWeekdayClosed(0)
        sunday = next(
            row
            for row in cast(list[dict[str, object]], view_model.openDates)
            if date.fromisoformat(str(row["date"])).weekday() == 6
        )
        assert sunday["isOpen"] is False

        # カレンダーのチェックボックスから渡される複数日を一括更新できる。
        assert view_model.setOpenDates(["2026-08-01", "2026-08-03"], False)
        open_by_date = {
            str(row["date"]): bool(row["isOpen"])
            for row in cast(list[dict[str, object]], view_model.openDates)
        }
        assert open_by_date == {
            "2026-08-01": False,
            "2026-08-02": False,
            "2026-08-03": False,
        }

        view_model.markDirty()
        assert cast(bool, view_model.isDirty)
        assert not view_model.closeProject(False)
        assert "未保存" in cast(str, view_model.errorMessage)
        view_model.discardDraft()
        assert view_model.closeProject(False)
        assert not cast(bool, view_model.hasOpenProject)
    finally:
        projects.close_project()
        registry.dispose()


def test_qualification_draft_is_saved_as_one_application_operation(
    tmp_path: Path,
) -> None:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    projects = ProjectService(registry, tmp_path / "backups")
    projects.create_project(
        tmp_path / "資格確認.jukuschedule",
        title="資格確認",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
    )
    view_model = WorkspaceViewModel(projects, MasterDataService(projects))

    try:
        assert view_model.refreshAll()
        assert view_model.saveTeacher(0, "T-001", "架空 講師", False, "", True)
        teachers = cast(list[dict[str, object]], view_model.teachers)
        subjects = cast(list[dict[str, object]], view_model.subjects)
        teacher_id = int(str(teachers[0]["id"]))
        view_model.selectTeacher(teacher_id)
        selected_subjects = {
            str(subjects[0]["id"]): True,
            str(subjects[1]["id"]): False,
        }

        assert view_model.saveQualifications(selected_subjects)
        qualifications = {
            int(str(row["subjectId"])): bool(row["canTeach"])
            for row in cast(
                list[dict[str, object]],
                view_model.currentTeacherQualifications,
            )
        }
        assert qualifications[int(str(subjects[0]["id"]))]
        assert not qualifications[int(str(subjects[1]["id"]))]
    finally:
        projects.close_project()
        registry.dispose()


def test_external_guard_prevents_forced_project_close(tmp_path: Path) -> None:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    projects = ProjectService(registry, tmp_path / "backups")
    projects.create_project(
        tmp_path / "実行中.jukuschedule",
        title="実行中",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
    )
    view_model = WorkspaceViewModel(projects, MasterDataService(projects))

    def reject_change() -> None:
        raise ProjectFileError("最適化の実行中はプロジェクトを切り替えられません")

    view_model.set_project_change_guard(reject_change)
    try:
        with pytest.raises(ProjectFileError, match="最適化"):
            view_model.ensure_project_switch_allowed()
        assert not view_model.closeProject(True)
        assert cast(bool, view_model.hasOpenProject)
        assert "最適化" in cast(str, view_model.errorMessage)
    finally:
        projects.close_project()
        registry.dispose()
