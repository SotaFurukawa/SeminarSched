"""Phase 7のプロジェクトbackup・破損検出・安全な復元の統合テスト。"""

from __future__ import annotations

import errno
import hashlib
import os
import sqlite3
import stat
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import select

from summer_scheduler.application.master_data_service import MasterDataService
from summer_scheduler.application.project_service import (
    BackupKind,
    ProjectFileError,
    ProjectService,
)
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import CourseProject
from summer_scheduler.ui.viewmodels.workspace_view_model import WorkspaceViewModel


@pytest.fixture
def project_service(tmp_path: Path) -> Iterator[ProjectService]:
    registry = create_database(tmp_path / "管理" / "registry.db")
    upgrade_database(registry.engine)
    service = ProjectService(
        registry,
        tmp_path / "バックアップ",
        automatic_backup_generations=3,
    )
    yield service
    service.close_project()
    registry.dispose()


def _create_project(service: ProjectService, path: Path) -> Path:
    return service.create_project(
        path,
        title="架空の夏期講習",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
    ).path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_automatic_backup_keeps_configured_generations_on_japanese_path(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = _create_project(
        project_service,
        tmp_path / "日本語 フォルダー" / "架空講習.jukuschedule",
    )

    for _ in range(5):
        project_service.create_automatic_backup()

    automatic = [
        candidate
        for candidate in project_service.recovery_candidates(project_path)
        if candidate.kind is BackupKind.AUTOMATIC
    ]
    assert len(automatic) == 3
    assert all(candidate.integrity.is_valid for candidate in automatic)
    assert all(candidate.path.is_file() for candidate in automatic)


def test_corruption_is_detected_and_valid_recovery_candidates_remain(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = _create_project(project_service, tmp_path / "破損確認.jukuschedule")
    project_service.create_automatic_backup()
    project_service.close_project()
    project_path.write_bytes(b"not a sqlite database")

    with pytest.raises(ProjectFileError, match="SQLite形式"):
        project_service.open_project(project_path)

    assert project_service.recovery_target_path == project_path.resolve()
    candidates = project_service.recovery_candidates()
    assert candidates
    assert all(candidate.integrity.is_valid for candidate in candidates)


def test_corrupted_recovery_candidate_is_visible_but_not_usable(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = _create_project(project_service, tmp_path / "候補破損.jukuschedule")
    candidate_path = project_service.create_automatic_backup()
    candidate_path.write_bytes(b"corrupted backup")

    candidate = next(
        item
        for item in project_service.recovery_candidates(project_path)
        if item.path == candidate_path
    )

    assert not candidate.integrity.is_valid
    with pytest.raises(ProjectFileError, match="復元できません"):
        project_service.restore_from_backup(candidate.path)
    assert project_service.current is not None


def test_integrity_check_detects_damaged_sqlite_pages(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = _create_project(project_service, tmp_path / "ページ破損.jukuschedule")
    project_service.close_project()
    with sqlite3.connect(project_path) as connection:
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        root_page = int(
            connection.execute(
                "SELECT rootpage FROM sqlite_master WHERE name = 'course_projects'"
            ).fetchone()[0]
        )
    content = bytearray(project_path.read_bytes())
    assert content.startswith(b"SQLite format 3")
    btree_header_offset = (root_page - 1) * page_size
    assert btree_header_offset < len(content)
    content[btree_header_offset] = 0xFF
    project_path.write_bytes(content)

    result = project_service.check_integrity(project_path)

    assert not result.is_valid
    assert "破損" in result.message or "整合性" in result.message
    with pytest.raises(ProjectFileError, match="破損|整合性"):
        project_service.open_project(project_path)


def test_restore_preserves_pre_restore_copy_and_does_not_modify_selected_backup(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    _create_project(project_service, tmp_path / "復元対象.jukuschedule")
    selected_backup = project_service.create_automatic_backup()
    backup_digest = _digest(selected_backup)

    database = project_service.require_database()
    with database.session_factory.begin() as session:
        project = session.scalar(select(CourseProject))
        assert project is not None
        project.title = "復元前に変更した講習"

    restored = project_service.restore_from_backup(selected_backup)

    assert restored.project.title == "架空の夏期講習"
    assert restored.pre_restore_backup is not None
    assert restored.pre_restore_backup.is_file()
    assert project_service.check_integrity(restored.pre_restore_backup).is_valid
    assert _digest(selected_backup) == backup_digest

    pre_restore_database = create_database(restored.pre_restore_backup)
    try:
        with pre_restore_database.session_factory() as session:
            pre_restore_project = session.scalar(select(CourseProject))
            assert pre_restore_project is not None
            assert pre_restore_project.title == "復元前に変更した講習"
    finally:
        pre_restore_database.dispose()


def test_corrupted_original_is_preserved_before_recovery(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = _create_project(project_service, tmp_path / "破損から復旧.jukuschedule")
    selected_backup = project_service.create_automatic_backup()
    project_service.close_project()
    corrupt_bytes = b"SQLite-corrupt-original-for-test"
    project_path.write_bytes(corrupt_bytes)

    with pytest.raises(ProjectFileError):
        project_service.open_project(project_path)
    restored = project_service.restore_from_backup(selected_backup)

    assert restored.project.path == project_path.resolve()
    assert project_service.check_integrity(project_path).is_valid
    assert restored.pre_restore_backup is not None
    assert restored.pre_restore_backup.read_bytes() == corrupt_bytes


def test_invalid_backup_never_changes_restore_target(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = _create_project(project_service, tmp_path / "変更禁止.jukuschedule")
    original_digest = _digest(project_path)
    invalid_backup = tmp_path / "壊れたバックアップ.jukuschedule"
    invalid_backup.write_bytes(b"broken")

    with pytest.raises(ProjectFileError, match="復元できません"):
        project_service.restore_from_backup(invalid_backup)

    assert _digest(project_path) == original_digest
    assert project_service.current is not None


def test_restore_replace_failure_reopens_unchanged_active_project(
    project_service: ProjectService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = _create_project(project_service, tmp_path / "復元失敗保護.jukuschedule")
    selected_backup = project_service.create_automatic_backup()
    original_digest = _digest(project_path)
    real_replace = os.replace

    def fail_only_final_replace(
        source: str | os.PathLike[str],
        target: str | os.PathLike[str],
    ) -> None:
        if Path(target).resolve() == project_path.resolve():
            raise PermissionError(errno.EACCES, "permission denied")
        real_replace(source, target)

    monkeypatch.setattr(
        os,
        "replace",
        fail_only_final_replace,
    )

    with pytest.raises(ProjectFileError, match="書き込み権限"):
        project_service.restore_from_backup(selected_backup)

    assert _digest(project_path) == original_digest
    assert project_service.current is not None
    assert project_service.current.path == project_path
    assert any(
        candidate.kind is BackupKind.PRE_RESTORE and candidate.integrity.is_valid
        for candidate in project_service.recovery_candidates(project_path)
    )


def test_read_only_project_has_clear_japanese_error(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = _create_project(project_service, tmp_path / "読取専用.jukuschedule")
    project_service.close_project()
    project_path.chmod(stat.S_IREAD)
    try:
        with pytest.raises(ProjectFileError, match="読み取り専用"):
            project_service.open_project(project_path)
        assert project_service.recovery_target_path == project_path.resolve()
    finally:
        project_path.chmod(stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.parametrize(
    ("raised_error", "expected_message"),
    [
        (OSError(errno.ENOSPC, "disk is full"), "空き容量"),
        (PermissionError(errno.EACCES, "permission denied"), "書き込み権限"),
        (OSError(errno.ENAMETOOLONG, "filename too long"), "パスが長すぎ"),
        (
            PermissionError(errno.EACCES, "being used by another process"),
            "OneDrive",
        ),
    ],
)
def test_atomic_backup_failure_is_clear_and_never_changes_source(
    project_service: ProjectService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised_error: OSError,
    expected_message: str,
) -> None:
    project_path = _create_project(project_service, tmp_path / "失敗安全.jukuschedule")
    original_digest = _digest(project_path)
    target = tmp_path / "失敗先" / "backup.jukuschedule"

    def fail_replace(
        _source: str | os.PathLike[str],
        _target: str | os.PathLike[str],
    ) -> None:
        raise raised_error

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(ProjectFileError, match=expected_message):
        project_service.backup(target)

    assert _digest(project_path) == original_digest
    assert not target.exists()
    if target.parent.exists():
        assert not tuple(target.parent.glob("*.tmp"))


def test_abnormal_session_marker_exposes_candidates_to_next_service(
    tmp_path: Path,
) -> None:
    backup_directory = tmp_path / "異常終了バックアップ"
    registry_1 = create_database(tmp_path / "registry-1.db")
    registry_2 = create_database(tmp_path / "registry-2.db")
    upgrade_database(registry_1.engine)
    upgrade_database(registry_2.engine)
    service_1 = ProjectService(registry_1, backup_directory)
    project_path = _create_project(service_1, tmp_path / "異常終了対象.jukuschedule")
    service_1.create_automatic_backup()

    service_2 = ProjectService(registry_2, backup_directory)
    try:
        assert service_2.recovery_target_path == project_path.resolve()
        assert any(candidate.integrity.is_valid for candidate in service_2.recovery_candidates())
    finally:
        service_2.close_project()
        service_1.close_project()
        registry_1.dispose()
        registry_2.dispose()


def test_workspace_exposes_real_recovery_workflow_and_privacy_warning(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    view_model = WorkspaceViewModel(
        project_service,
        MasterDataService(project_service),
    )
    project_path = _create_project(project_service, tmp_path / "画面復旧.jukuschedule")
    view_model.refreshProjectState()

    candidates = cast(list[dict[str, object]], view_model.recoveryCandidates)
    assert candidates
    selected = next(candidate for candidate in candidates if candidate["isValid"])

    assert view_model.restoreProject(str(selected["path"]))
    assert cast(str, view_model.currentProjectTitle) == "架空の夏期講習"
    assert "個人情報" in cast(str, view_model.statusMessage)
    assert project_service.current is not None
    assert project_service.current.path == project_path


def test_same_name_manual_backup_is_not_overwritten(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    _create_project(project_service, tmp_path / "同名保護.jukuschedule")
    target = tmp_path / "手動退避.jukuschedule"
    project_service.backup(target)
    original_digest = _digest(target)

    with pytest.raises(ProjectFileError, match="既にあります"):
        project_service.backup(target)

    assert _digest(target) == original_digest


def test_save_as_existing_file_is_not_overwritten_or_selected(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    current = _create_project(project_service, tmp_path / "現在編集中.jukuschedule")
    existing = project_service.duplicate(tmp_path / "既存の別project.jukuschedule")
    existing_digest = _digest(existing)

    with pytest.raises(ProjectFileError, match="既にあります"):
        project_service.save_as(existing)

    assert _digest(existing) == existing_digest
    assert project_service.current is not None
    assert project_service.current.path == current


def test_failed_open_marker_survives_normal_exit_without_open_project(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "見つからない.jukuschedule"
    with pytest.raises(ProjectFileError, match="見つかりません"):
        project_service.open_project(missing)
    marker = tmp_path / "バックアップ" / "recovery-session.json"
    assert marker.is_file()

    project_service.close_project()

    assert marker.is_file()
    assert project_service.recovery_target_path == missing.resolve()


def test_write_permission_probe_does_not_modify_project_bytes(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = _create_project(project_service, tmp_path / "書込確認.jukuschedule")
    project_service.close_project()
    digest_before = _digest(project_path)

    project_service.open_project(project_path)

    assert _digest(project_path) == digest_before
    assert os.access(project_path, os.R_OK)
