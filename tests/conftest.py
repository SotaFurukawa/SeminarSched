"""テスト間でローカル環境設定が漏れないようにするfixture。"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QGuiApplication

_SETTINGS_ENVIRONMENT_VARIABLES = (
    "SUMMER_SCHEDULER_CONFIG",
    "SUMMER_SCHEDULER_DATA_DIR",
    "SUMMER_SCHEDULER_DATABASE_PATH",
    "SUMMER_SCHEDULER_LOG_DIR",
)


@pytest.fixture(scope="session")
def qt_gui_app() -> Iterator[QGuiApplication]:
    """全in-process Qt testで1個のoffscreen applicationを共有する。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    existing = QCoreApplication.instance()
    if existing is None:
        app = QGuiApplication(["pytest", "-platform", "offscreen"])
    elif isinstance(existing, QGuiApplication):
        app = existing
    else:
        raise RuntimeError("QGuiApplicationより先にQCoreApplicationが作成されました")
    yield app
    app.processEvents()


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """開発端末のアプリ用環境変数を各テストから隔離する。"""
    for name in _SETTINGS_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
