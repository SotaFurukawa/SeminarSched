"""設定、ログ、DBをUIより先に準備する起動処理。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.infrastructure.db import (
    Database,
    create_database,
    upgrade_database,
)
from summer_scheduler.infrastructure.logging import configure_logging, shutdown_logging
from summer_scheduler.shared.settings import (
    AppSettings,
    ensure_runtime_directories,
    load_settings,
)

logger = logging.getLogger(__name__)


class BootstrapError(RuntimeError):
    """アプリのローカル実行環境を準備できなかった場合の例外。"""


@dataclass(slots=True)
class RuntimeContext:
    """起動中だけ保持する共有資源。"""

    settings: AppSettings
    database: Database
    projects: ProjectService
    log_path: Path

    def close(self) -> None:
        """DB接続資源を解放する。"""
        logger.info("アプリケーションを終了します")
        self.projects.close_project()
        self.database.dispose()
        shutdown_logging()


def bootstrap(config_path: Path | None = None) -> RuntimeContext:
    """設定を読み、ログを構成し、SQLiteを最新状態にする。"""
    settings = load_settings(config_path)
    ensure_runtime_directories(settings)
    log_path = configure_logging(settings.logging)
    logger.info("アプリケーションの起動準備を開始します")

    database: Database | None = None
    try:
        database = create_database(settings.database_path)
        upgrade_database(database.engine)
        database.verify_connection()
    except Exception as exc:
        if database is not None:
            database.dispose()
        logger.exception("ローカルデータベースの準備に失敗しました")
        shutdown_logging()
        raise BootstrapError(
            "ローカルデータベースを準備できませんでした。ログを確認してください。"
        ) from exc

    logger.info("ローカルデータベースの準備が完了しました")
    projects = ProjectService(
        database,
        backup_directory=settings.data_directory.parent / "backups",
        automatic_backup_generations=settings.backup.automatic_generations,
        workspace_directory=settings.data_directory.parent / "workspace",
    )
    return RuntimeContext(
        settings=settings,
        database=database,
        projects=projects,
        log_path=log_path,
    )
