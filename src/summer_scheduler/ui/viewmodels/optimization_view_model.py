"""Phase 4最適化実行をQMLへ公開する非同期ViewModel。"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QElapsedTimer,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)

from summer_scheduler.application.optimization_run_service import (
    OptimizationRunService,
    OptimizationRunServiceError,
    PreparedOptimization,
)
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.optimization.dto import (
    OptimizationInput,
    OptimizationResult,
    SolverStatus,
)
from summer_scheduler.optimization.solver import (
    CancellationToken,
    OptimizationProgress,
    solve_optimization,
)

logger = logging.getLogger(__name__)

_ALLOWED_PRESETS = frozenset({"fast", "standard", "high_quality"})
_STAGE_LABELS = {
    "candidate_generation": "候補生成",
    "initial_solution": "初期実行可能解の構築",
    "model_build": "モデル構築",
    "unassigned_count": "未配置数の最小化",
    "teacher_preference_penalty": "講師希望の調整",
    "active_teacher_slot_count": "講師稼働枠の最小化",
    "availability_preference_score": "希望日時の調整",
    "changed_assignment_count": "既存時間割の維持",
    "teacher_load_imbalance": "勤務可能枠に対する参加割合の調整",
}


class _OptimizationWorker(QObject):
    """不変入力だけを受け取り、DBへ触れずsolverを実行するworker。"""

    progressed = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    done = Signal()

    def __init__(
        self,
        data: OptimizationInput,
        cancellation: CancellationToken,
    ) -> None:
        super().__init__()
        self._data = data
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        try:
            result = solve_optimization(
                self._data,
                cancellation=self._cancellation,
                progress=self.progressed.emit,
            )
        except Exception as exc:
            # 例外値には入力由来情報が含まれ得るため、型名だけをUI threadへ渡す。
            self.failed.emit(type(exc).__name__)
        else:
            self.completed.emit(result)
        finally:
            self.done.emit()


class OptimizationViewModel(QObject):
    """prepare/保存とsolver workerを分離したPhase 4表示境界。"""

    projectStateChanged = Signal()
    runStateChanged = Signal()
    resultChanged = Signal()
    messageChanged = Signal()
    optimizationSaved = Signal()

    def __init__(
        self,
        service: OptimizationRunService,
        projects: ProjectService,
        log_path: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._projects = projects
        app_log_path = log_path.resolve(strict=False)
        self._log_directory = app_log_path.parent / "optimization-runs"
        self._log_path = self._log_directory
        self._default_preset = service.default_preset

        self._is_running = False
        self._elapsed_seconds = 0.0
        self._solver_status = "未実行"
        self._stage = "待機"
        self._assigned_count = 0
        self._unassigned_count = 0
        self._objective_breakdown = _empty_objective_breakdown()
        self._unassigned_lessons: list[dict[str, object]] = []
        self._warnings: list[str] = []
        self._status_message = ""
        self._error_message = ""

        self._prepared: PreparedOptimization | None = None
        self._cancellation: CancellationToken | None = None
        self._thread: QThread | None = None
        self._worker: _OptimizationWorker | None = None
        self._completion_handled = False
        self._shutdown_requested = False

        self._elapsed_clock = QElapsedTimer()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(250)
        self._elapsed_timer.timeout.connect(self._refresh_elapsed)

    # QML properties

    def _get_has_open_project(self) -> bool:
        return self._projects.current is not None

    hasOpenProject = Property(bool, _get_has_open_project, notify=projectStateChanged)

    def _get_is_running(self) -> bool:
        return self._is_running

    isRunning = Property(bool, _get_is_running, notify=runStateChanged)

    def _get_default_preset(self) -> str:
        return self._default_preset

    defaultPreset = Property(str, _get_default_preset, constant=True)

    def _get_elapsed_seconds(self) -> float:
        return self._elapsed_seconds

    elapsedSeconds = Property(float, _get_elapsed_seconds, notify=runStateChanged)

    def _get_solver_status(self) -> str:
        return self._solver_status

    solverStatus = Property(str, _get_solver_status, notify=runStateChanged)

    def _get_stage(self) -> str:
        return self._stage

    stage = Property(str, _get_stage, notify=runStateChanged)

    def _get_assigned_count(self) -> int:
        return self._assigned_count

    assignedCount = Property(int, _get_assigned_count, notify=resultChanged)

    def _get_unassigned_count(self) -> int:
        return self._unassigned_count

    unassignedCount = Property(int, _get_unassigned_count, notify=resultChanged)

    def _get_objective_breakdown(self) -> dict[str, int]:
        return self._objective_breakdown

    objectiveBreakdown = Property(
        object,
        _get_objective_breakdown,
        notify=resultChanged,
    )

    def _get_unassigned_lessons(self) -> list[dict[str, object]]:
        return self._unassigned_lessons

    unassignedLessons = Property(
        list,
        _get_unassigned_lessons,
        notify=resultChanged,
    )

    def _get_warnings(self) -> list[str]:
        return self._warnings

    warnings = Property(list, _get_warnings, notify=resultChanged)

    def _get_log_path(self) -> str:
        return str(self._log_path)

    logPath = Property(str, _get_log_path, notify=runStateChanged)

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=messageChanged)

    def _get_error_message(self) -> str:
        return self._error_message

    errorMessage = Property(str, _get_error_message, notify=messageChanged)

    # Public lifecycle

    def ensure_project_switch_allowed(self) -> None:
        if self._is_running:
            raise ProjectFileError(
                "最適化の実行中はプロジェクトを切り替えられません。先に中止してください"
            )

    @Slot()
    def refreshProjectState(self) -> None:
        self.projectStateChanged.emit()

    @Slot(str, result=bool)
    def runOptimization(self, preset: str) -> bool:
        if self._is_running or self._thread is not None:
            self._set_error("最適化はすでに実行中です")
            return False
        if preset not in _ALLOWED_PRESETS:
            self._set_error("実行品質は高速・標準・高品質から選択してください")
            return False
        if self._projects.current is None:
            self._set_error("先にプロジェクトを作成または開いてください")
            return False

        self._clear_messages()
        try:
            prepared = self._service.prepare(
                preset,
                log_directory=self._log_directory,
            )
        except (OptimizationRunServiceError, ProjectFileError, ValueError) as exc:
            logger.warning(
                "最適化prepareを完了できませんでした（%s）",
                type(exc).__name__,
            )
            self._set_error(str(exc))
            return False
        except Exception as exc:
            logger.error(
                "最適化prepareで予期しないエラーが発生しました（%s）",
                type(exc).__name__,
            )
            self._set_error("最適化を開始できませんでした。ローカルログを確認してください")
            return False

        self._reset_result()
        self._prepared = prepared
        self._log_path = prepared.log_path
        self._cancellation = CancellationToken()
        self._completion_handled = False
        self._shutdown_requested = False
        self._is_running = True
        self._solver_status = "実行中"
        self._stage = "モデル準備"
        self._elapsed_seconds = 0.0
        self._elapsed_clock.start()
        self._elapsed_timer.start()
        self._set_status("時間割の最適化を開始しました")
        self.runStateChanged.emit()
        self._start_worker(prepared.input, self._cancellation)
        return True

    @Slot()
    def cancelOptimization(self) -> None:
        if not self._is_running or self._cancellation is None:
            return
        self._cancellation.cancel()
        self._set_status("中止を要求しました。安全な停止を待っています")

    @Slot()
    def clearMessages(self) -> None:
        self._clear_messages()

    @Slot()
    def shutdown(self) -> None:
        """アプリ終了時に協調停止し、workerを残したまま破棄しない。"""
        self._shutdown_requested = True
        cancellation = self._cancellation
        if cancellation is not None:
            cancellation.cancel()
        thread = self._thread
        if thread is not None and thread.isRunning():
            if not thread.wait(30_000):
                # 実行中workerの強制破棄は結果を破損し得るため、
                # アプリ終了時も協調停止の完了を優先する。
                logger.warning("最適化workerの協調停止に30秒以上かかっています")
                thread.wait()
        if self._prepared is not None and not self._completion_handled:
            self._mark_cancelled_safely(
                self._prepared,
                solver_status="UNKNOWN",
                elapsed_seconds=self._current_elapsed(),
            )
            self._completion_handled = True

    # Worker callbacks (queued onto the ViewModel/UI thread)

    @Slot(object)
    def _on_progress(self, value: object) -> None:
        if not isinstance(value, OptimizationProgress) or not self._is_running:
            return
        self._elapsed_seconds = max(self._elapsed_seconds, value.elapsed_seconds)
        self._stage = _STAGE_LABELS.get(value.stage_name, value.stage_name)
        if value.solver_status is not None:
            self._solver_status = value.solver_status
        self.runStateChanged.emit()

    @Slot(object)
    def _on_solver_completed(self, value: object) -> None:
        if self._completion_handled:
            return
        if not isinstance(value, OptimizationResult):
            self._handle_worker_failure("InvalidWorkerResult")
            return
        prepared = self._prepared
        if prepared is None:
            self._handle_worker_failure("MissingPreparedOptimization")
            return

        self._completion_handled = True
        self._apply_result(value)
        if value.cancelled:
            self._mark_cancelled_safely(
                prepared,
                solver_status=value.solver_status,
                elapsed_seconds=value.elapsed_seconds,
                assignment_count=len(value.assignments),
                unassigned_count=len(value.unassigned_lessons),
                warning_count=len(value.warnings),
            )
            self._set_status("最適化を中止しました。現在の時間割は変更していません")
            return
        if value.solver_status not in {"OPTIMAL", "FEASIBLE"}:
            self._mark_failed_safely(
                prepared,
                solver_status=value.solver_status,
                elapsed_seconds=value.elapsed_seconds,
                assignment_count=len(value.assignments),
                unassigned_count=len(value.unassigned_lessons),
                warning_count=len(value.warnings),
            )
            self._set_error("実行可能な時間割を取得できませんでした")
            return

        try:
            finalized = self._service.finalize(prepared, value)
        except OptimizationRunServiceError as exc:
            logger.warning(
                "最適化finalizeを完了できませんでした（%s）",
                type(exc).__name__,
            )
            self._set_error(str(exc))
            return
        except Exception as exc:
            logger.error(
                "最適化finalizeで予期しないエラーが発生しました（%s）",
                type(exc).__name__,
            )
            self._mark_failed_safely(
                prepared,
                solver_status=value.solver_status,
                elapsed_seconds=value.elapsed_seconds,
            )
            self._set_error("最適化結果を保存できませんでした。ローカルログを確認してください")
            return

        self._set_status(
            f"時間割を保存しました（配置{finalized.assignment_count}件、"
            f"未配置{finalized.unassigned_count}件）"
        )
        self.optimizationSaved.emit()

    @Slot(str)
    def _on_worker_failed(self, exception_type: str) -> None:
        self._handle_worker_failure(exception_type)

    @Slot()
    def _on_thread_finished(self) -> None:
        if not self._completion_handled and self._prepared is not None:
            self._handle_worker_failure("WorkerFinishedWithoutResult")
        self._elapsed_timer.stop()
        self._elapsed_seconds = self._current_elapsed()
        self._is_running = False
        self._cancellation = None
        self._prepared = None
        thread = self._thread
        self._thread = None
        self._worker = None
        self.runStateChanged.emit()
        if thread is not None:
            thread.deleteLater()

    @Slot()
    def _refresh_elapsed(self) -> None:
        if not self._is_running:
            return
        self._elapsed_seconds = self._current_elapsed()
        self.runStateChanged.emit()

    # Internal helpers

    def _start_worker(
        self,
        data: OptimizationInput,
        cancellation: CancellationToken,
    ) -> None:
        thread = QThread(self)
        worker = _OptimizationWorker(data, cancellation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progressed.connect(self._on_progress)
        worker.completed.connect(self._on_solver_completed)
        worker.failed.connect(self._on_worker_failed)
        # shutdown()がUI threadでwait中でもquitが処理されるよう、worker threadから
        # 直接event loopへ停止要求を届ける。
        worker.done.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _handle_worker_failure(self, exception_type: str) -> None:
        if self._completion_handled:
            return
        self._completion_handled = True
        logger.error(
            "最適化workerで予期しないエラーが発生しました（%s）",
            exception_type,
        )
        if self._prepared is not None:
            self._mark_failed_safely(
                self._prepared,
                solver_status="UNKNOWN",
                elapsed_seconds=self._current_elapsed(),
            )
        self._solver_status = "UNKNOWN"
        self._stage = "異常終了"
        self._set_error("最適化を完了できませんでした。ローカルログを確認してください")

    def _mark_cancelled_safely(
        self,
        prepared: PreparedOptimization,
        *,
        solver_status: SolverStatus,
        elapsed_seconds: float,
        assignment_count: int | None = None,
        unassigned_count: int | None = None,
        warning_count: int | None = None,
    ) -> None:
        try:
            self._service.mark_cancelled(
                prepared,
                solver_status=solver_status,
                elapsed_seconds=elapsed_seconds,
                assignment_count=assignment_count,
                unassigned_count=unassigned_count,
                warning_count=warning_count,
            )
        except Exception as exc:
            logger.error(
                "最適化runのcancelled更新に失敗しました（%s）",
                type(exc).__name__,
            )

    def _mark_failed_safely(
        self,
        prepared: PreparedOptimization,
        *,
        solver_status: SolverStatus,
        elapsed_seconds: float,
        assignment_count: int | None = None,
        unassigned_count: int | None = None,
        warning_count: int | None = None,
    ) -> None:
        try:
            self._service.mark_failed(
                prepared,
                solver_status=solver_status,
                elapsed_seconds=elapsed_seconds,
                assignment_count=assignment_count,
                unassigned_count=unassigned_count,
                warning_count=warning_count,
            )
        except Exception as exc:
            logger.error(
                "最適化runのfailed更新に失敗しました（%s）",
                type(exc).__name__,
            )

    def _apply_result(self, result: OptimizationResult) -> None:
        objective = result.objective_breakdown
        self._solver_status = result.solver_status
        self._stage = "完了" if not result.cancelled else "中止"
        self._elapsed_seconds = max(self._elapsed_seconds, result.elapsed_seconds)
        self._assigned_count = len(result.assignments)
        self._unassigned_count = len(result.unassigned_lessons)
        self._objective_breakdown = {
            "unassignedCount": objective.unassigned_count,
            "teacherPreferencePenalty": objective.teacher_preference_penalty,
            "activeTeacherSlotCount": objective.active_teacher_slot_count,
            "availabilityPreferenceScore": objective.availability_preference_score,
            "changedAssignmentCount": objective.changed_assignment_count,
            "optionalBalanceScore": objective.optional_balance_score,
        }
        self._unassigned_lessons = [
            {
                "lessonRequestId": item.lesson_request_id,
                "sessionIndex": item.session_index,
                "studentId": item.student_id,
                "subjectId": item.subject_id,
                "reasons": [
                    {
                        "code": reason.code.value,
                        "message": reason.message,
                        "excludedCandidateCount": reason.excluded_candidate_count,
                    }
                    for reason in item.reasons
                ],
                "reasonText": " / ".join(reason.message for reason in item.reasons),
            }
            for item in result.unassigned_lessons
        ]
        self._warnings = list(result.warnings)
        self.resultChanged.emit()
        self.runStateChanged.emit()

    def _reset_result(self) -> None:
        self._assigned_count = 0
        self._unassigned_count = 0
        self._objective_breakdown = _empty_objective_breakdown()
        self._unassigned_lessons = []
        self._warnings = []
        self.resultChanged.emit()

    def _current_elapsed(self) -> float:
        if not self._elapsed_clock.isValid():
            return self._elapsed_seconds
        return max(self._elapsed_seconds, self._elapsed_clock.elapsed() / 1000.0)

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


def _empty_objective_breakdown() -> dict[str, int]:
    return {
        "unassignedCount": 0,
        "teacherPreferencePenalty": 0,
        "activeTeacherSlotCount": 0,
        "availabilityPreferenceScore": 0,
        "changedAssignmentCount": 0,
        "optionalBalanceScore": 0,
    }


__all__ = ["OptimizationViewModel"]
