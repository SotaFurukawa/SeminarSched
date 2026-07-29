"""`.jukuschedule`プロジェクトファイルのライフサイクル管理。"""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Final, NoReturn
from uuid import uuid4

from sqlalchemy import select

from summer_scheduler.domain.defaults import DEFAULT_SUBJECTS, DEFAULT_TIME_SLOTS
from summer_scheduler.domain.validation import (
    DomainValidationError,
    raise_for_errors,
    validate_project,
)
from summer_scheduler.infrastructure.db import (
    Database,
    create_database,
    get_current_revision,
    get_head_revision,
    upgrade_database,
)
from summer_scheduler.infrastructure.db.models import (
    ApplicationMetadata,
    Campus,
    CourseProject,
    OpenDate,
    Subject,
    TimeSlot,
)

PROJECT_EXTENSION: Final = ".jukuschedule"
_RECENT_PROJECTS_KEY: Final = "recent_projects"
_MAX_RECENT_PROJECTS: Final = 10
_RECOVERY_MARKER_FILENAME: Final = "recovery-session.json"

logger = logging.getLogger(__name__)


class ProjectFileError(RuntimeError):
    """プロジェクトファイル操作を安全に完了できなかった場合の例外。"""


class BackupKind(StrEnum):
    """復旧候補として表示するローカルバックアップの種類。"""

    AUTOMATIC = "automatic"
    MIGRATION = "migration"
    PRE_RESTORE = "pre_restore"


@dataclass(frozen=True, slots=True)
class IntegrityCheckResult:
    """SQLiteの整合性検査結果。"""

    is_valid: bool
    message: str


@dataclass(frozen=True, slots=True)
class RecoveryCandidate:
    """特定プロジェクトへ戻せる可能性があるバックアップ。"""

    path: Path
    target_path: Path
    kind: BackupKind
    created_at: datetime
    size_bytes: int
    integrity: IntegrityCheckResult


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """安全な復元後のプロジェクトと、復元前退避の場所。"""

    project: ProjectSummary
    restored_from: Path
    pre_restore_backup: Path | None


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """UIと最近使用した一覧へ返すプロジェクト概要。"""

    path: Path
    project_id: int
    title: str
    campus_name: str
    start_date: date
    end_date: date
    last_opened_at: datetime

    def to_recent_dict(self) -> dict[str, object]:
        """JSONへ保存できる辞書へ変換する。"""
        return {
            "path": str(self.path),
            "project_id": self.project_id,
            "title": self.title,
            "campus_name": self.campus_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "last_opened_at": self.last_opened_at.isoformat(),
        }


class ProjectService:
    """アプリ管理DBと現在のプロジェクトDBを分離して扱う。"""

    def __init__(
        self,
        registry_database: Database,
        backup_directory: Path,
        *,
        automatic_backup_generations: int = 5,
    ) -> None:
        if automatic_backup_generations < 1:
            raise ValueError("自動バックアップ世代数は1以上で指定してください")
        self._registry_database = registry_database
        self._backup_directory = backup_directory.resolve()
        self._automatic_backup_generations = automatic_backup_generations
        self._project_database: Database | None = None
        self._current: ProjectSummary | None = None
        self._safety_warning = ""
        self._session_marker_owned = False
        self._recovery_target_path = self._load_recovery_marker()

    @property
    def current(self) -> ProjectSummary | None:
        """現在開いているプロジェクトを返す。"""
        return self._current

    @property
    def project_database(self) -> Database | None:
        """現在のプロジェクトDBを返す。"""
        return self._project_database

    @property
    def recovery_target_path(self) -> Path | None:
        """正常終了を確認できない、または開けなかった復旧対象を返す。"""
        return self._recovery_target_path

    @property
    def safety_warning(self) -> str:
        """直近の非致命的なバックアップ警告を返す。"""
        return self._safety_warning

    def require_database(self) -> Database:
        """プロジェクト未選択時は日本語エラーにする。"""
        if self._project_database is None:
            raise ProjectFileError("先にプロジェクトを作成または開いてください")
        return self._project_database

    def require_project(self) -> ProjectSummary:
        """現在のプロジェクト概要を返す。"""
        if self._current is None:
            raise ProjectFileError("先にプロジェクトを作成または開いてください")
        return self._current

    def check_integrity(self, path: Path | None = None) -> IntegrityCheckResult:
        """指定ファイルまたは現在のプロジェクトへSQLite整合性検査を実行する。"""
        target = self.require_project().path if path is None else _normalize_project_path(path)
        return _check_project_integrity(target)

    def create_automatic_backup(self) -> Path:
        """現在の整合したDBを自動バックアップし、設定世代数へ整理する。"""
        source = self.require_project().path
        target = self._backup_directory / _backup_filename(
            source,
            kind=BackupKind.AUTOMATIC,
        )
        try:
            _copy_sqlite_atomic(source, target, overwrite=False)
            self._prune_automatic_backups(source)
        except (OSError, sqlite3.Error, ProjectFileError) as exc:
            if isinstance(exc, ProjectFileError):
                raise
            _raise_storage_error("自動バックアップを作成", exc)
        return target

    def recovery_candidates(
        self,
        target_path: Path | None = None,
    ) -> tuple[RecoveryCandidate, ...]:
        """復旧対象に紐づくbackupを、新しい順で整合性結果とともに返す。"""
        target = target_path
        if target is None:
            if self._recovery_target_path is not None:
                target = self._recovery_target_path
            elif self._current is not None:
                target = self._current.path
            else:
                return ()
        normalized = _normalize_project_path(target)
        key = _project_path_key(normalized)
        candidates: list[RecoveryCandidate] = []
        patterns = (
            (BackupKind.AUTOMATIC, f"{BackupKind.AUTOMATIC.value}-{key}-*{PROJECT_EXTENSION}"),
            (BackupKind.MIGRATION, f"{BackupKind.MIGRATION.value}-{key}-*{PROJECT_EXTENSION}"),
            (
                BackupKind.PRE_RESTORE,
                f"{BackupKind.PRE_RESTORE.value}-{key}-*{PROJECT_EXTENSION}",
            ),
        )
        try:
            for kind, pattern in patterns:
                for candidate_path in self._backup_directory.glob(pattern):
                    try:
                        stat = candidate_path.stat()
                    except OSError:
                        continue
                    candidates.append(
                        RecoveryCandidate(
                            path=candidate_path.resolve(),
                            target_path=normalized,
                            kind=kind,
                            created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                            size_bytes=stat.st_size,
                            integrity=_check_project_integrity(candidate_path),
                        )
                    )
        except OSError as exc:
            _raise_storage_error("復旧候補を確認", exc)
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (candidate.created_at, candidate.path.name),
                reverse=True,
            )
        )

    def restore_from_backup(
        self,
        backup_path: Path,
        *,
        target_path: Path | None = None,
    ) -> RestoreResult:
        """選択backupを検証してから、復元前退避を作り原子的に置換する。"""
        backup = _normalize_project_path(backup_path)
        integrity = _check_project_integrity(backup)
        if not integrity.is_valid:
            raise ProjectFileError(f"選択したバックアップを復元できません: {integrity.message}")

        selected_target = target_path
        if selected_target is None:
            if self._current is not None:
                selected_target = self._current.path
            else:
                selected_target = self._recovery_target_path
        if selected_target is None:
            raise ProjectFileError("復元先がありません。先に復旧対象のプロジェクトを開いてください")
        target = _normalize_project_path(selected_target)
        if backup.resolve() == target.resolve():
            raise ProjectFileError("バックアップと復元先には異なるファイルを指定してください")

        prepared = _temporary_path(target)
        prepared_database: Database | None = None
        try:
            _copy_sqlite_atomic(backup, prepared, overwrite=False)
            prepared_database = create_database(prepared)
            upgrade_database(prepared_database.engine)
            _load_project_summary(prepared_database, prepared)
            prepared_database.dispose()
            prepared_database = None
            _verify_project_file(prepared, require_writable=False)
        except Exception as exc:
            if prepared_database is not None:
                prepared_database.dispose()
            _remove_temporary_safely(prepared)
            if isinstance(exc, ProjectFileError):
                raise
            _raise_storage_error("バックアップを復元用に検証", exc)

        pre_restore_backup: Path | None = None
        target_was_current = (
            self._current is not None and self._current.path.resolve() == target.resolve()
        )
        try:
            if target.exists():
                pre_restore_backup = self._create_pre_restore_backup(target)
            if target_was_current:
                self.close_project()
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(prepared, target)
            restored = self.open_project(target)
        except Exception as exc:
            _remove_temporary_safely(prepared)
            if target_was_current and target.is_file() and self._current is None:
                try:
                    self.open_project(target)
                except ProjectFileError:
                    logger.warning("復元失敗後に元のプロジェクトを再度開けませんでした")
            if isinstance(exc, ProjectFileError):
                raise
            _raise_storage_error("バックアップから復元", exc)

        self._recovery_target_path = None
        return RestoreResult(
            project=restored,
            restored_from=backup,
            pre_restore_backup=pre_restore_backup,
        )

    def create_project(
        self,
        path: Path,
        *,
        title: str,
        campus_name: str,
        start_date: date,
        end_date: date,
    ) -> ProjectSummary:
        """既定コマ・科目・開校日を持つ新規ファイルを原子的に作成する。"""
        raise_for_errors(
            validate_project(
                title=title,
                campus_name=campus_name,
                start_date=start_date,
                end_date=end_date,
            )
        )
        target = _normalize_project_path(path)
        if target.exists():
            raise ProjectFileError(f"同名のプロジェクトファイルが既にあります: {target.name}")
        temporary = _temporary_path(target)
        database: Database | None = None

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            database = create_database(temporary)
            upgrade_database(database.engine)
            self._seed_project(
                database,
                title=title.strip(),
                campus_name=campus_name.strip(),
                start_date=start_date,
                end_date=end_date,
            )
            database.dispose()
            database = None
            os.replace(temporary, target)
        except DomainValidationError:
            if database is not None:
                database.dispose()
            _remove_temporary_safely(temporary)
            raise
        except Exception as exc:
            if database is not None:
                database.dispose()
            _remove_temporary_safely(temporary)
            _raise_storage_error("新規プロジェクトを作成", exc)

        return self.open_project(target)

    def open_project(self, path: Path) -> ProjectSummary:
        """既存プロジェクトを検証・migrationして開く。"""
        target = _normalize_project_path(path)
        if not target.is_file():
            self._record_failed_open(target)
            raise ProjectFileError(f"プロジェクトファイルが見つかりません: {target}")
        try:
            _verify_project_file(target, require_writable=True)
        except ProjectFileError:
            self._record_failed_open(target)
            raise

        database = create_database(target)
        try:
            current_revision = get_current_revision(database.engine)
            if current_revision != get_head_revision():
                self._create_pre_migration_backup(target)
            upgrade_database(database.engine)
            summary = _load_project_summary(database, target)
        except Exception as exc:
            database.dispose()
            self._record_failed_open(target)
            if isinstance(exc, ProjectFileError):
                raise
            raise ProjectFileError(
                "プロジェクトを開けませんでした。ファイル形式とログを確認してください。"
            ) from exc

        self.close_project()
        self._project_database = database
        self._current = summary
        self._recovery_target_path = None
        self._safety_warning = ""
        self._write_session_marker(target)
        self._remember_recent(summary)
        try:
            self.create_automatic_backup()
        except ProjectFileError as exc:
            self._safety_warning = (
                f"プロジェクトは開きましたが、自動バックアップを作成できませんでした。{exc}"
            )
            logger.warning("プロジェクトopen時の自動バックアップに失敗しました")
        return summary

    def close_project(self) -> None:
        """現在のプロジェクト接続だけを閉じる。"""
        if self._project_database is not None:
            self._project_database.dispose()
        self._project_database = None
        self._current = None
        if self._session_marker_owned:
            self._clear_session_marker()

    def refresh_current(self) -> ProjectSummary:
        """DBからプロジェクト概要を読み直し、最近使用一覧も更新する。"""
        current = self.require_project()
        summary = _load_project_summary(self.require_database(), current.path)
        self._current = summary
        self._remember_recent(summary)
        return summary

    def save_as(self, path: Path) -> ProjectSummary:
        """現在のDBを別名へ安全に複製し、その新しいファイルへ切り替える。"""
        source = self.require_project().path
        target = _normalize_project_path(path)
        _copy_sqlite_atomic(source, target, overwrite=False)
        return self.open_project(target)

    def duplicate(self, path: Path) -> Path:
        """現在のDBを別ファイルへ複製し、開いているファイルは変えない。"""
        source = self.require_project().path
        target = _normalize_project_path(path)
        _copy_sqlite_atomic(source, target, overwrite=False)
        return target

    def backup(self, path: Path | None = None) -> Path:
        """現在のDBを指定先または利用者別backup領域へ複製する。"""
        source = self.require_project().path
        if path is None:
            timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S-%f")
            target = self._backup_directory / f"{source.stem}_{timestamp}{PROJECT_EXTENSION}"
        else:
            target = _normalize_project_path(path)
        _copy_sqlite_atomic(source, target, overwrite=False)
        return target

    def recent_projects(self) -> tuple[ProjectSummary, ...]:
        """存在する最近使用ファイルを新しい順で返す。"""
        stored = self._load_recent_payload()
        projects: list[ProjectSummary] = []
        for item in stored:
            try:
                summary = _recent_dict_to_summary(item)
            except (KeyError, TypeError, ValueError):
                continue
            if summary.path.is_file():
                projects.append(summary)
        return tuple(projects[:_MAX_RECENT_PROJECTS])

    def _seed_project(
        self,
        database: Database,
        *,
        title: str,
        campus_name: str,
        start_date: date,
        end_date: date,
    ) -> None:
        with database.session_factory.begin() as session:
            campus = Campus(name=campus_name)
            session.add(campus)
            session.flush()
            project = CourseProject(
                campus_id=campus.id,
                title=title,
                start_date=start_date,
                end_date=end_date,
                status="draft",
                file_version=1,
            )
            session.add(project)
            session.flush()

            session.add_all(
                TimeSlot(
                    project_id=project.id,
                    code=item.code,
                    display_name=item.display_name,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    sort_order=item.sort_order,
                    enabled=True,
                )
                for item in DEFAULT_TIME_SLOTS
            )
            session.add_all(
                Subject(
                    code=item.code,
                    display_name=item.display_name,
                    school_level=item.school_level,
                    sort_order=item.sort_order,
                    active=True,
                )
                for item in DEFAULT_SUBJECTS
            )
            session.add_all(
                OpenDate(
                    project_id=project.id,
                    date=current_date,
                    is_open=True,
                    note="",
                )
                for current_date in _date_range(start_date, end_date)
            )
            session.merge(
                ApplicationMetadata(
                    key="project_file_format",
                    value="1",
                    updated_at=datetime.now(tz=UTC),
                )
            )

    def _remember_recent(self, summary: ProjectSummary) -> None:
        payload = [
            item
            for item in self._load_recent_payload()
            if Path(str(item.get("path", ""))).resolve() != summary.path.resolve()
        ]
        payload.insert(0, summary.to_recent_dict())
        encoded = json.dumps(payload[:_MAX_RECENT_PROJECTS], ensure_ascii=False)
        with self._registry_database.session_factory.begin() as session:
            metadata = session.get(ApplicationMetadata, _RECENT_PROJECTS_KEY)
            if metadata is None:
                session.add(
                    ApplicationMetadata(
                        key=_RECENT_PROJECTS_KEY,
                        value=encoded,
                        updated_at=datetime.now(tz=UTC),
                    )
                )
            else:
                metadata.value = encoded
                metadata.updated_at = datetime.now(tz=UTC)

    def _load_recent_payload(self) -> list[dict[str, object]]:
        with self._registry_database.session_factory() as session:
            metadata = session.get(ApplicationMetadata, _RECENT_PROJECTS_KEY)
            if metadata is None:
                return []
            try:
                value = json.loads(metadata.value)
            except json.JSONDecodeError:
                return []
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _create_pre_migration_backup(self, source: Path) -> Path:
        target = self._backup_directory / _backup_filename(
            source,
            kind=BackupKind.MIGRATION,
        )
        _copy_sqlite_atomic(source, target, overwrite=False)
        return target

    def _create_pre_restore_backup(self, source: Path) -> Path:
        target = self._backup_directory / _backup_filename(
            source,
            kind=BackupKind.PRE_RESTORE,
        )
        integrity = _check_project_integrity(source)
        if integrity.is_valid:
            _copy_sqlite_atomic(source, target, overwrite=False)
        else:
            _copy_file_atomic(source, target, overwrite=False)
        return target

    def _prune_automatic_backups(self, source: Path) -> None:
        key = _project_path_key(source)
        backups = sorted(
            self._backup_directory.glob(f"{BackupKind.AUTOMATIC.value}-{key}-*{PROJECT_EXTENSION}"),
            key=lambda path: path.name,
            reverse=True,
        )
        for obsolete in backups[self._automatic_backup_generations :]:
            try:
                obsolete.unlink()
            except OSError as exc:
                _raise_storage_error("古い自動バックアップを整理", exc)

    def _record_failed_open(self, target: Path) -> None:
        self._recovery_target_path = target.resolve()
        if self._current is None:
            self._write_recovery_marker(target, state="failed_open", owned=False)

    def _write_session_marker(self, target: Path) -> None:
        self._write_recovery_marker(target, state="active", owned=True)

    def _write_recovery_marker(
        self,
        target: Path,
        *,
        state: str,
        owned: bool,
    ) -> None:
        marker = self._backup_directory / _RECOVERY_MARKER_FILENAME
        payload = {
            "target_path": str(target.resolve()),
            "state": state,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        try:
            _write_json_atomic(marker, payload)
        except (OSError, TypeError) as exc:
            self._safety_warning = (
                f"異常終了時の復旧情報を保存できませんでした。{_storage_error_message(exc)}"
            )
            logger.warning(
                "復旧markerを保存できませんでした（%s）",
                type(exc).__name__,
            )
            return
        self._session_marker_owned = owned

    def _clear_session_marker(self) -> None:
        marker = self._backup_directory / _RECOVERY_MARKER_FILENAME
        try:
            marker.unlink(missing_ok=True)
        except OSError as exc:
            self._safety_warning = (
                f"正常終了情報を更新できませんでした。{_storage_error_message(exc)}"
            )
            logger.warning(
                "復旧markerを削除できませんでした（%s）",
                type(exc).__name__,
            )
        self._session_marker_owned = False

    def _load_recovery_marker(self) -> Path | None:
        marker = self._backup_directory / _RECOVERY_MARKER_FILENAME
        try:
            with marker.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "復旧markerを読み込めませんでした（%s）",
                type(exc).__name__,
            )
            return None
        if not isinstance(payload, dict):
            return None
        raw_path = payload.get("target_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        return _normalize_project_path(Path(raw_path))


def _load_project_summary(database: Database, path: Path) -> ProjectSummary:
    with database.session_factory() as session:
        projects = list(session.scalars(select(CourseProject)))
        if len(projects) != 1:
            raise ProjectFileError("プロジェクトファイルには講習プロジェクトが1件必要です")
        project = projects[0]
        campus = session.get(Campus, project.campus_id)
        if campus is None:
            raise ProjectFileError("プロジェクトの校舎情報が見つかりません")
        return ProjectSummary(
            path=path.resolve(),
            project_id=project.id,
            title=project.title,
            campus_name=campus.name,
            start_date=project.start_date,
            end_date=project.end_date,
            last_opened_at=datetime.now(tz=UTC),
        )


def _check_project_integrity(path: Path) -> IntegrityCheckResult:
    if not path.is_file():
        return IntegrityCheckResult(False, "プロジェクトファイルが見つかりません")
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=1.0)) as connection:
            check_rows = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check"))
            if check_rows != ("ok",):
                return IntegrityCheckResult(
                    False,
                    "データベースの整合性検査で破損を検出しました",
                )
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
    except sqlite3.Error as exc:
        detail = str(exc).casefold()
        if "not a database" in detail:
            return IntegrityCheckResult(
                False,
                "SQLite形式のプロジェクトファイルではありません",
            )
        return IntegrityCheckResult(
            False,
            "データベースの整合性検査中に破損または読込みエラーを検出しました",
        )
    if "course_projects" not in tables or "alembic_version" not in tables:
        return IntegrityCheckResult(False, "有効な.jukuscheduleプロジェクトではありません")
    return IntegrityCheckResult(True, "データベースの整合性に問題はありません")


def _verify_project_file(path: Path, *, require_writable: bool) -> None:
    result = _check_project_integrity(path)
    if not result.is_valid:
        raise ProjectFileError(result.message)
    if require_writable:
        _verify_project_writable(path)


def _verify_project_writable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        _raise_storage_error("プロジェクトの書込み可否を確認", exc)
    if mode & 0o222 == 0 or not os.access(path, os.W_OK):
        raise ProjectFileError(
            "プロジェクトファイルが読み取り専用です。"
            "書き込み可能なフォルダーへコピーしてから開いてください"
        )
    if not os.access(path.parent, os.W_OK):
        raise ProjectFileError(
            "保存先フォルダーへの書き込み権限がありません。"
            "別のフォルダーへ移動してから開いてください"
        )
    try:
        uri = path.resolve().as_uri() + "?mode=rw"
        with closing(sqlite3.connect(uri, uri=True, timeout=0.1)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
    except sqlite3.Error as exc:
        _raise_storage_error("プロジェクトの書込み可否を確認", exc)


def _normalize_project_path(path: Path) -> Path:
    value = path.expanduser()
    if value.suffix.lower() != PROJECT_EXTENSION:
        value = Path(f"{value}{PROJECT_EXTENSION}")
    return value.resolve()


def _temporary_path(target: Path) -> Path:
    return target.parent / f".{target.name}.{uuid4().hex}.tmp"


def _copy_sqlite_atomic(source: Path, target: Path, *, overwrite: bool) -> None:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ProjectFileError("コピー先には現在と異なるファイル名を指定してください")
    if target.exists() and not overwrite:
        raise ProjectFileError(f"コピー先のファイルが既にあります: {target.name}")
    temporary = _temporary_path(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        source_uri = source.as_uri() + "?mode=ro"
        with (
            closing(sqlite3.connect(source_uri, uri=True, timeout=1.0)) as source_connection,
            closing(sqlite3.connect(temporary)) as target_connection,
        ):
            source_connection.backup(target_connection)
            target_connection.commit()
        copied = _check_project_integrity(temporary)
        if not copied.is_valid:
            raise ProjectFileError(f"コピー後の整合性検査に失敗しました: {copied.message}")
        os.replace(temporary, target)
    except ProjectFileError:
        _remove_temporary_safely(temporary)
        raise
    except (OSError, sqlite3.Error) as exc:
        _remove_temporary_safely(temporary)
        _raise_storage_error("プロジェクトファイルをコピー", exc)


def _copy_file_atomic(source: Path, target: Path, *, overwrite: bool) -> None:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise ProjectFileError("コピー先には現在と異なるファイル名を指定してください")
    if target.exists() and not overwrite:
        raise ProjectFileError(f"コピー先のファイルが既にあります: {target.name}")
    temporary = _temporary_path(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as source_stream, temporary.open("xb") as target_stream:
            shutil.copyfileobj(source_stream, target_stream)
            target_stream.flush()
            os.fsync(target_stream.fileno())
        os.replace(temporary, target)
    except (OSError, sqlite3.Error) as exc:
        _remove_temporary_safely(temporary)
        _raise_storage_error("復元前のファイルを退避", exc)


def _backup_filename(source: Path, *, kind: BackupKind) -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S-%f")
    return f"{kind.value}-{_project_path_key(source)}-{timestamp}{PROJECT_EXTENSION}"


def _project_path_key(path: Path) -> str:
    normalized = str(path.expanduser().resolve()).casefold()
    return sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _write_json_atomic(path: Path, payload: dict[str, str]) -> None:
    temporary = _temporary_path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        _remove_temporary_safely(temporary)
        raise


def _remove_temporary_safely(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "一時プロジェクトファイルを削除できませんでした（%s）",
            type(exc).__name__,
        )


def _storage_error_message(exc: BaseException) -> str:
    detail = str(exc).casefold()
    error_number = exc.errno if isinstance(exc, OSError) else None
    if error_number == errno.ENOSPC or "disk is full" in detail:
        return "ディスクの空き容量が不足しています。空き容量を確保して再試行してください"
    if any(
        marker in detail
        for marker in (
            "database is locked",
            "sharing violation",
            "being used by another process",
            "used by another process",
        )
    ):
        return (
            "ファイルが他のアプリまたはOneDriveの同期処理で使用中です。"
            "同期完了後に再試行してください"
        )
    if error_number in {errno.EACCES, errno.EPERM, errno.EROFS} or any(
        marker in detail
        for marker in (
            "permission denied",
            "readonly",
            "read-only",
            "attempt to write a readonly database",
        )
    ):
        return (
            "ファイルまたは保存先が読み取り専用か、書き込み権限がありません。"
            "書き込み可能な場所を選んでください"
        )
    if error_number == errno.ENAMETOOLONG or "filename too long" in detail:
        return "パスが長すぎます。より短いフォルダー名とファイル名を指定してください"
    return "プロジェクトファイル操作を完了できませんでした。保存先とログを確認してください"


def _raise_storage_error(operation: str, exc: BaseException) -> NoReturn:
    error_number = exc.errno if isinstance(exc, OSError) else None
    logger.warning(
        "%sできませんでした（type=%s, errno=%s）",
        operation,
        type(exc).__name__,
        error_number,
    )
    raise ProjectFileError(f"{operation}できませんでした。{_storage_error_message(exc)}") from exc


def _date_range(start_date: date, end_date: date) -> tuple[date, ...]:
    days = (end_date - start_date).days
    return tuple(start_date + timedelta(days=offset) for offset in range(days + 1))


def _recent_dict_to_summary(value: dict[str, object]) -> ProjectSummary:
    return ProjectSummary(
        path=Path(str(value["path"])).resolve(),
        project_id=int(str(value["project_id"])),
        title=str(value["title"]),
        campus_name=str(value["campus_name"]),
        start_date=date.fromisoformat(str(value["start_date"])),
        end_date=date.fromisoformat(str(value["end_date"])),
        last_opened_at=datetime.fromisoformat(str(value["last_opened_at"])),
    )
