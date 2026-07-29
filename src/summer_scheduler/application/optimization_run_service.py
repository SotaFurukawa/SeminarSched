"""最適化実行のprepare/finalizeを安全に永続化するApplication Service。"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from summer_scheduler.application.optimization_input_builder import (
    build_optimization_input,
)
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.application.project_validation_service import (
    ProjectValidationService,
)
from summer_scheduler.infrastructure.db.models import Assignment, OptimizationRun
from summer_scheduler.infrastructure.logging.optimization_run_log import (
    OptimizationRunLogEvent,
    append_optimization_run_log,
    create_optimization_run_log,
)
from summer_scheduler.infrastructure.repositories import Phase4Repository
from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.dto import (
    OptimizationInput,
    OptimizationResult,
    OptimizationSettings,
    SolverStatus,
)
from summer_scheduler.optimization.result_validation import (
    validate_optimization_result,
)
from summer_scheduler.optimization.serialization import (
    optimization_input_to_json,
    optimization_result_to_json,
)
from summer_scheduler.shared.settings import OptimizationAppSettings

Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)


class OptimizationRunServiceError(RuntimeError):
    """最適化実行境界を安全に完了できない場合の基底例外。"""


class OptimizationPreparationError(OptimizationRunServiceError):
    """入力検証またはprepareに失敗した場合の例外。"""


class OptimizationFinalizationError(OptimizationRunServiceError):
    """結果が保存条件を満たさない、または保存に失敗した場合の例外。"""


class OptimizationInputChangedError(OptimizationFinalizationError):
    """prepare後に最適化入力が変更された場合の例外。"""


@dataclass(frozen=True, slots=True)
class PreparedOptimization:
    """UI workerへ渡してよい、DB Session非依存の実行準備結果。"""

    optimization_run_id: int
    project_id: int
    project_path: Path
    preset: str
    input: OptimizationInput
    input_fingerprint: str
    log_directory: Path
    log_path: Path


@dataclass(frozen=True, slots=True)
class FinalizedOptimization:
    """completedとして保存した結果の個人情報を含まない概要。"""

    optimization_run_id: int
    assignment_count: int
    unassigned_count: int
    warning_count: int


class OptimizationRunService:
    """入力snapshotと結果保存を短いDB transactionへ分離する。"""

    def __init__(
        self,
        projects: ProjectService,
        app_settings: OptimizationAppSettings,
        *,
        validation: ProjectValidationService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._projects = projects
        self._app_settings = app_settings
        self._validation = validation or ProjectValidationService(projects)
        self._clock = clock or _utc_now

    @property
    def default_preset(self) -> str:
        """設定ファイルで選ばれた既定presetをUIへ公開する。"""
        return self._app_settings.default_preset

    def prepare(
        self,
        preset: str,
        *,
        log_directory: Path,
    ) -> PreparedOptimization:
        """検証済み入力snapshotとrunning runを作り、DB資源を保持せず返す。"""
        project = self._projects.require_project()
        issues = self._validation.run_validation()
        error_count = sum(issue.severity == "error" for issue in issues)
        if error_count:
            raise OptimizationPreparationError(
                f"入力検証エラーが{error_count}件あるため最適化を開始できません"
            )

        settings = _optimization_settings(self._app_settings, preset)
        database = self._projects.require_database()
        warning_count = sum(issue.severity == "warning" for issue in issues)
        started_at = _as_utc(self._clock())
        with database.session_factory.begin() as session:
            data = build_optimization_input(
                session=session,
                project_id=project.project_id,
                settings=settings,
            )
            input_json = optimization_input_to_json(data)
            fingerprint = _sha256(input_json)
            run = Phase4Repository(session).create_optimization_run(
                OptimizationRun(
                    project_id=project.project_id,
                    started_at=started_at,
                    finished_at=None,
                    status="running",
                    solver_status="UNKNOWN",
                    time_limit_seconds=math.ceil(settings.time_limit_seconds),
                    objective_summary_json="{}",
                    unassigned_count=0,
                    warning_count=warning_count,
                    log_path_optional=None,
                    input_snapshot_json=input_json,
                    result_snapshot_json="{}",
                    random_seed=settings.random_seed,
                    elapsed_seconds=None,
                )
            )
            run_id = run.id
            try:
                log_path = create_optimization_run_log(
                    log_directory,
                    run_id=run_id,
                    preset=preset,
                    timestamp=started_at,
                    warning_count=warning_count,
                )
            except Exception as exc:
                raise OptimizationPreparationError(
                    "最適化専用ログを作成できないため開始できません"
                ) from exc
            Phase4Repository(session).update_optimization_run(
                run,
                log_path_optional=str(log_path),
            )

        return PreparedOptimization(
            optimization_run_id=run_id,
            project_id=project.project_id,
            project_path=project.path.resolve(strict=False),
            preset=preset,
            input=data,
            input_fingerprint=fingerprint,
            log_directory=log_path.parent,
            log_path=log_path,
        )

    def finalize(
        self,
        prepared: PreparedOptimization,
        result: OptimizationResult,
    ) -> FinalizedOptimization:
        """検証済み実行可能結果だけを現在時間割へ原子的に反映する。"""
        self._require_same_project(prepared)
        if result.cancelled:
            self.mark_cancelled(
                prepared,
                solver_status=result.solver_status,
                elapsed_seconds=result.elapsed_seconds,
                assignment_count=len(result.assignments),
                unassigned_count=len(result.unassigned_lessons),
                warning_count=len(result.warnings),
            )
            raise OptimizationFinalizationError("中止された最適化結果は時間割へ反映しません")
        if result.solver_status not in {"OPTIMAL", "FEASIBLE"}:
            self.mark_failed(
                prepared,
                solver_status=result.solver_status,
                elapsed_seconds=result.elapsed_seconds,
                assignment_count=len(result.assignments),
                unassigned_count=len(result.unassigned_lessons),
                warning_count=len(result.warnings),
            )
            raise OptimizationFinalizationError(
                f"{result.solver_status}の最適化結果は時間割へ反映できません"
            )

        try:
            finalized, finished_at = self._finalize_transaction(prepared, result)
        except Exception as exc:
            try:
                self.mark_failed(
                    prepared,
                    solver_status=result.solver_status,
                    elapsed_seconds=result.elapsed_seconds,
                    assignment_count=len(result.assignments),
                    unassigned_count=len(result.unassigned_lessons),
                    warning_count=len(result.warnings),
                )
            except Exception as mark_exc:
                exc.add_note(f"最適化runのfailed更新にも失敗しました: {type(mark_exc).__name__}")
            if isinstance(exc, OptimizationFinalizationError):
                raise
            raise OptimizationFinalizationError("最適化結果を安全に保存できませんでした") from exc
        self._append_run_log_safely(
            prepared,
            event="completed",
            timestamp=finished_at,
            solver_status=result.solver_status,
            assignment_count=finalized.assignment_count,
            unassigned_count=finalized.unassigned_count,
            warning_count=finalized.warning_count,
            elapsed_seconds=result.elapsed_seconds,
        )
        return finalized

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
        """running runをcancelledにし、Assignmentには触れない。"""
        self._mark_terminal(
            prepared,
            status="cancelled",
            solver_status=solver_status,
            elapsed_seconds=elapsed_seconds,
            assignment_count=assignment_count,
            unassigned_count=unassigned_count,
            warning_count=warning_count,
        )

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
        """running runをfailedにし、Assignmentには触れない。"""
        self._mark_terminal(
            prepared,
            status="failed",
            solver_status=solver_status,
            elapsed_seconds=elapsed_seconds,
            assignment_count=assignment_count,
            unassigned_count=unassigned_count,
            warning_count=warning_count,
        )

    def _finalize_transaction(
        self,
        prepared: PreparedOptimization,
        result: OptimizationResult,
    ) -> tuple[FinalizedOptimization, datetime]:
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = Phase4Repository(session)
            run = _require_running_run(repository, prepared)
            if _sha256(run.input_snapshot_json) != prepared.input_fingerprint:
                raise OptimizationInputChangedError(
                    "保存済み入力snapshotがprepare時点と一致しません"
                )
            if _sha256(optimization_input_to_json(prepared.input)) != prepared.input_fingerprint:
                raise OptimizationInputChangedError(
                    "prepare済み入力snapshotの整合性を確認できません"
                )

            current_input = build_optimization_input(
                session=session,
                project_id=prepared.project_id,
                settings=prepared.input.settings,
            )
            current_json = optimization_input_to_json(current_input)
            if _sha256(current_json) != prepared.input_fingerprint:
                raise OptimizationInputChangedError(
                    "最適化実行中に入力が変更されたため結果を保存しません"
                )

            generation = generate_candidates(current_input)
            report = validate_optimization_result(
                current_input,
                generation,
                result,
            )
            if not report.is_valid:
                raise OptimizationFinalizationError(
                    f"最適化結果にハード制約違反が{len(report.violations)}件あります"
                )

            previous = repository.list_assignments(project_id=prepared.project_id)
            result_snapshot_json = _result_snapshot(
                result,
                previous,
                input_fingerprint=prepared.input_fingerprint,
            )
            objective_summary_json = _canonical_json(asdict(result.objective_breakdown))
            assignments = _assignment_rows(
                prepared,
                result,
            )
            warning_count = run.warning_count + len(result.warnings)
            finished_at = _as_utc(self._clock())
            repository.update_optimization_run(
                run,
                finished_at=finished_at,
                status="completed",
                solver_status=result.solver_status,
                objective_summary_json=objective_summary_json,
                unassigned_count=len(result.unassigned_lessons),
                warning_count=warning_count,
                result_snapshot_json=result_snapshot_json,
                elapsed_seconds=result.elapsed_seconds,
            )
            saved = repository.replace_assignments(
                project_id=prepared.project_id,
                assignments=assignments,
                preserve_locked=True,
            )
            return (
                FinalizedOptimization(
                    optimization_run_id=run.id,
                    assignment_count=len(saved),
                    unassigned_count=len(result.unassigned_lessons),
                    warning_count=warning_count,
                ),
                finished_at,
            )

    def _mark_terminal(
        self,
        prepared: PreparedOptimization,
        *,
        status: OptimizationRunLogEvent,
        solver_status: SolverStatus,
        elapsed_seconds: float | None,
        assignment_count: int | None,
        unassigned_count: int | None,
        warning_count: int | None,
    ) -> None:
        self._require_same_project(prepared)
        database = self._projects.require_database()
        finished_at: datetime | None = None
        total_warning_count: int | None = None
        with database.session_factory.begin() as session:
            repository = Phase4Repository(session)
            run = repository.get_optimization_run(prepared.optimization_run_id)
            if run is None or run.project_id != prepared.project_id:
                raise OptimizationFinalizationError("prepare済みの最適化runが見つかりません")
            _require_matching_log_path(run, prepared)
            if run.status == status:
                return
            if run.status != "running":
                raise OptimizationFinalizationError(
                    "runningではない最適化runの状態は変更できません"
                )
            finished_at = _as_utc(self._clock())
            total_warning_count = (
                run.warning_count + warning_count
                if warning_count is not None
                else run.warning_count
            )
            repository.update_optimization_run(
                run,
                finished_at=finished_at,
                status=status,
                solver_status=solver_status,
                elapsed_seconds=elapsed_seconds,
                unassigned_count=(
                    unassigned_count if unassigned_count is not None else run.unassigned_count
                ),
                warning_count=total_warning_count,
            )
        assert finished_at is not None
        self._append_run_log_safely(
            prepared,
            event=status,
            timestamp=finished_at,
            solver_status=solver_status,
            assignment_count=assignment_count,
            unassigned_count=unassigned_count,
            warning_count=total_warning_count,
            elapsed_seconds=elapsed_seconds,
        )

    def _append_run_log_safely(
        self,
        prepared: PreparedOptimization,
        *,
        event: OptimizationRunLogEvent,
        timestamp: datetime,
        solver_status: SolverStatus,
        assignment_count: int | None,
        unassigned_count: int | None,
        warning_count: int | None,
        elapsed_seconds: float | None,
    ) -> None:
        """DB commit後のログ障害を永続化結果へ波及させない。"""
        try:
            append_optimization_run_log(
                prepared.log_directory,
                prepared.log_path,
                event=event,
                run_id=prepared.optimization_run_id,
                preset=prepared.preset,
                timestamp=timestamp,
                status=event,
                solver_status=solver_status,
                assignment_count=assignment_count,
                unassigned_count=unassigned_count,
                warning_count=warning_count,
                elapsed_seconds=elapsed_seconds,
            )
        except Exception as exc:
            # 例外値やパスには個人情報が含まれ得るため、一般ログには型名だけを残す。
            logger.error(
                "最適化専用ログへの追記に失敗しました（%s）",
                type(exc).__name__,
            )

    def _require_same_project(
        self,
        prepared: PreparedOptimization,
    ) -> None:
        current = self._projects.require_project()
        same_path = _path_key(current.path) == _path_key(prepared.project_path)
        if current.project_id != prepared.project_id or not same_path:
            raise OptimizationFinalizationError("prepare時と同じプロジェクトを開いてください")


def _optimization_settings(
    source: OptimizationAppSettings,
    preset: str,
) -> OptimizationSettings:
    return OptimizationSettings(
        time_limit_seconds=source.time_limit_for(preset),
        random_seed=source.random_seed,
        num_search_workers=source.num_search_workers,
        regular_teacher_priority_weights=(source.regular_teacher_priority_weights),
        preferred_teacher_rank_weights=source.preferred_teacher_rank_weights,
        student_preferred_time_weight=source.student_preferred_time_weight,
        teacher_preferred_time_weight=source.teacher_preferred_time_weight,
        preserve_existing_assignment_weight=(source.preserve_existing_assignment_weight),
        optional_balance_weight=source.optional_balance_weight,
    )


def _require_running_run(
    repository: Phase4Repository,
    prepared: PreparedOptimization,
) -> OptimizationRun:
    run = repository.get_optimization_run(prepared.optimization_run_id)
    if run is None or run.project_id != prepared.project_id or run.status != "running":
        raise OptimizationFinalizationError("running状態のprepare済み最適化runが見つかりません")
    _require_matching_log_path(run, prepared)
    return run


def _require_matching_log_path(
    run: OptimizationRun,
    prepared: PreparedOptimization,
) -> None:
    if run.log_path_optional is None or (
        _path_key(Path(run.log_path_optional)) != _path_key(prepared.log_path)
    ):
        raise OptimizationFinalizationError("最適化専用ログの保存先が一致しません")


def _assignment_rows(
    prepared: PreparedOptimization,
    result: OptimizationResult,
) -> list[Assignment]:
    locked_keys = {
        (row.lesson_request_id, row.session_index)
        for row in prepared.input.existing_assignments
        if row.is_locked
    }
    return [
        Assignment(
            project_id=prepared.project_id,
            lesson_request_id=row.lesson_request_id,
            session_index=row.session_index,
            date=row.day,
            time_slot_id=row.time_slot_id,
            teacher_id=row.teacher_id,
            optimization_run_id_optional=prepared.optimization_run_id,
            is_locked=(row.lesson_request_id, row.session_index) in locked_keys,
            is_manual=False,
            created_by="solver",
        )
        for row in result.assignments
    ]


def _result_snapshot(
    result: OptimizationResult,
    previous: list[Assignment],
    *,
    input_fingerprint: str,
) -> str:
    previous_rows = sorted(
        previous,
        key=lambda row: (
            row.lesson_request_id,
            row.session_index,
            row.id,
        ),
    )
    return _canonical_json(
        {
            "schema": "summer_scheduler.optimization_run_result",
            "schema_version": 1,
            "input_fingerprint": input_fingerprint,
            "optimization_result": json.loads(optimization_result_to_json(result)),
            "previous_assignments": [
                {
                    "id": row.id,
                    "lesson_request_id": row.lesson_request_id,
                    "session_index": row.session_index,
                    "date": row.date.isoformat(),
                    "time_slot_id": row.time_slot_id,
                    "teacher_id": row.teacher_id,
                    "is_locked": row.is_locked,
                    "is_manual": row.is_manual,
                    "created_by": row.created_by,
                    "optimization_run_id": row.optimization_run_id_optional,
                }
                for row in previous_rows
            ],
        }
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=False)))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "FinalizedOptimization",
    "OptimizationFinalizationError",
    "OptimizationInputChangedError",
    "OptimizationPreparationError",
    "OptimizationRunService",
    "OptimizationRunServiceError",
    "PreparedOptimization",
]
