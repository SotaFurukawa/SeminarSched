"""段階的最適化で使用する整数目的式を構築する。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from ortools.sat.python import cp_model

from summer_scheduler.domain.time_ranges import time_ranges_overlap
from summer_scheduler.optimization.dto import (
    CandidateData,
    CandidateGenerationResult,
    LessonRequestData,
    OptimizationInput,
    OptimizationSettings,
)
from summer_scheduler.optimization.variables import ModelVariables

ObjectiveDirection = Literal["minimize", "maximize"]
TeacherLoad = dict[int, int]


@dataclass(frozen=True, slots=True)
class ObjectiveStage:
    """1回のCP-SAT Solveで最適化する、整数値の辞書式目的。"""

    name: str
    direction: ObjectiveDirection
    expression: cp_model.LinearExpr


def build_objective_stages(
    model: cp_model.CpModel,
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> tuple[ObjectiveStage, ...]:
    """仕様順の辞書式目的を返す。

    `add_hard_constraints`の後に呼び出すこと。各式は整数係数だけを使用し、前段の
    最適値を等式で固定してから次段へ進められる。第6段階だけは設定値が0なら省略する。
    """
    stages = [
        ObjectiveStage(
            name="unassigned_count",
            direction="minimize",
            expression=cp_model.LinearExpr.sum(
                [variables.unassigned[key] for key in sorted(variables.unassigned)]
            ),
        ),
        ObjectiveStage(
            name="teacher_preference_penalty",
            direction="minimize",
            expression=_teacher_preference_expression(data, generation, variables),
        ),
        ObjectiveStage(
            name="active_teacher_slot_count",
            direction="minimize",
            expression=cp_model.LinearExpr.sum(
                [variables.teacher_active[key] for key in sorted(variables.teacher_active)]
            ),
        ),
        ObjectiveStage(
            name="availability_preference_score",
            direction="maximize",
            expression=_availability_preference_expression(data, generation, variables),
        ),
        ObjectiveStage(
            name="changed_assignment_count",
            direction="minimize",
            expression=_changed_assignment_expression(data, generation, variables),
        ),
    ]
    if data.settings.optional_balance_weight > 0:
        stages.append(
            ObjectiveStage(
                name="teacher_load_imbalance",
                direction="minimize",
                expression=_teacher_load_imbalance_expression(model, data, variables),
            )
        )
    return tuple(stages)


def teacher_preference_penalty(
    request: LessonRequestData,
    teacher_id: int,
    settings: OptimizationSettings,
) -> int:
    """1候補の講師希望違反点を返す。

    通常担当の優先度1～4と希望順位1～3のうち、同じ講師に該当する最大点だけを
    採用する。基準点も当該LessonRequestに設定された講師区分の最大値とするため、
    希望講師を一切設定していない要求へ無意味な違反点を付けない。
    """
    if request.regular_teacher_priority == 5:
        return 0
    scores_by_teacher = _teacher_preference_scores(request, settings)
    best_configured_score = max(scores_by_teacher.values(), default=0)
    return best_configured_score - scores_by_teacher.get(teacher_id, 0)


def realized_teacher_loads(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    selected: Iterable[CandidateData],
) -> TeacherLoad:
    """解における関連講師ごとの稼働コマ数を返す。

    候補を持つ講師と固定集団授業の担当講師を母集団とし、稼働ゼロの講師も残す。
    集団授業は個別コマとの半開区間が重なる各コマを固定稼働として数える。
    """
    relevant_teacher_ids = {candidate.teacher_id for candidate in generation.candidates} | {
        block.teacher_id for block in data.group_blocks if block.teacher_id is not None
    }
    active_slots = {
        (candidate.teacher_id, candidate.day, candidate.time_slot_id) for candidate in selected
    }
    for block in data.group_blocks:
        if block.teacher_id is None:
            continue
        for slot in data.time_slots:
            if time_ranges_overlap(
                slot.start_time,
                slot.end_time,
                block.start_time,
                block.end_time,
            ):
                active_slots.add((block.teacher_id, block.day, slot.id))

    loads: TeacherLoad = {teacher_id: 0 for teacher_id in sorted(relevant_teacher_ids)}
    for teacher_id, _, _ in active_slots:
        loads[teacher_id] += 1
    return loads


def _teacher_preference_expression(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> cp_model.LinearExpr:
    requests = {request.id: request for request in data.lesson_requests}
    candidate_vars: list[cp_model.IntVar] = []
    penalties: list[int] = []
    for candidate in generation.candidates:
        candidate_vars.append(variables.assignments[candidate])
        penalties.append(
            teacher_preference_penalty(
                requests[candidate.lesson_request_id],
                candidate.teacher_id,
                data.settings,
            )
        )
    return cp_model.LinearExpr.weighted_sum(candidate_vars, penalties)


def _teacher_preference_scores(
    request: LessonRequestData,
    settings: OptimizationSettings,
) -> dict[int, int]:
    scores: dict[int, int] = {}
    if request.regular_teacher_id is not None and 1 <= request.regular_teacher_priority <= 4:
        _keep_maximum(
            scores,
            request.regular_teacher_id,
            settings.regular_teacher_priority_weights[request.regular_teacher_priority - 1],
        )
    for rank, teacher_id in enumerate(request.preferred_teacher_ids[:3]):
        if teacher_id is None:
            continue
        _keep_maximum(scores, teacher_id, settings.preferred_teacher_rank_weights[rank])
    return scores


def _keep_maximum(scores: dict[int, int], teacher_id: int, score: int) -> None:
    scores[teacher_id] = max(scores.get(teacher_id, 0), score)


def _availability_preference_expression(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> cp_model.LinearExpr:
    candidate_vars: list[cp_model.IntVar] = []
    scores: list[int] = []
    for candidate in generation.candidates:
        score = 0
        if candidate.student_availability_level == 2:
            score += data.settings.student_preferred_time_weight
        if candidate.teacher_availability_level == 2:
            score += data.settings.teacher_preferred_time_weight
        candidate_vars.append(variables.assignments[candidate])
        scores.append(score)
    return cp_model.LinearExpr.weighted_sum(candidate_vars, scores)


def _changed_assignment_expression(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> cp_model.LinearExpr:
    candidate_by_identity = {
        (
            candidate.lesson_request_id,
            candidate.session_index,
            candidate.day,
            candidate.time_slot_id,
            candidate.teacher_id,
        ): candidate
        for candidate in generation.candidates
    }
    existing = tuple(item for item in data.existing_assignments if not item.is_locked)
    matching_vars: list[cp_model.IntVar] = []
    for item in existing:
        candidate = candidate_by_identity.get(
            (
                item.lesson_request_id,
                item.session_index,
                item.day,
                item.time_slot_id,
                item.teacher_id,
            )
        )
        if candidate is not None:
            matching_vars.append(variables.assignments[candidate])

    weight = data.settings.preserve_existing_assignment_weight
    return cp_model.LinearExpr.weighted_sum(
        matching_vars,
        [-weight] * len(matching_vars),
    ) + weight * len(existing)


def _teacher_load_imbalance_expression(
    model: cp_model.CpModel,
    data: OptimizationInput,
    variables: ModelVariables,
) -> cp_model.LinearExpr:
    active_by_teacher: dict[int, list[cp_model.IntVar]] = defaultdict(list)
    for (teacher_id, _, _), active in sorted(variables.teacher_active.items()):
        active_by_teacher[teacher_id].append(active)
    if not active_by_teacher:
        return cp_model.LinearExpr.constant(0)

    load_vars: list[cp_model.IntVar] = []
    maximum_load = max(len(active_vars) for active_vars in active_by_teacher.values())
    for teacher_id, active_vars in sorted(active_by_teacher.items()):
        load = model.new_int_var(0, len(active_vars), f"teacher_load_{teacher_id}")
        model.add(load == cp_model.LinearExpr.sum(active_vars))
        load_vars.append(load)
        variables.teacher_loads[teacher_id] = load

    maximum = model.new_int_var(0, maximum_load, "teacher_load_maximum")
    minimum = model.new_int_var(0, maximum_load, "teacher_load_minimum")
    model.add_max_equality(maximum, load_vars)
    model.add_min_equality(minimum, load_vars)
    variables.teacher_load_maximum = maximum
    variables.teacher_load_minimum = minimum
    return data.settings.optional_balance_weight * (maximum - minimum)


__all__ = [
    "ObjectiveDirection",
    "ObjectiveStage",
    "TeacherLoad",
    "build_objective_stages",
    "realized_teacher_loads",
    "teacher_preference_penalty",
]
