"""Phase 7データ復旧QMLとapplication配線の契約テスト。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
QML = ROOT / "src" / "summer_scheduler" / "ui" / "qml" / "ProjectHomePage.qml"
VIEW_MODEL = ROOT / "src" / "summer_scheduler" / "ui" / "viewmodels" / "workspace_view_model.py"
APP = ROOT / "src" / "summer_scheduler" / "app.py"


def test_project_home_exposes_real_recovery_and_privacy_workflow() -> None:
    source = QML.read_text(encoding="utf-8")

    assert "root.viewModel.recoveryTargetPath" in source
    assert "root.viewModel.recoveryCandidates" in source
    assert "root.viewModel.checkCurrentProjectIntegrity()" in source
    assert "root.viewModel.restoreProject(root.pendingRestorePath)" in source
    assert "restoreConfirmDialog" in source
    assert "復元前バックアップ" in source
    assert "個人情報" in source
    assert "isValid" in source


def test_workspace_calls_project_service_instead_of_operating_on_db_from_qml() -> None:
    source = VIEW_MODEL.read_text(encoding="utf-8")

    assert "def createAutomaticBackup(self)" in source
    assert "self._projects.create_automatic_backup()" in source
    assert "def restoreProject(self, backup_path_value: str)" in source
    assert "self._projects.restore_from_backup(" in source
    assert "def checkCurrentProjectIntegrity(self)" in source
    assert "self._projects.check_integrity()" in source


def test_application_timer_uses_configured_backup_interval() -> None:
    source = APP.read_text(encoding="utf-8")

    assert "automatic_backup_timer = QTimer(application)" in source
    assert "runtime.settings.backup.automatic_interval_minutes" in source
    assert "workspace_view_model.createAutomaticBackup" in source
