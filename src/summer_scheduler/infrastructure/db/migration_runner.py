"""アプリ起動時にAlembicマイグレーションを適用する。"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine


def upgrade_database(engine: Engine) -> None:
    """指定エンジンを最新リビジョンまで安全に更新する。"""
    config = Config()
    config.set_main_option("script_location", str(_migration_directory()))

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        with _without_bytecode_cache():
            command.upgrade(config, "head")


def get_current_revision(engine: Engine) -> str | None:
    """DBへ現在適用されているrevisionを返す。"""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def get_head_revision() -> str:
    """パッケージに含まれるmigrationのheadを返す。"""
    with _without_bytecode_cache():
        head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("Alembicのhead revisionが見つかりません")
    return head


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(_migration_directory()))
    return config


def _migration_directory() -> Path:
    return Path(__file__).resolve().parent / "alembic"


@contextmanager
def _without_bytecode_cache() -> Iterator[None]:
    """動的に読むmigration sourceをアプリ本体配下へ書き換えない。"""
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous
