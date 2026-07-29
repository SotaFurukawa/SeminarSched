"""OptimizationViewModelのthread・保存・中止境界テスト。"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import date
from datetime import time as wall_time
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QThread

from summer_scheduler.application.optimization_run_service import (
    FinalizedOptimization,
    OptimizationPreparationError,
    OptimizationRunService,
    PreparedOptimization,
)
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    DiagnosticCode,
    DiagnosticReason,
    LessonRequestData,
    ObjectiveBreakdown,
    OptimizationInput,
    OptimizationResult,
    OptimizationSettings,
    ScheduledAssignment,
    SolverStatus,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
    UnassignedLesson,
)
from summer_scheduler.optimization.solver import (
    CancellationToken,
    OptimizationProgress,
    ProgressCallback,
)
from summer_scheduler.ui.viewmodels import optimization_view_model as view_model_module
from summer_scheduler.ui.viewmodels.optimization_view_model import OptimizationViewModel

DAY = date(2026, 8, 3)


@pytest.fixture(scope="module")
def core_app(qt_gui_app: QCoreApplication) -> Iterator[QCoreApplication]:
    yield qt_gui_app
    qt_gui_app.processEvents()


def test_solver_runs_only_on_worker_and_finalize_returns_to_ui_thread(
    core_app: QCoreApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeOptimizationService(_prepared(tmp_path))
    projects = _FakeProjects()
    worker_thread: list[QThread] = []

    def solve(
        data: OptimizationInput,
        *,
        cancellation: CancellationToken | None = None,
        progress: ProgressCallback | None = None,
    ) -> OptimizationResult:
        worker_thread.append(QThread.currentThread())
        assert data is service.prepared.input
        assert cancellation is not None
        if progress is not None:
            progress(
                OptimizationProgress(
                    stage_index=1,
                    stage_count=5,
                    stage_name="unassigned_count",
                    solver_status="FEASIBLE",
                    elapsed_seconds=0.25,
                    objective_value=1,
                )
            )
        return _result()

    monkeypatch.setattr(view_model_module, "solve_optimization", solve)
    view_model = _view_model(service, projects, tmp_path)

    assert view_model._get_default_preset() == "fast"
    assert view_model.runOptimization("fast")
    _wait_until(core_app, lambda: not view_model._get_is_running())

    assert worker_thread
    assert worker_thread[0] != core_app.thread()
    assert service.prepare_thread == core_app.thread()
    assert service.finalize_thread == core_app.thread()
    assert view_model._get_solver_status() == "OPTIMAL"
    assert view_model._get_assigned_count() == 1
    assert view_model._get_unassigned_count() == 1
    assert view_model._get_objective_breakdown()["activeTeacherSlotCount"] == 1
    assert view_model._get_unassigned_lessons()[0]["reasonText"] == "候補なし"
    assert view_model._get_status_message().startswith("時間割を保存しました")
    assert view_model._get_log_path() == str(service.prepared.log_path)
    assert service.log_directory == service.prepared.log_directory
    view_model.shutdown()


def test_cancel_uses_token_marks_run_and_blocks_project_switch(
    core_app: QCoreApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeOptimizationService(_prepared(tmp_path))
    projects = _FakeProjects()
    started = threading.Event()

    def solve(
        data: OptimizationInput,
        *,
        cancellation: CancellationToken | None = None,
        progress: ProgressCallback | None = None,
    ) -> OptimizationResult:
        del data, progress
        assert cancellation is not None
        started.set()
        while not cancellation.is_cancelled:
            time.sleep(0.005)
        return replace(
            _result(),
            assignments=(),
            solver_status="FEASIBLE",
            cancelled=True,
        )

    monkeypatch.setattr(view_model_module, "solve_optimization", solve)
    view_model = _view_model(service, projects, tmp_path)

    assert view_model.runOptimization("standard")
    assert started.wait(1)
    with pytest.raises(ProjectFileError, match="実行中"):
        view_model.ensure_project_switch_allowed()
    view_model.cancelOptimization()
    _wait_until(core_app, lambda: not view_model._get_is_running())

    assert service.cancelled_thread == core_app.thread()
    assert service.finalize_thread is None
    assert view_model._get_status_message().startswith("最適化を中止しました")
    view_model.ensure_project_switch_allowed()
    view_model.shutdown()


def test_shutdown_requests_cancel_and_waits_without_terminate(
    core_app: QCoreApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _FakeOptimizationService(_prepared(tmp_path))
    started = threading.Event()
    stopped = threading.Event()

    def solve(
        data: OptimizationInput,
        *,
        cancellation: CancellationToken | None = None,
        progress: ProgressCallback | None = None,
    ) -> OptimizationResult:
        del data, progress
        assert cancellation is not None
        started.set()
        while not cancellation.is_cancelled:
            time.sleep(0.005)
        stopped.set()
        return replace(_result(), assignments=(), cancelled=True)

    monkeypatch.setattr(view_model_module, "solve_optimization", solve)
    view_model = _view_model(service, _FakeProjects(), tmp_path)
    assert view_model.runOptimization("fast")
    assert started.wait(1)

    view_model.shutdown()
    _wait_until(core_app, lambda: not view_model._get_is_running())

    assert stopped.is_set()
    assert service.cancelled_thread == core_app.thread()


def test_worker_error_log_does_not_include_exception_value(
    core_app: QCoreApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _FakeOptimizationService(_prepared(tmp_path))
    sensitive = r"C:\利用者\個人情報\生徒名"

    def solve(
        data: OptimizationInput,
        *,
        cancellation: CancellationToken | None = None,
        progress: ProgressCallback | None = None,
    ) -> OptimizationResult:
        del data, cancellation, progress
        raise RuntimeError(sensitive)

    monkeypatch.setattr(view_model_module, "solve_optimization", solve)
    view_model = _view_model(service, _FakeProjects(), tmp_path)

    with caplog.at_level(logging.ERROR):
        assert view_model.runOptimization("fast")
        _wait_until(core_app, lambda: not view_model._get_is_running())

    assert "RuntimeError" in caplog.text
    assert sensitive not in caplog.text
    assert service.failed_thread == core_app.thread()
    assert view_model._get_error_message() == (
        "最適化を完了できませんでした。ローカルログを確認してください"
    )
    view_model.shutdown()


def test_prepare_error_log_does_not_include_exception_value(
    core_app: QCoreApplication,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive = "架空生徒・秘密"
    service = _FakeOptimizationService(_prepared(tmp_path))
    service.prepare_error = OptimizationPreparationError(sensitive)
    view_model = _view_model(service, _FakeProjects(), tmp_path)

    with caplog.at_level(logging.WARNING):
        assert not view_model.runOptimization("fast")

    assert sensitive not in caplog.text
    assert "OptimizationPreparationError" in caplog.text
    assert view_model._get_error_message() == sensitive
    core_app.processEvents()


def test_invalid_preset_and_missing_project_are_rejected(
    tmp_path: Path,
) -> None:
    service = _FakeOptimizationService(_prepared(tmp_path))
    projects = _FakeProjects()
    view_model = _view_model(service, projects, tmp_path)

    assert not view_model.runOptimization("unlimited")
    assert service.prepare_calls == 0

    projects.current = None
    view_model.refreshProjectState()
    assert not view_model.runOptimization("fast")
    assert view_model._get_has_open_project() is False


def test_prepare_stage_names_are_localized(
    tmp_path: Path,
) -> None:
    service = _FakeOptimizationService(_prepared(tmp_path))
    view_model = _view_model(service, _FakeProjects(), tmp_path)
    view_model._is_running = True

    view_model._on_progress(
        OptimizationProgress(
            stage_index=0,
            stage_count=5,
            stage_name="candidate_generation",
            solver_status=None,
            elapsed_seconds=0.1,
        )
    )
    assert view_model._get_stage() == "候補生成"

    view_model._on_progress(
        OptimizationProgress(
            stage_index=0,
            stage_count=5,
            stage_name="model_build",
            solver_status=None,
            elapsed_seconds=0.2,
        )
    )
    assert view_model._get_stage() == "モデル構築"
    view_model._is_running = False


class _FakeProjects:
    def __init__(self) -> None:
        self.current: object | None = object()


class _FakeOptimizationService:
    default_preset = "fast"

    def __init__(self, prepared: PreparedOptimization) -> None:
        self.prepared = prepared
        self.prepare_error: Exception | None = None
        self.prepare_calls = 0
        self.prepare_thread: QThread | None = None
        self.finalize_thread: QThread | None = None
        self.cancelled_thread: QThread | None = None
        self.failed_thread: QThread | None = None
        self.log_directory: Path | None = None

    def prepare(
        self,
        preset: str,
        *,
        log_directory: Path,
    ) -> PreparedOptimization:
        assert preset in {"fast", "standard", "high_quality"}
        self.log_directory = log_directory
        self.prepare_calls += 1
        self.prepare_thread = QThread.currentThread()
        if self.prepare_error is not None:
            raise self.prepare_error
        return self.prepared

    def finalize(
        self,
        prepared: PreparedOptimization,
        result: OptimizationResult,
    ) -> FinalizedOptimization:
        assert prepared is self.prepared
        self.finalize_thread = QThread.currentThread()
        return FinalizedOptimization(
            optimization_run_id=prepared.optimization_run_id,
            assignment_count=len(result.assignments),
            unassigned_count=len(result.unassigned_lessons),
            warning_count=len(result.warnings),
        )

    def mark_cancelled(
        self,
        prepared: PreparedOptimization,
        *,
        solver_status: SolverStatus = "UNKNOWN",
        elapsed_seconds: float | None = None,
        assignment_count: int | None = None,
        unassigned_count: int | None = None,
        warning_count: int | None = None,
    ) -> None:
        del (
            solver_status,
            elapsed_seconds,
            assignment_count,
            unassigned_count,
            warning_count,
        )
        assert prepared is self.prepared
        self.cancelled_thread = QThread.currentThread()

    def mark_failed(
        self,
        prepared: PreparedOptimization,
        *,
        solver_status: SolverStatus = "UNKNOWN",
        elapsed_seconds: float | None = None,
        assignment_count: int | None = None,
        unassigned_count: int | None = None,
        warning_count: int | None = None,
    ) -> None:
        del (
            solver_status,
            elapsed_seconds,
            assignment_count,
            unassigned_count,
            warning_count,
        )
        assert prepared is self.prepared
        self.failed_thread = QThread.currentThread()


def _view_model(
    service: _FakeOptimizationService,
    projects: _FakeProjects,
    tmp_path: Path,
) -> OptimizationViewModel:
    return OptimizationViewModel(
        cast(OptimizationRunService, service),
        cast(ProjectService, projects),
        tmp_path / "ログ" / "summer_scheduler.log",
    )


def _prepared(tmp_path: Path) -> PreparedOptimization:
    return PreparedOptimization(
        optimization_run_id=1,
        project_id=1,
        project_path=tmp_path / "架空.jukuschedule",
        preset="fast",
        input=_input(),
        input_fingerprint="fingerprint",
        log_directory=tmp_path / "ログ" / "optimization-runs",
        log_path=(tmp_path / "ログ" / "optimization-runs" / "optimization-run-test.log"),
    )


def _input() -> OptimizationInput:
    slot = TimeSlotData(
        id=100,
        code="Y",
        display_name="Yコマ",
        start_time=wall_time(14, 10),
        end_time=wall_time(15, 30),
        sort_order=1,
    )
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY,),
        time_slots=(slot,),
        students=(StudentData(1, "架空生徒"),),
        teachers=(TeacherData(10, "架空講師", frozenset({500})),),
        subjects=(SubjectData(500, "JH_MATH", "中学校・数学"),),
        lesson_requests=(LessonRequestData(1000, 1, 500, 2),),
        availabilities=(
            AvailabilityData("student", 1, DAY, slot.id, 1),
            AvailabilityData("teacher", 10, DAY, slot.id, 1),
        ),
        group_blocks=(),
        existing_assignments=(),
        settings=OptimizationSettings(
            time_limit_seconds=30,
            random_seed=7,
            num_search_workers=1,
            regular_teacher_priority_weights=(1, 2, 3, 4),
            preferred_teacher_rank_weights=(3, 2, 1),
            student_preferred_time_weight=2,
            teacher_preferred_time_weight=1,
            preserve_existing_assignment_weight=3,
        ),
    )


def _result() -> OptimizationResult:
    reason = DiagnosticReason(
        code=DiagnosticCode.NO_CANDIDATE,
        message="候補なし",
    )
    return OptimizationResult(
        solver_status="OPTIMAL",
        assignments=(
            ScheduledAssignment(
                lesson_request_id=1000,
                session_index=1,
                student_id=1,
                subject_id=500,
                teacher_id=10,
                day=DAY,
                time_slot_id=100,
            ),
        ),
        unassigned_lessons=(
            UnassignedLesson(
                lesson_request_id=1000,
                session_index=2,
                student_id=1,
                subject_id=500,
                reasons=(reason,),
            ),
        ),
        objective_breakdown=ObjectiveBreakdown(
            unassigned_count=1,
            teacher_preference_penalty=2,
            active_teacher_slot_count=1,
            availability_preference_score=3,
            changed_assignment_count=0,
        ),
        elapsed_seconds=0.5,
        warnings=("架空の警告",),
    )


def _wait_until(
    app: QCoreApplication,
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float = 3.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Qt非同期処理が制限時間内に完了しませんでした")
