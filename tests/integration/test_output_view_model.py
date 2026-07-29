"""Phase 6出力ViewModelの非同期処理・設定・一時PDF境界テスト。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QThread

from summer_scheduler.application.output_service import OutputService
from summer_scheduler.application.phase6_dto import (
    OutputDateOptionDto,
    OutputPersonOptionDto,
    OutputResultDto,
    OutputWorkspaceDto,
)
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.infrastructure.exporting import OutputDestinationExistsError
from summer_scheduler.reporting.builder import ReportKind
from summer_scheduler.reporting.data import OutputSelection
from summer_scheduler.reporting.settings import OutputSettings
from summer_scheduler.ui.viewmodels.output_view_model import OutputViewModel

DAY_1 = date(2026, 8, 1)
DAY_2 = date(2026, 8, 2)


@pytest.fixture(scope="module")
def core_app(qt_gui_app: QCoreApplication) -> QCoreApplication:
    return qt_gui_app


def test_workspace_load_runs_off_ui_thread_and_maps_all_options(
    core_app: QCoreApplication,
) -> None:
    service = _FakeOutputService(_workspace())
    service.block_load = True
    projects = _FakeProjects()
    view_model = _view_model(service, projects)
    try:
        assert view_model.refreshWorkspace()
        assert service.load_started.wait(1)
        assert view_model._get_is_busy()
        with pytest.raises(ProjectFileError, match="生成中|出力"):
            view_model.ensure_project_switch_allowed()

        service.load_release.set()
        _wait_until(core_app, lambda: not view_model._get_is_busy())

        assert service.load_thread != core_app.thread()
        assert view_model._get_workspace_loaded()
        assert view_model._get_project_title() == "架空校 夏期講習"
        assert view_model._get_assignment_count() == 12
        assert len(view_model._get_date_options()) == 2
        assert len(view_model._get_teacher_options()) == 2
        assert len(view_model._get_student_options()) == 2
        assert all(bool(row["selected"]) for row in view_model._get_date_options())
        assert view_model._get_destination_path().endswith("全体時間割.xlsx")
    finally:
        service.load_release.set()
        view_model.shutdown()


def test_settings_include_campus_logo_visible_fields_and_explicit_default_directory(
    core_app: QCoreApplication,
    tmp_path: Path,
) -> None:
    service = _FakeOutputService(_workspace())
    view_model = _view_model(service, _FakeProjects())
    try:
        assert view_model.refreshWorkspace()
        _wait_until(core_app, lambda: not view_model._get_is_busy())
        logo = tmp_path / "校舎ロゴ.png"
        logo.write_bytes(b"not-real-image-but-local")
        explicit_directory = tmp_path / "明示した既定出力先"

        assert view_model.setPaperSize("A4")
        assert view_model.setOrientation("portrait")
        assert view_model.setDaysPerPage(1)
        assert view_model.setTeacherColumnsPerPage(4)
        assert view_model.setFontSize(9.5)
        assert view_model.setMarginMm(12.5)
        assert view_model.setStudentPageMode("combined")
        assert view_model.setCsvWithBom(False)
        assert view_model.setFileNamePattern("{project}_{report}_{date}")
        assert view_model.setLogoPath(str(logo))
        assert view_model.setVisibleField("note", False)
        assert view_model.setDefaultOutputDirectory(str(explicit_directory))
        assert view_model.setStyleRule(
            "warning",
            "[要確認]",
            "#FFCCDD",
            "#112233",
        )
        assert view_model.setDestination(str(tmp_path / "別の一時保存先" / "任意.xlsx"))

        assert view_model._get_settings_dirty()
        assert view_model._get_logo_path() == str(logo.resolve())
        visible = {
            str(row["value"]): bool(row["selected"])
            for row in view_model._get_visible_field_options()
        }
        assert visible["note"] is False
        assert visible["subject"] is True
        with pytest.raises(ProjectFileError, match="未保存の出力設定"):
            view_model.ensure_project_switch_allowed()
        assert not view_model.refreshWorkspace()
        assert view_model._get_settings_dirty()
        view_model.refreshProjectState()
        assert view_model._get_settings_dirty()
        assert view_model._get_logo_path() == str(logo.resolve())

        assert view_model.saveSettings()
        saved = service.saved_settings
        assert saved is not None
        assert saved.logo_path_optional == str(logo.resolve())
        assert "note" not in saved.visible_fields
        assert saved.default_output_directory_optional == str(explicit_directory.resolve())
        assert saved.style("warning").marker == "[要確認]"
        assert saved.style("warning").fill_color == "#FFCCDD"
        assert view_model._get_settings_dirty() is False
        view_model.ensure_project_switch_allowed()
    finally:
        view_model.shutdown()


def test_overwrite_confirmation_selection_and_busy_project_guard(
    core_app: QCoreApplication,
    tmp_path: Path,
) -> None:
    service = _FakeOutputService(_workspace())
    view_model = _view_model(service, _FakeProjects())
    confirmations: list[str] = []
    generated: list[str] = []
    view_model.overwriteConfirmationRequested.connect(confirmations.append)
    view_model.outputGenerated.connect(generated.append)
    try:
        assert view_model.refreshWorkspace()
        _wait_until(core_app, lambda: not view_model._get_is_busy())
        assert view_model.setTeacherSelected(10, False)
        assert view_model.setStudentSelected(100, False)

        target = tmp_path / "日本語出力" / "時間割.xlsx"
        target.parent.mkdir(parents=True)
        target.write_text("original", encoding="utf-8")
        assert view_model.setDestination(str(target))

        assert not view_model.generateOutput(False)
        assert confirmations == ["時間割.xlsx"]
        assert view_model._get_overwrite_required()
        assert target.read_text(encoding="utf-8") == "original"

        service.block_export = True
        assert view_model.generateOutput(True)
        assert service.export_started.wait(1)
        assert view_model._get_is_busy()
        with pytest.raises(ProjectFileError, match="生成中|出力"):
            view_model.ensure_project_switch_allowed()
        service.export_release.set()
        _wait_until(core_app, lambda: not view_model._get_is_busy())

        assert target.read_text(encoding="utf-8") == "generated-xlsx"
        assert generated == [str(target)]
        call = service.export_calls[-1]
        assert call.selection.dates == ()
        assert call.selection.teacher_ids == (20,)
        assert call.selection.student_ids == (200,)
        assert call.overwrite is True
        assert service.export_thread != core_app.thread()
        view_model.ensure_project_switch_allowed()
    finally:
        service.export_release.set()
        view_model.shutdown()


def test_project_refresh_during_export_is_deferred_until_worker_releases_service(
    core_app: QCoreApplication,
    tmp_path: Path,
) -> None:
    service = _FakeOutputService(_workspace())
    view_model = _view_model(service, _FakeProjects())
    try:
        assert view_model.refreshWorkspace()
        _wait_until(core_app, lambda: not view_model._get_is_busy())
        baseline_invalidations = service.invalidate_count
        service.block_export = True
        target = tmp_path / "匿名出力.xlsx"
        assert view_model.setDestination(str(target))
        assert view_model.generateOutput(False)
        assert service.export_started.wait(1)

        started = time.monotonic()
        view_model.refreshProjectState()
        elapsed = time.monotonic() - started

        assert elapsed < 0.1
        assert service.invalidate_count == baseline_invalidations
        assert view_model._get_workspace_loaded()

        service.export_release.set()
        _wait_until(core_app, lambda: not view_model._get_is_busy())
        _wait_until(
            core_app,
            lambda: service.invalidate_count == baseline_invalidations + 1,
        )
        assert not view_model._get_workspace_loaded()
    finally:
        service.export_release.set()
        view_model.shutdown()


def test_preview_is_invalidated_by_draft_change_and_temp_files_are_cleaned(
    core_app: QCoreApplication,
) -> None:
    service = _FakeOutputService(_workspace())
    view_model = _view_model(service, _FakeProjects())
    try:
        assert view_model.refreshWorkspace()
        _wait_until(core_app, lambda: not view_model._get_is_busy())

        assert view_model.generatePreview()
        _wait_until(core_app, lambda: not view_model._get_is_busy())
        first_preview = Path(view_model._get_preview_url().toLocalFile())
        preview_directory = first_preview.parent
        assert first_preview.is_file()
        assert view_model._get_has_preview()
        assert view_model._get_preview_page_count() == 3

        assert view_model.setPaperSize("A4")
        assert view_model._get_has_preview() is False
        _wait_until(core_app, lambda: not first_preview.exists())

        assert view_model.generatePreview()
        _wait_until(core_app, lambda: not view_model._get_is_busy())
        second_preview = Path(view_model._get_preview_url().toLocalFile())
        assert second_preview.is_file()
        assert view_model.resetSettings()
        _wait_until(core_app, lambda: not second_preview.exists())

        assert view_model.generatePreview()
        _wait_until(core_app, lambda: not view_model._get_is_busy())
        final_preview = Path(view_model._get_preview_url().toLocalFile())
        assert final_preview.is_file()
        view_model.shutdown()
        assert not final_preview.exists()
        assert not preview_directory.exists()
    finally:
        view_model.shutdown()


def test_preview_cleanup_failure_is_warned_without_logging_sensitive_path(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    view_model = _view_model(_FakeOutputService(_workspace()), _FakeProjects())
    sensitive = tmp_path / "匿名生徒名を含むプレビュー.pdf"
    sensitive.write_bytes(b"preview")
    view_model._preview_files.add(sensitive)
    original_unlink = Path.unlink

    def locked_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == sensitive:
            raise PermissionError(f"locked preview: {path}")
        original_unlink(path, missing_ok=missing_ok)

    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(Path, "unlink", locked_unlink)
            with caplog.at_level(logging.WARNING):
                view_model._cleanup_inactive_preview_files()
        assert sensitive in view_model._preview_files
        assert "一時PDFを削除できませんでした" in caplog.text
        assert str(sensitive) not in caplog.text
        assert sensitive.name not in caplog.text
    finally:
        view_model.shutdown()


def test_unexpected_settings_save_logs_redacted_traceback(
    core_app: QCoreApplication,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeOutputService(_workspace())
    view_model = _view_model(service, _FakeProjects())
    sensitive = r"C:\Users\person\匿名生徒名\設定.yaml"

    def fail_save(_settings: OutputSettings) -> OutputSettings:
        raise RuntimeError(f"unexpected value at {sensitive}")

    try:
        assert view_model.refreshWorkspace()
        _wait_until(core_app, lambda: not view_model._get_is_busy())
        monkeypatch.setattr(service, "save_settings", fail_save)
        with caplog.at_level(logging.ERROR):
            assert not view_model.saveSettings()
        assert "予期しないエラー" in caplog.text
        assert "Traceback" in caplog.text
        assert sensitive not in caplog.text
        assert "匿名生徒名" not in caplog.text
    finally:
        view_model.shutdown()


@dataclass(frozen=True, slots=True)
class _ExportCall:
    kind: str
    output_format: str
    destination: Path
    selection: OutputSelection
    settings: OutputSettings
    overwrite: bool


class _FakeProjects:
    def __init__(self) -> None:
        self.current: object | None = _FakeCurrent(project_id=1)


@dataclass(frozen=True, slots=True)
class _FakeCurrent:
    project_id: int


class _FakeOutputService:
    def __init__(self, workspace: OutputWorkspaceDto) -> None:
        self.workspace = workspace
        self.saved_settings: OutputSettings | None = None
        self.export_calls: list[_ExportCall] = []
        self.load_thread: QThread | None = None
        self.export_thread: QThread | None = None
        self.block_load = False
        self.block_export = False
        self.load_started = threading.Event()
        self.load_release = threading.Event()
        self.export_started = threading.Event()
        self.export_release = threading.Event()
        self.load_release.set()
        self.export_release.set()
        self.invalidate_count = 0

    def invalidate(self) -> None:
        self.invalidate_count += 1

    def load_workspace(self, *, refresh: bool = True) -> OutputWorkspaceDto:
        assert refresh
        self.load_thread = QThread.currentThread()
        self.load_started.set()
        if self.block_load:
            assert self.load_release.wait(3)
        return self.workspace

    def suggested_filename(
        self,
        kind: ReportKind | str,
        extension: str,
        *,
        settings_override: OutputSettings | None = None,
    ) -> str:
        del settings_override
        names = {
            "overall": "全体時間割",
            "students": "生徒別時間割",
            "teachers": "講師別時間割",
            "issues": "未配置・警告",
            "raw": "割当て生データ",
        }
        return f"{names[kind]}.{extension}"

    def save_settings(self, settings: OutputSettings) -> OutputSettings:
        self.saved_settings = settings
        self.workspace = OutputWorkspaceDto(
            project_id=self.workspace.project_id,
            project_title=self.workspace.project_title,
            campus_name=self.workspace.campus_name,
            settings=settings,
            dates=self.workspace.dates,
            teachers=self.workspace.teachers,
            students=self.workspace.students,
            assignment_count=self.workspace.assignment_count,
            group_lesson_count=self.workspace.group_lesson_count,
            unassigned_count=self.workspace.unassigned_count,
            warning_count=self.workspace.warning_count,
        )
        return settings

    def export_excel(
        self,
        kind: ReportKind,
        destination: Path,
        selection: OutputSelection,
        *,
        settings_override: OutputSettings | None = None,
        overwrite: bool = False,
    ) -> OutputResultDto:
        assert settings_override is not None
        return self._export(
            kind,
            "xlsx",
            destination,
            selection,
            settings_override,
            overwrite,
            page_count=3,
        )

    def export_pdf(
        self,
        kind: ReportKind,
        destination: Path,
        selection: OutputSelection,
        *,
        settings_override: OutputSettings | None = None,
        overwrite: bool = False,
    ) -> OutputResultDto:
        assert settings_override is not None
        return self._export(
            kind,
            "pdf",
            destination,
            selection,
            settings_override,
            overwrite,
            page_count=3,
        )

    def export_csv(
        self,
        destination: Path,
        selection: OutputSelection,
        *,
        settings_override: OutputSettings | None = None,
        overwrite: bool = False,
    ) -> OutputResultDto:
        assert settings_override is not None
        return self._export(
            "raw",
            "csv",
            destination,
            selection,
            settings_override,
            overwrite,
            page_count=None,
        )

    def _export(
        self,
        kind: str,
        output_format: str,
        destination: Path,
        selection: OutputSelection,
        settings: OutputSettings,
        overwrite: bool,
        *,
        page_count: int | None,
    ) -> OutputResultDto:
        self.export_thread = QThread.currentThread()
        self.export_started.set()
        if self.block_export:
            assert self.export_release.wait(3)
        if destination.exists() and not overwrite:
            raise OutputDestinationExistsError(f"同名のファイルが既にあります: {destination.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f"generated-{output_format}", encoding="utf-8")
        self.export_calls.append(
            _ExportCall(
                kind=kind,
                output_format=output_format,
                destination=destination,
                selection=selection,
                settings=settings,
                overwrite=overwrite,
            )
        )
        return OutputResultDto(
            kind=kind,
            format=output_format,
            path=destination,
            page_count_optional=page_count,
            record_count=12,
        )


def _view_model(
    service: _FakeOutputService,
    projects: _FakeProjects,
) -> OutputViewModel:
    return OutputViewModel(
        cast(OutputService, service),
        cast(ProjectService, projects),
    )


def _workspace() -> OutputWorkspaceDto:
    return OutputWorkspaceDto(
        project_id=1,
        project_title="架空校 夏期講習",
        campus_name="架空みらい校",
        settings=OutputSettings(project_id=1),
        dates=(
            OutputDateOptionDto(DAY_1, "8月1日(土)", True),
            OutputDateOptionDto(DAY_2, "8月2日(日)", True),
        ),
        teachers=(
            OutputPersonOptionDto(10, "架空 講師一", "T-001"),
            OutputPersonOptionDto(20, "架空 講師二", "T-002"),
        ),
        students=(
            OutputPersonOptionDto(100, "架空 生徒一", "中1／S-001"),
            OutputPersonOptionDto(200, "架空 生徒二", "中2／S-002"),
        ),
        assignment_count=12,
        group_lesson_count=2,
        unassigned_count=1,
        warning_count=3,
    )


def _wait_until(
    app: QCoreApplication,
    predicate: object,
    *,
    timeout_seconds: float = 3.0,
) -> None:
    assert callable(predicate)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Qt非同期処理が制限時間内に完了しませんでした")
