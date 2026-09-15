"""CP-SAT変数を型付きの索引へまとめる。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

from summer_scheduler.optimization.dto import CandidateData

SessionKey = tuple[int, int]
OccupancyKey = tuple[int, date, int]


@dataclass(slots=True)
class ModelVariables:
    """モデル構築・目的関数・解抽出で共有する変数群。"""

    assignments: dict[CandidateData, cp_model.IntVar] = field(default_factory=dict)
    unassigned: dict[SessionKey, cp_model.IntVar] = field(default_factory=dict)
    student_active: dict[OccupancyKey, cp_model.IntVar] = field(default_factory=dict)
    teacher_active: dict[OccupancyKey, cp_model.IntVar] = field(default_factory=dict)
    student_starts: dict[OccupancyKey, cp_model.IntVar] = field(default_factory=dict)
    teacher_starts: dict[OccupancyKey, cp_model.IntVar] = field(default_factory=dict)
    selection_indicators: list[tuple[cp_model.IntVar, tuple[cp_model.IntVar, ...]]] = field(
        default_factory=list
    )
    request_teacher_used: dict[tuple[int, int], cp_model.IntVar] = field(default_factory=dict)
    regular_teacher_shortfalls: dict[tuple[int, int], cp_model.IntVar] = field(default_factory=dict)
    request_teacher_excess: dict[int, cp_model.IntVar] = field(default_factory=dict)
    request_day_excess: dict[tuple[int, date], cp_model.IntVar] = field(default_factory=dict)
    request_day_used: dict[tuple[int, date], cp_model.IntVar] = field(default_factory=dict)
    request_day_pairs: dict[tuple[int, date, date], cp_model.IntVar] = field(default_factory=dict)
    request_spacing_scores: dict[int, cp_model.IntVar] = field(default_factory=dict)
    request_spacing_quality_minimum: cp_model.IntVar | None = None
    request_month_used: dict[tuple[int, int, int], cp_model.IntVar] = field(default_factory=dict)
    student_week_counts: dict[tuple[int, date], cp_model.IntVar] = field(default_factory=dict)
    student_week_deviations: dict[tuple[int, date, date], cp_model.IntVar] = field(
        default_factory=dict
    )
    student_week_deviation_maximum: cp_model.IntVar | None = None
    teacher_day_used: dict[tuple[int, date], cp_model.IntVar] = field(default_factory=dict)
    teacher_week_counts: dict[tuple[int, date], cp_model.IntVar] = field(default_factory=dict)
    teacher_week_deviations: dict[tuple[int, date, date], cp_model.IntVar] = field(
        default_factory=dict
    )
    teacher_week_deviation_maximum: cp_model.IntVar | None = None
    teacher_loads: dict[int, cp_model.IntVar] = field(default_factory=dict)
    teacher_load_pairwise_deviations: dict[tuple[int, int], cp_model.IntVar] = field(
        default_factory=dict
    )
    teacher_load_capacities: dict[int, int] = field(default_factory=dict)
    # 旧モデルとのシリアライズ互換用。割合ベースの公平性では使用しない。
    teacher_load_maximum: cp_model.IntVar | None = None
    teacher_load_minimum: cp_model.IntVar | None = None


def session_key(candidate: CandidateData) -> SessionKey:
    """候補から安定したセッション識別子を返す。"""
    return candidate.lesson_request_id, candidate.session_index


__all__ = ["ModelVariables", "OccupancyKey", "SessionKey", "session_key"]
