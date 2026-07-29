"""Phase 6の出力設定・非同期生成・一時PDFプレビューをQMLへ公開する。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, TypeVar, cast
from uuid import uuid4

from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QObject,
    QStandardPaths,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)

from summer_scheduler.application.output_service import OutputService, OutputServiceError
from summer_scheduler.application.phase6_dto import OutputResultDto, OutputWorkspaceDto
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.infrastructure.exporting import (
    OutputDestinationExistsError,
    OutputExportError,
)
from summer_scheduler.reporting.builder import ReportKind
from summer_scheduler.reporting.data import OutputSelection
from summer_scheduler.reporting.settings import (
    OutputSettings,
    OutputSettingsValidationError,
    PageOrientation,
    PaperSize,
    StudentPageMode,
    StyleRule,
)

logger = logging.getLogger(__name__)

OutputFormat = Literal["xlsx", "pdf", "csv"]
OutputKind = Literal["overall", "students", "teachers", "issues", "raw"]
_SelectionValue = TypeVar("_SelectionValue", date, int)

_REPORT_OPTIONS = (
    {"label": "全体時間割", "value": "overall"},
    {"label": "生徒別時間割", "value": "students"},
    {"label": "講師別時間割", "value": "teachers"},
    {"label": "未配置・警告一覧", "value": "issues"},
    {"label": "割当て生データ", "value": "raw"},
)
_FORMAT_OPTIONS = (
    {"label": "Excel（.xlsx）", "value": "xlsx"},
    {"label": "PDF（.pdf）", "value": "pdf"},
    {"label": "CSV（.csv）", "value": "csv"},
)
_VISIBLE_FIELD_OPTIONS = (
    {"label": "学年", "value": "grade"},
    {"label": "科目", "value": "subject"},
    {"label": "1対1", "value": "one_to_one"},
    {"label": "ロック", "value": "locked"},
    {"label": "手動変更", "value": "manual"},
    {"label": "警告", "value": "warning"},
    {"label": "備考", "value": "note"},
    {"label": "集団授業", "value": "group"},
)
_VALID_REPORT_KINDS = frozenset(row["value"] for row in _REPORT_OPTIONS)
_VALID_FORMATS = frozenset(row["value"] for row in _FORMAT_OPTIONS)
_VALID_VISIBLE_FIELDS = frozenset(row["value"] for row in _VISIBLE_FIELD_OPTIONS)
_LOGO_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp"})


@dataclass(frozen=True, slots=True)
class _OutputJob:
    kind: OutputKind
    output_format: OutputFormat
    destination: Path
    selection: OutputSelection
    settings: OutputSettings
    overwrite: bool
    is_preview: bool


@dataclass(frozen=True, slots=True)
class _OutputFailure:
    message: str
    exception_type: str
    overwrite_required: bool


class _OutputWorker(QObject):
    """DBをQMLへ漏らさず、出力Serviceを専用threadで実行するworker。"""

    completed = Signal(object)
    failed = Signal(object)
    done = Signal()

    def __init__(self, service: OutputService, job: _OutputJob) -> None:
        super().__init__()
        self._service = service
        self._job = job

    @Slot()
    def run(self) -> None:
        try:
            result = self._execute()
        except Exception as exc:
            if not _is_expected_output_error(exc):
                # 例外値には氏名や保存先が含まれ得るため、値だけを伏せて
                # tracebackをローカルログへ残す。
                logger.exception(
                    "出力workerで予期しないエラーが発生しました（%s）",
                    type(exc).__name__,
                    exc_info=(
                        type(exc),
                        RuntimeError("例外の詳細値は安全のため省略しました"),
                        exc.__traceback__,
                    ),
                )
            self.failed.emit(_failure_from_exception(exc))
        else:
            self.completed.emit(result)
        finally:
            self.done.emit()

    def _execute(self) -> OutputResultDto:
        job = self._job
        if job.is_preview:
            return self._service.export_pdf(
                cast(ReportKind, job.kind),
                job.destination,
                job.selection,
                settings_override=job.settings,
                overwrite=True,
            )
        if job.output_format == "xlsx":
            return self._service.export_excel(
                cast(ReportKind, job.kind),
                job.destination,
                job.selection,
                settings_override=job.settings,
                overwrite=job.overwrite,
            )
        if job.output_format == "pdf":
            return self._service.export_pdf(
                cast(ReportKind, job.kind),
                job.destination,
                job.selection,
                settings_override=job.settings,
                overwrite=job.overwrite,
            )
        return self._service.export_csv(
            job.destination,
            job.selection,
            settings_override=job.settings,
            overwrite=job.overwrite,
        )


class _WorkspaceWorker(QObject):
    """出力直前再診断を含むワークスペース読込みをUI thread外で実行する。"""

    completed = Signal(object)
    failed = Signal(object)
    done = Signal()

    def __init__(self, service: OutputService) -> None:
        super().__init__()
        self._service = service

    @Slot()
    def run(self) -> None:
        try:
            workspace = self._service.load_workspace(refresh=True)
        except Exception as exc:
            if not _is_expected_output_error(exc):
                logger.exception(
                    "出力ワークスペースworkerで予期しないエラーが発生しました（%s）",
                    type(exc).__name__,
                    exc_info=(
                        type(exc),
                        RuntimeError("例外の詳細値は安全のため省略しました"),
                        exc.__traceback__,
                    ),
                )
            self.failed.emit(_failure_from_exception(exc))
        else:
            self.completed.emit(workspace)
        finally:
            self.done.emit()


class OutputViewModel(QObject):
    """出力画面のdraft状態と、生成中のライフサイクルを管理する。"""

    projectStateChanged = Signal()
    workspaceChanged = Signal()
    settingsChanged = Signal()
    selectionChanged = Signal()
    outputStateChanged = Signal()
    messageChanged = Signal()
    previewChanged = Signal()
    overwriteConfirmationRequested = Signal(str)
    outputGenerated = Signal(str)

    def __init__(
        self,
        service: OutputService,
        projects: ProjectService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._projects = projects
        self._workspace: OutputWorkspaceDto | None = None
        self._settings: OutputSettings | None = None
        self._saved_settings: OutputSettings | None = None
        self._settings_dirty = False

        self._selected_dates: set[date] = set()
        self._selected_teacher_ids: set[int] = set()
        self._selected_student_ids: set[int] = set()
        self._report_kind: OutputKind = "overall"
        self._output_format: OutputFormat = "xlsx"
        self._destination: Path | None = None
        self._overwrite_required = False

        self._is_busy = False
        self._busy_text = ""
        self._status_message = ""
        self._error_message = ""
        self._last_output_path: Path | None = None
        self._last_result_summary = ""

        self._preview_directory: TemporaryDirectory[str] | None = None
        self._preview_path: Path | None = None
        self._preview_files: set[Path] = set()
        self._preview_page_count = 0

        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._active_job: _OutputJob | None = None
        self._completion_handled = False
        self._shutdown_requested = False
        self._project_refresh_pending = False

    # QML properties: project/workspace

    def _get_has_open_project(self) -> bool:
        return self._projects.current is not None

    hasOpenProject = Property(bool, _get_has_open_project, notify=projectStateChanged)

    def _get_workspace_loaded(self) -> bool:
        return self._workspace is not None

    workspaceLoaded = Property(bool, _get_workspace_loaded, notify=workspaceChanged)

    def _get_project_title(self) -> str:
        return self._workspace.project_title if self._workspace is not None else ""

    projectTitle = Property(str, _get_project_title, notify=workspaceChanged)

    def _get_campus_name(self) -> str:
        return self._workspace.campus_name if self._workspace is not None else ""

    campusName = Property(str, _get_campus_name, notify=workspaceChanged)

    def _get_assignment_count(self) -> int:
        return self._workspace.assignment_count if self._workspace is not None else 0

    assignmentCount = Property(int, _get_assignment_count, notify=workspaceChanged)

    def _get_group_lesson_count(self) -> int:
        return self._workspace.group_lesson_count if self._workspace is not None else 0

    groupLessonCount = Property(int, _get_group_lesson_count, notify=workspaceChanged)

    def _get_unassigned_count(self) -> int:
        return self._workspace.unassigned_count if self._workspace is not None else 0

    unassignedCount = Property(int, _get_unassigned_count, notify=workspaceChanged)

    def _get_warning_count(self) -> int:
        return self._workspace.warning_count if self._workspace is not None else 0

    warningCount = Property(int, _get_warning_count, notify=workspaceChanged)

    # QML properties: report, destination and run state

    def _get_report_options(self) -> list[dict[str, str]]:
        return [dict(row) for row in _REPORT_OPTIONS]

    reportOptions = Property(list, _get_report_options, constant=True)

    def _get_format_options(self) -> list[dict[str, str]]:
        return [dict(row) for row in _FORMAT_OPTIONS]

    formatOptions = Property(list, _get_format_options, constant=True)

    def _get_report_kind(self) -> str:
        return self._report_kind

    reportKind = Property(str, _get_report_kind, notify=outputStateChanged)

    def _get_output_format(self) -> str:
        return self._output_format

    outputFormat = Property(str, _get_output_format, notify=outputStateChanged)

    def _get_destination_path(self) -> str:
        return str(self._destination) if self._destination is not None else ""

    destinationPath = Property(str, _get_destination_path, notify=outputStateChanged)

    def _get_destination_url(self) -> QUrl:
        if self._destination is None:
            return QUrl()
        return QUrl.fromLocalFile(str(self._destination))

    destinationUrl = Property(QUrl, _get_destination_url, notify=outputStateChanged)

    def _get_destination_exists(self) -> bool:
        return self._destination is not None and self._destination.exists()

    destinationExists = Property(bool, _get_destination_exists, notify=outputStateChanged)

    def _get_is_busy(self) -> bool:
        return self._is_busy

    isBusy = Property(bool, _get_is_busy, notify=outputStateChanged)

    def _get_busy_text(self) -> str:
        return self._busy_text

    busyText = Property(str, _get_busy_text, notify=outputStateChanged)

    def _get_overwrite_required(self) -> bool:
        return self._overwrite_required

    overwriteRequired = Property(bool, _get_overwrite_required, notify=outputStateChanged)

    def _get_can_generate(self) -> bool:
        return (
            self._workspace is not None
            and self._settings is not None
            and self._destination is not None
            and not self._is_busy
        )

    canGenerate = Property(bool, _get_can_generate, notify=outputStateChanged)

    def _get_can_preview(self) -> bool:
        return (
            self._workspace is not None
            and self._settings is not None
            and self._report_kind != "raw"
            and not self._is_busy
        )

    canPreview = Property(bool, _get_can_preview, notify=outputStateChanged)

    def _get_last_output_path(self) -> str:
        return str(self._last_output_path) if self._last_output_path is not None else ""

    lastOutputPath = Property(str, _get_last_output_path, notify=outputStateChanged)

    def _get_last_result_summary(self) -> str:
        return self._last_result_summary

    lastResultSummary = Property(str, _get_last_result_summary, notify=outputStateChanged)

    # QML properties: settings draft

    def _get_settings_dirty(self) -> bool:
        return self._settings_dirty

    settingsDirty = Property(bool, _get_settings_dirty, notify=settingsChanged)

    def _get_paper_size(self) -> str:
        return self._settings.paper_size if self._settings is not None else "A3"

    paperSize = Property(str, _get_paper_size, notify=settingsChanged)

    def _get_orientation(self) -> str:
        return self._settings.orientation if self._settings is not None else "landscape"

    orientation = Property(str, _get_orientation, notify=settingsChanged)

    def _get_days_per_page(self) -> int:
        return self._settings.days_per_page if self._settings is not None else 2

    daysPerPage = Property(int, _get_days_per_page, notify=settingsChanged)

    def _get_teacher_columns_per_page(self) -> int:
        return self._settings.teacher_columns_per_page if self._settings is not None else 8

    teacherColumnsPerPage = Property(
        int,
        _get_teacher_columns_per_page,
        notify=settingsChanged,
    )

    def _get_font_size(self) -> float:
        return self._settings.font_size if self._settings is not None else 8.0

    fontSize = Property(float, _get_font_size, notify=settingsChanged)

    def _get_margin_mm(self) -> float:
        return self._settings.margin_mm if self._settings is not None else 8.0

    marginMm = Property(float, _get_margin_mm, notify=settingsChanged)

    def _get_student_page_mode(self) -> str:
        if self._settings is None:
            return "one_per_page"
        return self._settings.student_page_mode

    studentPageMode = Property(str, _get_student_page_mode, notify=settingsChanged)

    def _get_csv_with_bom(self) -> bool:
        return self._settings.csv_with_bom if self._settings is not None else True

    csvWithBom = Property(bool, _get_csv_with_bom, notify=settingsChanged)

    def _get_file_name_pattern(self) -> str:
        return self._settings.file_name_pattern if self._settings is not None else "{report}"

    fileNamePattern = Property(str, _get_file_name_pattern, notify=settingsChanged)

    def _get_logo_path(self) -> str:
        if self._settings is None:
            return ""
        return self._settings.logo_path_optional or ""

    logoPath = Property(str, _get_logo_path, notify=settingsChanged)

    def _get_logo_url(self) -> QUrl:
        path_value = self._get_logo_path()
        return QUrl.fromLocalFile(path_value) if path_value else QUrl()

    logoUrl = Property(QUrl, _get_logo_url, notify=settingsChanged)

    def _get_visible_field_options(self) -> list[dict[str, object]]:
        selected = set(self._settings.visible_fields) if self._settings is not None else set()
        return [
            {
                "label": row["label"],
                "value": row["value"],
                "selected": row["value"] in selected,
            }
            for row in _VISIBLE_FIELD_OPTIONS
        ]

    visibleFieldOptions = Property(
        list,
        _get_visible_field_options,
        notify=settingsChanged,
    )

    def _get_default_output_directory(self) -> str:
        if self._settings is None:
            return ""
        return self._settings.default_output_directory_optional or ""

    defaultOutputDirectory = Property(
        str,
        _get_default_output_directory,
        notify=settingsChanged,
    )

    def _get_default_output_directory_url(self) -> QUrl:
        path_value = self._get_default_output_directory()
        return QUrl.fromLocalFile(path_value) if path_value else QUrl()

    defaultOutputDirectoryUrl = Property(
        QUrl,
        _get_default_output_directory_url,
        notify=settingsChanged,
    )

    def _get_style_rules(self) -> list[dict[str, str]]:
        if self._settings is None:
            return []
        return [
            {
                "code": rule.code,
                "label": rule.label,
                "marker": rule.marker,
                "fillColor": rule.fill_color,
                "textColor": rule.text_color,
            }
            for rule in self._settings.style_rules
        ]

    styleRules = Property(list, _get_style_rules, notify=settingsChanged)

    # QML properties: selection

    def _get_date_options(self) -> list[dict[str, object]]:
        workspace = self._workspace
        if workspace is None:
            return []
        return [
            {
                "value": row.value.isoformat(),
                "label": row.label,
                "isOpen": row.is_open,
                "selected": row.value in self._selected_dates,
            }
            for row in workspace.dates
        ]

    dateOptions = Property(list, _get_date_options, notify=selectionChanged)

    def _get_teacher_options(self) -> list[dict[str, object]]:
        workspace = self._workspace
        if workspace is None:
            return []
        return [
            {
                "id": row.id,
                "label": row.label,
                "secondaryText": row.secondary_text,
                "selected": row.id in self._selected_teacher_ids,
            }
            for row in workspace.teachers
        ]

    teacherOptions = Property(list, _get_teacher_options, notify=selectionChanged)

    def _get_student_options(self) -> list[dict[str, object]]:
        workspace = self._workspace
        if workspace is None:
            return []
        return [
            {
                "id": row.id,
                "label": row.label,
                "secondaryText": row.secondary_text,
                "selected": row.id in self._selected_student_ids,
            }
            for row in workspace.students
        ]

    studentOptions = Property(list, _get_student_options, notify=selectionChanged)

    # QML properties: messages and preview

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=messageChanged)

    def _get_error_message(self) -> str:
        return self._error_message

    errorMessage = Property(str, _get_error_message, notify=messageChanged)

    def _get_preview_url(self) -> QUrl:
        if self._preview_path is None:
            return QUrl()
        return QUrl.fromLocalFile(str(self._preview_path))

    previewUrl = Property(QUrl, _get_preview_url, notify=previewChanged)

    def _get_has_preview(self) -> bool:
        return self._preview_path is not None and self._preview_path.is_file()

    hasPreview = Property(bool, _get_has_preview, notify=previewChanged)

    def _get_preview_page_count(self) -> int:
        return self._preview_page_count

    previewPageCount = Property(int, _get_preview_page_count, notify=previewChanged)

    # Public lifecycle

    def ensure_project_switch_allowed(self) -> None:
        if self._is_busy:
            raise ProjectFileError("出力またはプレビューの生成中はプロジェクトを切り替えられません")
        if self._settings_dirty:
            raise ProjectFileError(
                "未保存の出力設定があります。保存または元に戻してから切り替えてください"
            )

    @Slot()
    def refreshProjectState(self) -> None:
        """プロジェクト変更時は古いスナップショットと個人選択を破棄する。"""
        if self._is_busy or self._thread is not None:
            self._project_refresh_pending = True
            return
        self._project_refresh_pending = False
        self._service.invalidate()
        current = self._projects.current
        if (
            self._settings_dirty
            and self._workspace is not None
            and current is not None
            and getattr(current, "project_id", None) == self._workspace.project_id
        ):
            self._set_status(
                "時間割が更新されました。出力設定を保存または元に戻してから再読込みしてください"
            )
            return
        self._reset_workspace()
        self.projectStateChanged.emit()
        self.workspaceChanged.emit()
        self.selectionChanged.emit()
        self.outputStateChanged.emit()

    @Slot(result=bool)
    def refreshWorkspace(self) -> bool:
        if self._is_busy:
            self._set_error("出力処理中はデータを再読込みできません")
            return False
        if self._settings_dirty:
            self._set_error(
                "未保存の出力設定があります。保存または元に戻してから再読込みしてください"
            )
            return False
        if self._projects.current is None:
            self._reset_workspace()
            self.projectStateChanged.emit()
            self.workspaceChanged.emit()
            self.selectionChanged.emit()
            self.outputStateChanged.emit()
            self._set_error("先にプロジェクトを作成または開いてください")
            return False
        self._service.invalidate()
        self.clearPreview()
        return self._start_workspace_load()

    @Slot()
    def shutdown(self) -> None:
        """生成中ファイルを完了させ、一時プレビューをアプリ終了時に削除する。"""
        self._shutdown_requested = True
        thread = self._thread
        if thread is not None and thread.isRunning():
            if not thread.wait(30_000):
                logger.warning("出力workerの完了に30秒以上かかっています")
                thread.wait()
        self._thread = None
        self._worker = None
        self._active_job = None
        self._is_busy = False
        self._project_refresh_pending = False
        self._preview_path = None
        self.previewChanged.emit()
        QCoreApplication.processEvents()
        self._cleanup_preview_directory()

    # Report/output actions

    @Slot(str, result=bool)
    def setReportKind(self, value: str) -> bool:
        if value not in _VALID_REPORT_KINDS:
            self._set_error("未対応の帳票種別です")
            return False
        self._report_kind = cast(OutputKind, value)
        if self._report_kind == "raw":
            self._output_format = "csv"
        elif self._output_format == "csv":
            self._output_format = "xlsx"
        self.clearPreview()
        self._overwrite_required = False
        self._set_suggested_destination(reset_directory=False)
        self.outputStateChanged.emit()
        return True

    @Slot(str, result=bool)
    def setOutputFormat(self, value: str) -> bool:
        if value not in _VALID_FORMATS:
            self._set_error("出力形式はExcel・PDF・CSVから選択してください")
            return False
        self._output_format = cast(OutputFormat, value)
        if self._output_format == "csv":
            self._report_kind = "raw"
        elif self._report_kind == "raw":
            self._report_kind = "overall"
        self.clearPreview()
        self._overwrite_required = False
        self._set_suggested_destination(reset_directory=False)
        self.outputStateChanged.emit()
        return True

    @Slot(str, result=bool)
    def setDestination(self, value: str) -> bool:
        try:
            destination = _path_from_qml(value)
            self._destination = _path_with_extension(destination, self._output_format)
        except ValueError as exc:
            self._set_error(str(exc))
            return False
        self._overwrite_required = False
        self.outputStateChanged.emit()
        return True

    @Slot(bool, result=bool)
    def generateOutput(self, overwrite: bool = False) -> bool:
        if not self._ensure_ready_for_generation():
            return False
        assert self._settings is not None
        assert self._destination is not None
        try:
            selection = self._selection()
            self._settings.validate()
        except (OutputSettingsValidationError, ValueError) as exc:
            self._set_error(str(exc))
            return False
        destination = _path_with_extension(self._destination, self._output_format)
        self._destination = destination
        if destination.exists() and not overwrite:
            self._overwrite_required = True
            self.outputStateChanged.emit()
            self.overwriteConfirmationRequested.emit(destination.name)
            return False
        self._overwrite_required = False
        job = _OutputJob(
            kind=self._report_kind,
            output_format=self._output_format,
            destination=destination,
            selection=selection,
            settings=self._settings,
            overwrite=overwrite,
            is_preview=False,
        )
        return self._start_job(job, "出力ファイルを生成しています")

    @Slot(result=bool)
    def generatePreview(self) -> bool:
        if not self._ensure_ready_for_generation():
            return False
        if self._report_kind == "raw":
            self._set_error("CSV生データはPDFプレビューの対象外です")
            return False
        assert self._settings is not None
        try:
            selection = self._selection()
            self._settings.validate()
        except (OutputSettingsValidationError, ValueError) as exc:
            self._set_error(str(exc))
            return False
        self.clearPreview()
        destination = self._new_preview_path()
        job = _OutputJob(
            kind=self._report_kind,
            output_format="pdf",
            destination=destination,
            selection=selection,
            settings=self._settings,
            overwrite=True,
            is_preview=True,
        )
        return self._start_job(job, "印刷プレビューを生成しています")

    @Slot()
    def cancelOverwriteConfirmation(self) -> None:
        self._overwrite_required = False
        self.outputStateChanged.emit()

    @Slot()
    def clearPreview(self) -> None:
        if self._preview_path is None and self._preview_page_count == 0:
            return
        self._preview_path = None
        self._preview_page_count = 0
        self.previewChanged.emit()
        QTimer.singleShot(0, self._cleanup_inactive_preview_files)

    # Settings draft actions

    @Slot(str, result=bool)
    def setPaperSize(self, value: str) -> bool:
        if value not in {"A3", "A4"}:
            self._set_error("用紙はA3またはA4を指定してください")
            return False
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return self._replace_settings(replace(self._settings, paper_size=cast(PaperSize, value)))

    @Slot(str, result=bool)
    def setOrientation(self, value: str) -> bool:
        if value not in {"landscape", "portrait"}:
            self._set_error("向きは横または縦を指定してください")
            return False
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return self._replace_settings(
            replace(self._settings, orientation=cast(PageOrientation, value))
        )

    @Slot(int, result=bool)
    def setDaysPerPage(self, value: int) -> bool:
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return self._replace_settings(replace(self._settings, days_per_page=value))

    @Slot(int, result=bool)
    def setTeacherColumnsPerPage(self, value: int) -> bool:
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return self._replace_settings(replace(self._settings, teacher_columns_per_page=value))

    @Slot(float, result=bool)
    def setFontSize(self, value: float) -> bool:
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return self._replace_settings(replace(self._settings, font_size=value))

    @Slot(float, result=bool)
    def setMarginMm(self, value: float) -> bool:
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return self._replace_settings(replace(self._settings, margin_mm=value))

    @Slot(str, result=bool)
    def setStudentPageMode(self, value: str) -> bool:
        if value not in {"one_per_page", "combined"}:
            self._set_error("生徒別の改ページ設定が不正です")
            return False
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return self._replace_settings(
            replace(
                self._settings,
                student_page_mode=cast(StudentPageMode, value),
            )
        )

    @Slot(bool, result=bool)
    def setCsvWithBom(self, value: bool) -> bool:
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return self._replace_settings(replace(self._settings, csv_with_bom=value))

    @Slot(str, result=bool)
    def setFileNamePattern(self, value: str) -> bool:
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        changed = self._replace_settings(replace(self._settings, file_name_pattern=value))
        if changed:
            self._set_suggested_destination(reset_directory=False)
            self.outputStateChanged.emit()
        return changed

    @Slot(str, str, str, str, result=bool)
    def setStyleRule(
        self,
        code: str,
        marker: str,
        fill_color: str,
        text_color: str,
    ) -> bool:
        settings = self._settings
        if settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        found = False
        rules: list[StyleRule] = []
        for rule in settings.style_rules:
            if rule.code != code:
                rules.append(rule)
                continue
            found = True
            rules.append(
                replace(
                    rule,
                    marker=marker,
                    fill_color=fill_color,
                    text_color=text_color,
                )
            )
        if not found:
            self._set_error("変更する表示ルールが見つかりません")
            return False
        return self._replace_settings(replace(settings, style_rules=tuple(rules)))

    @Slot(str, result=bool)
    def setLogoPath(self, value: str) -> bool:
        settings = self._settings
        if settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        if not value.strip():
            return self._replace_settings(replace(settings, logo_path_optional=None))
        try:
            path = _path_from_qml(value).expanduser().resolve(strict=True)
        except (OSError, ValueError):
            self._set_error("ロゴ画像を読み込めません")
            return False
        if not path.is_file() or path.suffix.casefold() not in _LOGO_SUFFIXES:
            self._set_error("ロゴはPNG、JPEG、GIF、BMP形式を指定してください")
            return False
        return self._replace_settings(replace(settings, logo_path_optional=str(path)))

    @Slot(str, bool, result=bool)
    def setVisibleField(self, field: str, visible: bool) -> bool:
        settings = self._settings
        if settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        if field not in _VALID_VISIBLE_FIELDS:
            self._set_error("未対応の表示項目です")
            return False
        selected = set(settings.visible_fields)
        if visible:
            selected.add(field)
        else:
            selected.discard(field)
        ordered = tuple(row["value"] for row in _VISIBLE_FIELD_OPTIONS if row["value"] in selected)
        return self._replace_settings(replace(settings, visible_fields=ordered))

    @Slot(str, result=bool)
    def setDefaultOutputDirectory(self, value: str) -> bool:
        settings = self._settings
        if settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        if not value.strip():
            changed = replace(settings, default_output_directory_optional=None)
        else:
            try:
                directory = _path_from_qml(value).expanduser().resolve(strict=False)
            except ValueError as exc:
                self._set_error(str(exc))
                return False
            changed = replace(
                settings,
                default_output_directory_optional=str(directory),
            )
        if not self._replace_settings(changed):
            return False
        self._set_suggested_destination(reset_directory=True)
        self.outputStateChanged.emit()
        return True

    @Slot(result=bool)
    def saveSettings(self) -> bool:
        settings = self._settings
        if settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        if self._is_busy:
            self._set_error("出力処理中は設定を保存できません")
            return False
        try:
            settings.validate()
            saved = self._service.save_settings(settings)
        except (
            OutputServiceError,
            OutputSettingsValidationError,
            ProjectFileError,
        ) as exc:
            logger.warning("出力設定を保存できませんでした（%s）", type(exc).__name__)
            self._set_error(str(exc))
            return False
        except Exception as exc:
            logger.exception(
                "出力設定の保存で予期しないエラーが発生しました（%s）",
                type(exc).__name__,
                exc_info=(
                    type(exc),
                    RuntimeError("例外の詳細値は安全のため省略しました"),
                    exc.__traceback__,
                ),
            )
            self._set_error("出力設定を保存できませんでした。ローカルログを確認してください")
            return False
        self._settings = saved
        self._saved_settings = saved
        self._settings_dirty = False
        self.settingsChanged.emit()
        self._set_status("出力設定をプロジェクトへ保存しました")
        return True

    @Slot(result=bool)
    def resetSettings(self) -> bool:
        if self._saved_settings is None:
            self._set_error("元に戻す出力設定がありません")
            return False
        self._settings = self._saved_settings
        self._settings_dirty = False
        self.clearPreview()
        self.settingsChanged.emit()
        self._set_suggested_destination(reset_directory=True)
        self.outputStateChanged.emit()
        self._set_status("未保存の出力設定を元に戻しました")
        return True

    # Selection actions

    @Slot(str, bool, result=bool)
    def setDateSelected(self, value: str, selected: bool) -> bool:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            self._set_error("出力対象日が不正です")
            return False
        valid = (
            {row.value for row in self._workspace.dates} if self._workspace is not None else set()
        )
        return self._set_selected(self._selected_dates, parsed, selected, valid, "日付")

    @Slot(int, bool, result=bool)
    def setTeacherSelected(self, teacher_id: int, selected: bool) -> bool:
        valid = (
            {row.id for row in self._workspace.teachers} if self._workspace is not None else set()
        )
        return self._set_selected(
            self._selected_teacher_ids,
            teacher_id,
            selected,
            valid,
            "講師",
        )

    @Slot(int, bool, result=bool)
    def setStudentSelected(self, student_id: int, selected: bool) -> bool:
        valid = (
            {row.id for row in self._workspace.students} if self._workspace is not None else set()
        )
        return self._set_selected(
            self._selected_student_ids,
            student_id,
            selected,
            valid,
            "生徒",
        )

    @Slot()
    def selectAllDates(self) -> None:
        if self._workspace is None:
            return
        self._selected_dates = {row.value for row in self._workspace.dates}
        self.clearPreview()
        self.selectionChanged.emit()

    @Slot()
    def selectAllTeachers(self) -> None:
        if self._workspace is None:
            return
        self._selected_teacher_ids = {row.id for row in self._workspace.teachers}
        self.clearPreview()
        self.selectionChanged.emit()

    @Slot()
    def selectAllStudents(self) -> None:
        if self._workspace is None:
            return
        self._selected_student_ids = {row.id for row in self._workspace.students}
        self.clearPreview()
        self.selectionChanged.emit()

    @Slot()
    def clearMessages(self) -> None:
        self._clear_messages()

    # Worker callbacks

    @Slot(object)
    def _on_workspace_loaded(self, value: object) -> None:
        if self._completion_handled:
            return
        if not isinstance(value, OutputWorkspaceDto):
            self._on_job_failed(
                _OutputFailure(
                    message=(
                        "出力データの読込み結果を確認できませんでした。"
                        "ローカルログを確認してください"
                    ),
                    exception_type="InvalidWorkspaceResult",
                    overwrite_required=False,
                )
            )
            return
        self._completion_handled = True
        self._apply_workspace(value)

    @Slot(object)
    def _on_job_completed(self, value: object) -> None:
        if self._completion_handled:
            return
        if not isinstance(value, OutputResultDto):
            self._on_job_failed(
                _OutputFailure(
                    message=(
                        "出力処理の結果を確認できませんでした。ローカルログを確認してください"
                    ),
                    exception_type="InvalidWorkerResult",
                    overwrite_required=False,
                )
            )
            return
        job = self._active_job
        if job is None:
            self._on_job_failed(
                _OutputFailure(
                    message=(
                        "出力処理の状態を確認できませんでした。ローカルログを確認してください"
                    ),
                    exception_type="MissingOutputJob",
                    overwrite_required=False,
                )
            )
            return
        self._completion_handled = True
        if job.is_preview:
            self._preview_path = value.path.resolve(strict=False)
            self._preview_files.add(self._preview_path)
            self._preview_page_count = value.page_count_optional or 0
            self.previewChanged.emit()
            self._set_status(f"印刷プレビューを生成しました（{self._preview_page_count}ページ）")
            return
        self._last_output_path = value.path.resolve(strict=False)
        page_text = (
            f"、{value.page_count_optional}ページ" if value.page_count_optional is not None else ""
        )
        self._last_result_summary = f"{value.record_count}件{page_text}／{value.format.upper()}"
        self._set_status(f"出力ファイルを保存しました: {value.path.name}")
        self.outputStateChanged.emit()
        self.outputGenerated.emit(str(value.path))

    @Slot(object)
    def _on_job_failed(self, value: object) -> None:
        if self._completion_handled:
            return
        self._completion_handled = True
        failure = (
            value
            if isinstance(value, _OutputFailure)
            else _OutputFailure(
                message="出力を完了できませんでした。ローカルログを確認してください",
                exception_type="InvalidWorkerFailure",
                overwrite_required=False,
            )
        )
        logger.error("出力workerで処理を完了できませんでした（%s）", failure.exception_type)
        self._set_error(failure.message)
        if failure.overwrite_required and self._destination is not None:
            self._overwrite_required = True
            self.overwriteConfirmationRequested.emit(self._destination.name)
        self.outputStateChanged.emit()

    @Slot()
    def _on_thread_finished(self) -> None:
        if not self._completion_handled:
            self._on_job_failed(
                _OutputFailure(
                    message="出力を完了できませんでした。ローカルログを確認してください",
                    exception_type="WorkerFinishedWithoutResult",
                    overwrite_required=False,
                )
            )
        finished_job = self._active_job
        self._is_busy = False
        self._busy_text = ""
        self._active_job = None
        thread = self._thread
        self._thread = None
        self._worker = None
        self.outputStateChanged.emit()
        if (
            finished_job is not None
            and finished_job.is_preview
            and self._preview_path != finished_job.destination
        ):
            QTimer.singleShot(0, self._cleanup_inactive_preview_files)
        if thread is not None:
            thread.deleteLater()
        if self._project_refresh_pending and not self._shutdown_requested:
            QTimer.singleShot(0, self.refreshProjectState)

    # Internal helpers

    def _start_job(self, job: _OutputJob, busy_text: str) -> bool:
        if self._is_busy or self._thread is not None:
            self._set_error("別の出力処理が実行中です")
            return False
        self._clear_messages()
        self._completion_handled = False
        self._shutdown_requested = False
        self._active_job = job
        self._is_busy = True
        self._busy_text = busy_text
        self.outputStateChanged.emit()

        thread = QThread(self)
        worker = _OutputWorker(self._service, job)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_job_completed)
        worker.failed.connect(self._on_job_failed)
        worker.done.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def _start_workspace_load(self) -> bool:
        if self._is_busy or self._thread is not None:
            self._set_error("別の出力処理が実行中です")
            return False
        self._clear_messages()
        self._completion_handled = False
        self._shutdown_requested = False
        self._active_job = None
        self._is_busy = True
        self._busy_text = "現在の時間割と警告を再検査しています"
        self.outputStateChanged.emit()

        thread = QThread(self)
        worker = _WorkspaceWorker(self._service)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_workspace_loaded)
        worker.failed.connect(self._on_job_failed)
        worker.done.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def _apply_workspace(self, workspace: OutputWorkspaceDto) -> None:
        self._workspace = workspace
        self._settings = workspace.settings
        self._saved_settings = workspace.settings
        self._settings_dirty = False
        self._selected_dates = {row.value for row in workspace.dates}
        self._selected_teacher_ids = {row.id for row in workspace.teachers}
        self._selected_student_ids = {row.id for row in workspace.students}
        self._set_suggested_destination(reset_directory=True)
        self.workspaceChanged.emit()
        self.settingsChanged.emit()
        self.selectionChanged.emit()
        self.outputStateChanged.emit()
        self._set_status(
            f"出力データを確認しました（個別{workspace.assignment_count}件、"
            f"集団{workspace.group_lesson_count}件）"
        )

    def _ensure_ready_for_generation(self) -> bool:
        if self._is_busy or self._thread is not None:
            self._set_error("別の出力処理が実行中です")
            return False
        if self._projects.current is None or self._workspace is None:
            self._set_error("出力データを先に読込みしてください")
            return False
        if self._settings is None:
            self._set_error("出力設定が読み込まれていません")
            return False
        return True

    def _selection(self) -> OutputSelection:
        workspace = self._workspace
        if workspace is None:
            raise ValueError("出力データが読み込まれていません")
        if workspace.dates and not self._selected_dates:
            raise ValueError("出力対象日を1日以上選択してください")
        if workspace.teachers and not self._selected_teacher_ids:
            raise ValueError("出力対象講師を1名以上選択してください")
        if workspace.students and not self._selected_student_ids:
            raise ValueError("出力対象生徒を1名以上選択してください")
        all_dates = {row.value for row in workspace.dates}
        all_teachers = {row.id for row in workspace.teachers}
        all_students = {row.id for row in workspace.students}
        return OutputSelection(
            dates=(
                () if self._selected_dates == all_dates else tuple(sorted(self._selected_dates))
            ),
            teacher_ids=(
                ()
                if self._selected_teacher_ids == all_teachers
                else tuple(sorted(self._selected_teacher_ids))
            ),
            student_ids=(
                ()
                if self._selected_student_ids == all_students
                else tuple(sorted(self._selected_student_ids))
            ),
        )

    def _replace_settings(self, changed: OutputSettings) -> bool:
        try:
            changed.validate()
        except OutputSettingsValidationError as exc:
            self._set_error(str(exc))
            return False
        self._settings = changed
        self._settings_dirty = changed != self._saved_settings
        self.clearPreview()
        self.settingsChanged.emit()
        self._clear_messages()
        return True

    def _set_selected(
        self,
        target: set[_SelectionValue],
        value: _SelectionValue,
        selected: bool,
        valid: set[_SelectionValue],
        label: str,
    ) -> bool:
        if value not in valid:
            self._set_error(f"選択した{label}が見つかりません")
            return False
        if selected:
            target.add(value)
        else:
            target.discard(value)
            if valid and not target:
                target.add(value)
                self._set_error(f"出力対象{label}を1件以上選択してください")
                self.selectionChanged.emit()
                return False
        self.clearPreview()
        self.selectionChanged.emit()
        return True

    def _set_suggested_destination(self, *, reset_directory: bool) -> None:
        if self._workspace is None or self._settings is None:
            return
        directory = self._output_directory(reset=reset_directory)
        try:
            file_name = self._service.suggested_filename(
                self._report_kind,
                self._output_format,
                settings_override=self._settings,
            )
        except (OutputServiceError, OutputSettingsValidationError, KeyError, ValueError):
            file_name = f"出力.{self._output_format}"
        self._destination = directory / file_name

    def _output_directory(self, *, reset: bool) -> Path:
        if not reset and self._destination is not None:
            return self._destination.parent
        if self._settings is not None:
            configured = self._settings.default_output_directory_optional
            if configured:
                return Path(configured).expanduser()
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        return Path(documents) if documents else Path.cwd()

    def _new_preview_path(self) -> Path:
        if self._preview_directory is None:
            self._preview_directory = TemporaryDirectory(
                prefix="summer_scheduler_preview_",
                ignore_cleanup_errors=True,
            )
        path = Path(self._preview_directory.name) / f"preview-{uuid4().hex}.pdf"
        self._preview_files.add(path)
        return path

    def _cleanup_inactive_preview_files(self) -> None:
        active = self._preview_path
        pending = (
            self._active_job.destination
            if self._active_job is not None and self._active_job.is_preview
            else None
        )
        for path in tuple(self._preview_files):
            if path in {active, pending}:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                logger.warning(
                    "一時PDFを削除できませんでした（ファイル名は記録しません）",
                    exc_info=(
                        type(cleanup_exc),
                        OSError("例外の詳細値は安全のため省略しました"),
                        cleanup_exc.__traceback__,
                    ),
                )
            else:
                self._preview_files.discard(path)

    def _cleanup_preview_directory(self) -> None:
        self._cleanup_inactive_preview_files()
        temporary = self._preview_directory
        self._preview_directory = None
        self._preview_files.clear()
        if temporary is not None:
            temporary.cleanup()

    def _reset_workspace(self) -> None:
        self._workspace = None
        self._settings = None
        self._saved_settings = None
        self._settings_dirty = False
        self._selected_dates.clear()
        self._selected_teacher_ids.clear()
        self._selected_student_ids.clear()
        self._destination = None
        self._overwrite_required = False
        self._last_output_path = None
        self._last_result_summary = ""
        self.clearPreview()

    def _clear_messages(self) -> None:
        if not self._status_message and not self._error_message:
            return
        self._status_message = ""
        self._error_message = ""
        self.messageChanged.emit()

    def _set_status(self, message: str) -> None:
        self._status_message = message
        self._error_message = ""
        self.messageChanged.emit()

    def _set_error(self, message: str) -> None:
        self._status_message = ""
        self._error_message = message
        self.messageChanged.emit()


def _failure_from_exception(exc: Exception) -> _OutputFailure:
    known = _is_expected_output_error(exc)
    return _OutputFailure(
        message=(
            str(exc) if known else "出力を完了できませんでした。ローカルログを確認してください"
        ),
        exception_type=type(exc).__name__,
        overwrite_required=isinstance(exc, OutputDestinationExistsError),
    )


def _is_expected_output_error(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            OutputServiceError,
            OutputExportError,
            OutputSettingsValidationError,
            ProjectFileError,
        ),
    )


def _path_from_qml(value: str) -> Path:
    stripped = value.strip()
    if not stripped:
        raise ValueError("ファイルの保存先を選択してください")
    url = QUrl(stripped)
    if url.isLocalFile():
        local_path = url.toLocalFile()
        if local_path:
            return Path(local_path)
    return Path(stripped)


def _path_with_extension(path: Path, output_format: OutputFormat) -> Path:
    suffix = f".{output_format}"
    if path.suffix.casefold() == suffix:
        return path
    if path.suffix:
        return path.with_suffix(suffix)
    return Path(f"{path}{suffix}")


__all__ = ["OutputViewModel"]
