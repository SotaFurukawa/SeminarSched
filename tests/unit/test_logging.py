"""ローカルログ設定の単体テスト。"""

from __future__ import annotations

import logging
from pathlib import Path

from summer_scheduler.infrastructure.logging.configuration import (
    LOGGER_NAME,
    configure_logging,
    shutdown_logging,
)
from summer_scheduler.shared.settings import LoggingSettings


def test_log_file_is_created_with_utf8_japanese_message(tmp_path: Path) -> None:
    settings = LoggingSettings(
        directory=tmp_path / "ログ",
        filename="app.log",
        level="INFO",
        max_bytes=1024 * 1024,
        backup_count=2,
    )

    log_path = configure_logging(settings)
    logging.getLogger(f"{LOGGER_NAME}.test").info("起動確認")
    shutdown_logging()

    assert log_path.is_file()
    assert "起動確認" in log_path.read_text(encoding="utf-8")
