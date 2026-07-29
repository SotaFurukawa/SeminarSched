"""`.jukuschedule`プロジェクト管理の統合テスト。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from summer_scheduler.application.project_service import (
    ProjectFileError,
    ProjectService,
)
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import OpenDate, Subject, TimeSlot


@pytest.fixture
def project_service(tmp_path: Path) -> Iterator[ProjectService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    service = ProjectService(registry, tmp_path / "バックアップ")
    yield service
    service.close_project()
    registry.dispose()


def test_create_save_reopen_and_recent_project(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "日本語プロジェクト"

    created = project_service.create_project(
        project_path,
        title="2026年度 夏期講習",
        campus_name="架空校",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
    )

    assert created.path.name == "日本語プロジェクト.jukuschedule"
    assert created.path.is_file()
    database = project_service.require_database()
    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TimeSlot)) == 5
        assert session.scalar(select(func.count()).select_from(Subject)) == 23
        assert session.scalar(select(func.count()).select_from(OpenDate)) == 3

    project_service.close_project()
    reopened = project_service.open_project(created.path)

    assert reopened.title == "2026年度 夏期講習"
    assert reopened.campus_name == "架空校"
    assert project_service.recent_projects()[0].path == created.path


def test_save_as_duplicate_and_backup_keep_valid_sqlite_files(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    original = project_service.create_project(
        tmp_path / "元データ.jukuschedule",
        title="講習",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
    )

    duplicate = project_service.duplicate(tmp_path / "複製")
    backup = project_service.backup()
    saved_as = project_service.save_as(tmp_path / "別名保存")

    assert original.path.is_file()
    assert duplicate.is_file()
    assert backup.is_file()
    assert saved_as.path.name == "別名保存.jukuschedule"
    project_service.close_project()
    assert project_service.open_project(duplicate).title == "講習"


def test_open_rejects_non_project_sqlite(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "不正.jukuschedule"
    invalid.write_bytes(b"not a sqlite database")

    with pytest.raises(ProjectFileError, match="SQLite形式"):
        project_service.open_project(invalid)
