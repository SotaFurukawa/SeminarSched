"""SQLiteエンジンとSQLAlchemyセッション生成器。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import URL, Engine, create_engine, event, text
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker


@dataclass(slots=True)
class Database:
    """アプリケーションが共有するDB接続資源。"""

    engine: Engine
    session_factory: sessionmaker[Session]

    def verify_connection(self) -> None:
        """単純な問い合わせで接続可能か確認する。"""
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        """保持している接続プールを解放する。"""
        self.engine.dispose()


def create_database(database_path: Path) -> Database:
    """Unicodeを含むWindowsパスでも安全なSQLite接続を作る。"""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    url = URL.create("sqlite+pysqlite", database=str(database_path))
    engine = create_engine(url)
    event.listen(engine, "connect", _configure_sqlite_connection)

    return Database(
        engine=engine,
        session_factory=sessionmaker(
            bind=engine,
            class_=Session,
            expire_on_commit=False,
        ),
    )


def _configure_sqlite_connection(
    dbapi_connection: DBAPIConnection,
    _connection_record: Any,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()
