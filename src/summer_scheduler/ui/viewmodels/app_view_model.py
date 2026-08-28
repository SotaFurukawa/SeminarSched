"""Application-wide state exposed to QML.

This view model intentionally contains presentation state only. Database
initialization is performed by the bootstrap layer, which then reports the
result through :meth:`set_database_ready`.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot


class AppViewModel(QObject):
    """Expose small, application-wide status values to QML."""

    databaseReadyChanged = Signal()

    def __init__(
        self,
        app_version: str,
        schema_version: str,
        *,
        release_channel: str = "Beta",
        database_ready: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._app_version = app_version
        self._schema_version = schema_version
        self._release_channel = release_channel
        self._database_ready = database_ready

    def _get_app_version(self) -> str:
        return self._app_version

    appVersion = Property(str, _get_app_version, constant=True)

    def _get_release_channel(self) -> str:
        return self._release_channel

    releaseChannel = Property(str, _get_release_channel, constant=True)

    def _get_schema_version(self) -> str:
        return self._schema_version

    schemaVersion = Property(str, _get_schema_version, constant=True)

    def _get_database_ready(self) -> bool:
        return self._database_ready

    databaseReady = Property(
        bool,
        _get_database_ready,
        notify=databaseReadyChanged,
    )

    def _get_database_status_text(self) -> str:
        return "DB 準備完了" if self._database_ready else "DB 準備中"

    databaseStatusText = Property(
        str,
        _get_database_status_text,
        notify=databaseReadyChanged,
    )

    @Slot(bool)
    def set_database_ready(self, ready: bool) -> None:
        """Update the database status after bootstrap initialization."""

        if self._database_ready == ready:
            return

        self._database_ready = ready
        self.databaseReadyChanged.emit()
