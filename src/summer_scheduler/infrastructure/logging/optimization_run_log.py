"""個人情報を含めないPhase 4最適化run専用ログ。"""

from __future__ import annotations

import json
import math
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from summer_scheduler.optimization.dto import SolverStatus

OptimizationRunLogEvent = Literal["completed", "cancelled", "failed"]

_ALLOWED_PRESETS = frozenset({"fast", "standard", "high_quality"})
_ALLOWED_TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})
_ALLOWED_SOLVER_STATUSES = frozenset(
    {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "MODEL_INVALID"}
)
_FILE_PREFIX = "optimization-run-"


class OptimizationRunLogError(RuntimeError):
    """最適化run専用ログを安全に作成・追記できない。"""


def create_optimization_run_log(
    directory: Path,
    *,
    run_id: int,
    preset: str,
    timestamp: datetime,
    warning_count: int,
) -> Path:
    """run固有ファイルを排他的に作り、安全な開始概要を1行書く。"""
    _require_positive(run_id, "run_id")
    _require_preset(preset)
    _require_non_negative(warning_count, "warning_count")
    normalized_timestamp = _as_utc(timestamp)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        resolved_directory = directory.resolve(strict=True)
        path = resolved_directory / (
            f"{_FILE_PREFIX}{normalized_timestamp:%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex}.log"
        )
        _write_json_line(
            path,
            {
                "assignment_count": 0,
                "elapsed_seconds": 0.0,
                "event": "started",
                "preset": preset,
                "run_id": run_id,
                "solver_status": "UNKNOWN",
                "status": "running",
                "timestamp": normalized_timestamp.isoformat(),
                "unassigned_count": 0,
                "warning_count": warning_count,
            },
            exclusive=True,
        )
    except (OSError, ValueError) as exc:
        raise OptimizationRunLogError("最適化専用ログを作成できません") from exc
    return path


def append_optimization_run_log(
    directory: Path,
    path: Path,
    *,
    event: OptimizationRunLogEvent,
    run_id: int,
    preset: str,
    timestamp: datetime,
    status: str,
    solver_status: SolverStatus,
    assignment_count: int | None,
    unassigned_count: int | None,
    warning_count: int | None,
    elapsed_seconds: float | None,
) -> None:
    """既存のrun固有ファイルへ、安全な終了概要だけを追記する。"""
    _require_positive(run_id, "run_id")
    _require_preset(preset)
    if solver_status not in _ALLOWED_SOLVER_STATUSES:
        raise OptimizationRunLogError("最適化専用ログのsolver_statusが不正です")
    if event not in _ALLOWED_TERMINAL_STATUSES or status != event:
        raise OptimizationRunLogError("最適化専用ログの終了状態が不正です")
    _require_optional_non_negative(assignment_count, "assignment_count")
    _require_optional_non_negative(unassigned_count, "unassigned_count")
    _require_optional_non_negative(warning_count, "warning_count")
    if elapsed_seconds is not None and (not math.isfinite(elapsed_seconds) or elapsed_seconds < 0):
        raise OptimizationRunLogError("最適化専用ログのelapsed_secondsが不正です")
    normalized_timestamp = _as_utc(timestamp)
    try:
        resolved_directory = directory.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        if (
            resolved_path.parent != resolved_directory
            or not resolved_path.name.startswith(_FILE_PREFIX)
            or resolved_path.suffix != ".log"
        ):
            raise OptimizationRunLogError("最適化専用ログの保存先が不正です")
        _write_json_line(
            resolved_path,
            {
                "assignment_count": assignment_count,
                "elapsed_seconds": elapsed_seconds,
                "event": event,
                "preset": preset,
                "run_id": run_id,
                "solver_status": solver_status,
                "status": status,
                "timestamp": normalized_timestamp.isoformat(),
                "unassigned_count": unassigned_count,
                "warning_count": warning_count,
            },
            exclusive=False,
        )
    except OptimizationRunLogError:
        raise
    except (OSError, ValueError) as exc:
        raise OptimizationRunLogError("最適化専用ログへ追記できません") from exc


def _write_json_line(
    path: Path,
    value: dict[str, object],
    *,
    exclusive: bool,
) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    mode = "x" if exclusive else "a"
    with path.open(mode, encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _require_preset(value: str) -> None:
    if value not in _ALLOWED_PRESETS:
        raise OptimizationRunLogError("最適化専用ログのpresetが不正です")


def _require_positive(value: int, field: str) -> None:
    if type(value) is not int or value <= 0:
        raise OptimizationRunLogError(f"最適化専用ログの{field}が不正です")


def _require_non_negative(value: int, field: str) -> None:
    if type(value) is not int or value < 0:
        raise OptimizationRunLogError(f"最適化専用ログの{field}が不正です")


def _require_optional_non_negative(value: int | None, field: str) -> None:
    if value is not None:
        _require_non_negative(value, field)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "OptimizationRunLogError",
    "OptimizationRunLogEvent",
    "append_optimization_run_log",
    "create_optimization_run_log",
]
