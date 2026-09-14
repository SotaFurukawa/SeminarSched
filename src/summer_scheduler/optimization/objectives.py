"""段階的最適化で使用する整数目的式を構築する。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
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
_REGULAR_TEACHER_SCORE_BONUS = 2
_SAME_DAY_CONCENTRATION_EXCEPTION_SESSIONS = 8


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
    最適値を等式で固定してから次段へ進められる。勤務可能枠に対する実稼働率の
    公平性は、講師コマ数の圧縮などより先に評価する。設定値が0なら省略する。
    """
    worst_spacing_quality, spacing_score = _request_spacing_expressions(
        model,
        data,
        generation,
        variables,
    )
    maximum_student_week_deviation, student_period_imbalance_expression = (
        _student_period_imbalance_expressions(
            model,
            data,
            generation,
            variables,
        )
    )
    stages = [
        ObjectiveStage(
            name="unassigned_count",
            direction="minimize",
            expression=cp_model.LinearExpr.sum(
                [variables.unassigned[key] for key in sorted(variables.unassigned)]
            ),
        ),
        ObjectiveStage(
            name="same_day_concentration_penalty",
            direction="minimize",
            expression=_same_day_concentration_expression(
                model,
                data,
                generation,
                variables,
            ),
        ),
        ObjectiveStage(
            name="worst_request_spacing_quality",
            direction="maximize",
            expression=worst_spacing_quality,
        ),
        ObjectiveStage(
            name="maximum_student_week_deviation",
            direction="minimize",
            expression=maximum_student_week_deviation,
        ),
        # 最悪ケースの分散を守ったうえで講師マッチングを先に確定する。
        # 優先度ごとの最低担当率はハード制約で守り、1～4は最低率を超える
        # 通常担当への割当ても、この段階で分散の合計点より先に評価する。
        ObjectiveStage(
            name="teacher_preference_penalty",
            direction="minimize",
            expression=_teacher_preference_expression(data, generation, variables),
        ),
        ObjectiveStage(
            name="teacher_continuity_penalty",
            direction="minimize",
            expression=_teacher_continuity_expression(model, generation, variables),
        ),
        ObjectiveStage(
            name="request_spacing_score",
            direction="maximize",
            expression=spacing_score,
        ),
        ObjectiveStage(
            name="student_period_imbalance",
            direction="minimize",
            expression=student_period_imbalance_expression,
        ),
        ObjectiveStage(
            name="period_distribution_score",
            direction="maximize",
            expression=_period_distribution_expression(model, data, generation, variables),
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
    maximum_teacher_week_deviation, teacher_week_imbalance_expression = (
        _teacher_week_imbalance_expressions(model, data, variables)
    )
    stages.extend(
        [
            ObjectiveStage(
                name="active_teacher_day_count",
                direction="minimize",
                expression=cp_model.LinearExpr.sum(
                    list(_teacher_day_used_variables(model, data, variables).values())
                ),
            ),
            ObjectiveStage(
                name="maximum_teacher_week_deviation",
                direction="minimize",
                expression=maximum_teacher_week_deviation,
            ),
            ObjectiveStage(
                name="teacher_week_imbalance",
                direction="minimize",
                expression=teacher_week_imbalance_expression,
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


def teacher_availability_capacities(
    data: OptimizationInput,
    teacher_ids: Iterable[int],
) -> dict[int, int]:
    """講師ごとの勤務可能コマ数を、公平性の分母として返す。

    回答漏れや固定集団授業だけの講師でも0除算にならないよう最小値を1とする。
    """
    relevant = set(teacher_ids)
    open_dates = set(data.open_dates)
    enabled_slot_ids = {slot.id for slot in data.time_slots if slot.enabled}
    available = {
        (row.owner_id, row.day, row.time_slot_id)
        for row in data.availabilities
        if row.owner_type == "teacher"
        and row.owner_id in relevant
        and row.level > 0
        and row.day in open_dates
        and row.time_slot_id in enabled_slot_ids
    }
    return {
        teacher_id: max(
            1,
            sum(owner_id == teacher_id for owner_id, _day, _slot_id in available),
        )
        for teacher_id in sorted(relevant)
    }


def teacher_participation_imbalance(
    data: OptimizationInput,
    loads: TeacherLoad,
) -> int:
    """勤務可能枠に対する実稼働率の講師間差を整数の交差積で測る。"""
    capacities = teacher_availability_capacities(data, loads)
    teacher_ids = sorted(loads)
    return sum(
        abs(loads[first] * capacities[second] - loads[second] * capacities[first])
        for position, first in enumerate(teacher_ids)
        for second in teacher_ids[position + 1 :]
    )


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
            settings.regular_teacher_priority_weights[request.regular_teacher_priority - 1]
            + _REGULAR_TEACHER_SCORE_BONUS,
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


def _teacher_continuity_expression(
    model: cp_model.CpModel,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> cp_model.LinearExpr:
    """同一生徒・科目に相当する要求を、できるだけ少ない講師へまとめる。"""
    grouped: dict[tuple[int, int], list[CandidateData]] = defaultdict(list)
    for candidate in generation.candidates:
        grouped[(candidate.lesson_request_id, candidate.teacher_id)].append(candidate)

    used_by_request: dict[int, list[cp_model.IntVar]] = defaultdict(list)
    for (request_id, teacher_id), candidates in sorted(grouped.items()):
        used = model.new_bool_var(f"request_teacher_used_{request_id}_{teacher_id}")
        variables.request_teacher_used[(request_id, teacher_id)] = used
        selections = [variables.assignments[candidate] for candidate in candidates]
        for selection in selections:
            model.add(selection <= used)
        model.add(used <= cp_model.LinearExpr.sum(selections))
        used_by_request[request_id].append(used)

    excess_variables: list[cp_model.IntVar] = []
    for request_id, used_variables in sorted(used_by_request.items()):
        upper_bound = max(0, len(used_variables) - 1)
        excess = model.new_int_var(
            0,
            upper_bound,
            f"request_teacher_excess_{request_id}",
        )
        model.add(excess >= cp_model.LinearExpr.sum(used_variables) - 1)
        variables.request_teacher_excess[request_id] = excess
        excess_variables.append(excess)
    return cp_model.LinearExpr.sum(excess_variables)


def _same_day_concentration_expression(
    model: cp_model.CpModel,
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> cp_model.LinearExpr:
    """8回未満の同一要求は、同じ日に2回以上固めないことを優先する。"""
    requests = {request.id: request for request in data.lesson_requests}
    grouped: dict[tuple[int, date], list[CandidateData]] = defaultdict(list)
    for candidate in generation.candidates:
        request = requests[candidate.lesson_request_id]
        if request.required_sessions >= _SAME_DAY_CONCENTRATION_EXCEPTION_SESSIONS:
            continue
        grouped[(candidate.lesson_request_id, candidate.day)].append(candidate)

    excess_variables: list[cp_model.IntVar] = []
    for (request_id, day), candidates in sorted(grouped.items()):
        request = requests[request_id]
        excess = model.new_int_var(
            0,
            max(0, request.required_sessions - 1),
            f"request_day_excess_{request_id}_{day.isoformat()}",
        )
        selections = [variables.assignments[candidate] for candidate in candidates]
        model.add(excess >= cp_model.LinearExpr.sum(selections) - 1)
        variables.request_day_excess[(request_id, day)] = excess
        excess_variables.append(excess)
    return cp_model.LinearExpr.sum(excess_variables)


def _period_distribution_expression(
    model: cp_model.CpModel,
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> cp_model.LinearExpr:
    """複数月にまたがる講習では、同一要求が各月へ分散するほど高く評価する。"""
    requests = {request.id: request for request in data.lesson_requests}
    if len({(day.year, day.month) for day in data.open_dates}) < 2:
        return cp_model.LinearExpr.constant(0)

    grouped: dict[tuple[int, int, int], list[CandidateData]] = defaultdict(list)
    for candidate in generation.candidates:
        if requests[candidate.lesson_request_id].required_sessions < 2:
            continue
        grouped[(candidate.lesson_request_id, candidate.day.year, candidate.day.month)].append(
            candidate
        )

    used_variables: list[cp_model.IntVar] = []
    for key, candidates in sorted(grouped.items()):
        request_id, year, month = key
        used = model.new_bool_var(f"request_month_used_{request_id}_{year}_{month}")
        selections = [variables.assignments[candidate] for candidate in candidates]
        for selection in selections:
            model.add(selection <= used)
        model.add(used <= cp_model.LinearExpr.sum(selections))
        variables.request_month_used[key] = used
        used_variables.append(used)
    return cp_model.LinearExpr.sum(used_variables)


def _request_spacing_expressions(
    model: cp_model.CpModel,
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> tuple[cp_model.LinearExpr, cp_model.LinearExpr]:
    """同一生徒・科目の授業日を、開校日数÷回数の格子へ近づける。"""
    open_days = tuple(sorted(set(data.open_dates)))
    if len(open_days) < 2:
        zero = cp_model.LinearExpr.constant(0)
        return zero, zero
    day_positions = {day_value: index for index, day_value in enumerate(open_days)}
    requests = {request.id: request for request in data.lesson_requests}
    request_score_terms: dict[int, list[tuple[cp_model.IntVar, int]]] = defaultdict(list)
    for candidate in generation.candidates:
        request = requests[candidate.lesson_request_id]
        if request.required_sessions < 2:
            continue
        request_score_terms[request.id].append(
            (
                variables.assignments[candidate],
                _request_candidate_spacing_score(
                    len(open_days),
                    day_positions[candidate.day],
                    request.required_sessions,
                    candidate.session_index,
                ),
            )
        )

    score_variables: list[cp_model.IntVar] = []
    quality_minimum: cp_model.IntVar | None = None
    for request_id, terms in sorted(request_score_terms.items()):
        required_sessions = requests[request_id].required_sessions
        maximum_session_score = 2 * required_sessions * len(open_days) + 1
        maximum_request_score = required_sessions * maximum_session_score
        score = model.new_int_var(
            0,
            maximum_request_score,
            f"request_spacing_score_{request_id}",
        )
        model.add(
            score
            == cp_model.LinearExpr.weighted_sum(
                [variable for variable, _weight in terms],
                [weight for _variable, weight in terms],
            )
        )
        variables.request_spacing_scores[request_id] = score
        score_variables.append(score)
        if quality_minimum is None:
            quality_minimum = model.new_int_var(0, 1000, "request_spacing_quality_minimum")
            variables.request_spacing_quality_minimum = quality_minimum
        # 各科目を0～1000へ正規化し、最も分散できていない科目を先に改善する。
        model.add(score * 1000 >= quality_minimum * maximum_request_score)

    if quality_minimum is None:
        zero = cp_model.LinearExpr.constant(0)
        return zero, zero
    return quality_minimum, cp_model.LinearExpr.sum(score_variables)


def _request_candidate_spacing_score(
    open_day_count: int,
    day_position: int,
    required_sessions: int,
    session_index: int,
) -> int:
    """講習期間を回数で等分した各回の中心へ近いほど高い整数点を返す。"""
    maximum_score = 2 * required_sessions * open_day_count + 1
    actual_position = 2 * required_sessions * day_position
    target_position = (2 * session_index - 1) * open_day_count
    return maximum_score - abs(actual_position - target_position)


def request_spacing_score(
    data: OptimizationInput,
    selected: Iterable[CandidateData],
) -> int:
    """選択済み解の、開校日間隔に基づく要求別分散スコアを返す。"""
    open_days = tuple(sorted(set(data.open_dates)))
    if len(open_days) < 2:
        return 0
    day_positions = {day_value: index for index, day_value in enumerate(open_days)}
    requests = {request.id: request for request in data.lesson_requests}
    return sum(
        _request_candidate_spacing_score(
            len(open_days),
            day_positions[candidate.day],
            requests[candidate.lesson_request_id].required_sessions,
            candidate.session_index,
        )
        for candidate in selected
        if requests[candidate.lesson_request_id].required_sessions >= 2
    )


def worst_request_spacing_quality(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    selected: Iterable[CandidateData],
) -> int:
    """最も分散できていない生徒・科目の正規化スコア（0～1000）を返す。"""
    open_days = tuple(sorted(set(data.open_dates)))
    if len(open_days) < 2:
        return 0
    requests = {request.id: request for request in data.lesson_requests}
    eligible_request_ids: set[int] = set()
    for candidate in generation.candidates:
        request = requests[candidate.lesson_request_id]
        if request.required_sessions >= 2:
            eligible_request_ids.add(request.id)
    if not eligible_request_ids:
        return 0

    day_positions = {day_value: index for index, day_value in enumerate(open_days)}
    scores: dict[int, int] = defaultdict(int)
    for candidate in selected:
        request = requests[candidate.lesson_request_id]
        if request.id in eligible_request_ids:
            scores[request.id] += _request_candidate_spacing_score(
                len(open_days),
                day_positions[candidate.day],
                request.required_sessions,
                candidate.session_index,
            )

    qualities: list[int] = []
    open_day_count = len(open_days)
    for request_id in sorted(eligible_request_ids):
        required_sessions = requests[request_id].required_sessions
        maximum_session_score = 2 * required_sessions * open_day_count + 1
        maximum_request_score = required_sessions * maximum_session_score
        qualities.append((scores[request_id] * 1000) // maximum_request_score)
    return min(qualities)


def _student_period_imbalance_expressions(
    model: cp_model.CpModel,
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
) -> tuple[cp_model.LinearExpr, cp_model.LinearExpr]:
    """生徒ごとに、受講可能な週の授業数をできるだけ均等にする。"""
    requests = {request.id: request for request in data.lesson_requests}
    candidates_by_student_week: dict[tuple[int, date], list[CandidateData]] = defaultdict(list)
    total_sessions_by_student: dict[int, int] = defaultdict(int)
    for request in data.lesson_requests:
        total_sessions_by_student[request.student_id] += request.required_sessions
    for candidate in generation.candidates:
        student_id = requests[candidate.lesson_request_id].student_id
        candidates_by_student_week[(student_id, _sunday_of_week(candidate.day))].append(candidate)

    weeks_by_student: dict[int, list[date]] = defaultdict(list)
    for student_id, week_start in sorted(candidates_by_student_week):
        weeks_by_student[student_id].append(week_start)

    deviations: list[cp_model.IntVar] = []
    for student_id, weeks in sorted(weeks_by_student.items()):
        distinct_weeks = sorted(set(weeks))
        session_bound = total_sessions_by_student[student_id]
        if session_bound < 2 or len(distinct_weeks) < 2:
            continue
        weekly_counts: dict[date, cp_model.IntVar] = {}
        for week_start in distinct_weeks:
            count = model.new_int_var(
                0,
                session_bound,
                f"student_week_count_{student_id}_{week_start.isoformat()}",
            )
            model.add(
                count
                == cp_model.LinearExpr.sum(
                    [
                        variables.assignments[candidate]
                        for candidate in candidates_by_student_week[(student_id, week_start)]
                    ]
                )
            )
            weekly_counts[week_start] = count
            variables.student_week_counts[(student_id, week_start)] = count
        for position, first_week in enumerate(distinct_weeks):
            for second_week in distinct_weeks[position + 1 :]:
                deviation = model.new_int_var(
                    0,
                    session_bound,
                    (
                        f"student_week_deviation_{student_id}_"
                        f"{first_week.isoformat()}_{second_week.isoformat()}"
                    ),
                )
                model.add_abs_equality(
                    deviation,
                    weekly_counts[first_week] - weekly_counts[second_week],
                )
                deviations.append(deviation)
                variables.student_week_deviations[(student_id, first_week, second_week)] = deviation
    if not deviations:
        zero = cp_model.LinearExpr.constant(0)
        return zero, zero
    maximum = model.new_int_var(
        0,
        max(total_sessions_by_student.values(), default=0),
        "student_week_deviation_maximum",
    )
    model.add_max_equality(maximum, deviations)
    variables.student_week_deviation_maximum = maximum
    return maximum, cp_model.LinearExpr.sum(deviations)


def _teacher_day_used_variables(
    model: cp_model.CpModel,
    data: OptimizationInput,
    variables: ModelVariables,
) -> dict[tuple[int, date], cp_model.IntVar]:
    if variables.teacher_day_used:
        return variables.teacher_day_used
    active_by_teacher_day: dict[tuple[int, date], list[cp_model.IntVar]] = defaultdict(list)
    for (teacher_id, day_value, _slot_id), active in sorted(variables.teacher_active.items()):
        active_by_teacher_day[(teacher_id, day_value)].append(active)
    for (teacher_id, day_value), active_slots in sorted(active_by_teacher_day.items()):
        used = model.new_bool_var(f"teacher_day_used_{teacher_id}_{day_value.isoformat()}")
        for active in active_slots:
            model.add(active <= used)
        model.add(used <= cp_model.LinearExpr.sum(active_slots))
        variables.teacher_day_used[(teacher_id, day_value)] = used
    return variables.teacher_day_used


def _teacher_week_imbalance_expressions(
    model: cp_model.CpModel,
    data: OptimizationInput,
    variables: ModelVariables,
) -> tuple[cp_model.LinearExpr, cp_model.LinearExpr]:
    day_used = _teacher_day_used_variables(model, data, variables)
    days_by_teacher_week: dict[tuple[int, date], list[cp_model.IntVar]] = defaultdict(list)
    for (teacher_id, day_value), used in sorted(day_used.items()):
        days_by_teacher_week[(teacher_id, _sunday_of_week(day_value))].append(used)
    weeks_by_teacher: dict[int, list[date]] = defaultdict(list)
    for teacher_id, week_start in sorted(days_by_teacher_week):
        weeks_by_teacher[teacher_id].append(week_start)

    deviations: list[cp_model.IntVar] = []
    for teacher_id, week_values in sorted(weeks_by_teacher.items()):
        weeks = sorted(set(week_values))
        if len(weeks) < 2:
            continue
        counts: dict[date, cp_model.IntVar] = {}
        for week_start in weeks:
            day_variables = days_by_teacher_week[(teacher_id, week_start)]
            count = model.new_int_var(
                0,
                len(day_variables),
                f"teacher_week_count_{teacher_id}_{week_start.isoformat()}",
            )
            model.add(count == cp_model.LinearExpr.sum(day_variables))
            variables.teacher_week_counts[(teacher_id, week_start)] = count
            counts[week_start] = count
        for position, first_week in enumerate(weeks):
            for second_week in weeks[position + 1 :]:
                deviation = model.new_int_var(
                    0,
                    max(
                        len(days_by_teacher_week[(teacher_id, first_week)]),
                        len(days_by_teacher_week[(teacher_id, second_week)]),
                    ),
                    f"teacher_week_deviation_{teacher_id}_{first_week.isoformat()}_{second_week.isoformat()}",
                )
                model.add_abs_equality(
                    deviation,
                    counts[first_week] - counts[second_week],
                )
                deviations.append(deviation)
                variables.teacher_week_deviations[(teacher_id, first_week, second_week)] = deviation
    if not deviations:
        zero = cp_model.LinearExpr.constant(0)
        return zero, zero
    maximum = model.new_int_var(
        0,
        max((len(values) for values in days_by_teacher_week.values()), default=0),
        "teacher_week_deviation_maximum",
    )
    model.add_max_equality(maximum, deviations)
    variables.teacher_week_deviation_maximum = maximum
    return maximum, cp_model.LinearExpr.sum(deviations)


def realized_teacher_active_days(
    data: OptimizationInput,
    selected: Iterable[CandidateData],
) -> dict[int, set[date]]:
    """解と固定授業を含む、講師ごとの実出勤日を返す。"""
    result: dict[int, set[date]] = defaultdict(set)
    for candidate in selected:
        result[candidate.teacher_id].add(candidate.day)
    for block in data.group_blocks:
        if block.teacher_id is not None:
            result[block.teacher_id].add(block.day)
    return result


def teacher_week_imbalance(
    data: OptimizationInput,
    selected: Iterable[CandidateData],
) -> int:
    """講師ごとの週別出勤日数のばらつきを返す。"""
    active_days = realized_teacher_active_days(data, selected)
    weeks = sorted({_sunday_of_week(day_value) for day_value in data.open_dates})
    return sum(
        abs(
            sum(_sunday_of_week(day_value) == first for day_value in days)
            - sum(_sunday_of_week(day_value) == second for day_value in days)
        )
        for days in active_days.values()
        for position, first in enumerate(weeks)
        for second in weeks[position + 1 :]
    )


def student_period_imbalance(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    selected: Iterable[CandidateData],
) -> int:
    """選択済み解の、生徒別・週別授業数のばらつきを返す。"""
    requests = {request.id: request for request in data.lesson_requests}
    eligible_weeks: dict[int, set[date]] = defaultdict(set)
    for candidate in generation.candidates:
        student_id = requests[candidate.lesson_request_id].student_id
        eligible_weeks[student_id].add(_sunday_of_week(candidate.day))
    counts: dict[tuple[int, date], int] = defaultdict(int)
    for candidate in selected:
        student_id = requests[candidate.lesson_request_id].student_id
        counts[(student_id, _sunday_of_week(candidate.day))] += 1
    return sum(
        abs(counts[(student_id, first)] - counts[(student_id, second)])
        for student_id, weeks in eligible_weeks.items()
        for position, first in enumerate(sorted(weeks))
        for second in sorted(weeks)[position + 1 :]
    )


def maximum_student_week_deviation(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    selected: Iterable[CandidateData],
) -> int:
    """全生徒のうち最も大きい週別授業数差を返す。"""
    requests = {request.id: request for request in data.lesson_requests}
    eligible_weeks: dict[int, set[date]] = defaultdict(set)
    for candidate in generation.candidates:
        student_id = requests[candidate.lesson_request_id].student_id
        eligible_weeks[student_id].add(_sunday_of_week(candidate.day))
    counts: dict[tuple[int, date], int] = defaultdict(int)
    for candidate in selected:
        student_id = requests[candidate.lesson_request_id].student_id
        counts[(student_id, _sunday_of_week(candidate.day))] += 1
    return max(
        (
            abs(counts[(student_id, first)] - counts[(student_id, second)])
            for student_id, weeks in eligible_weeks.items()
            for position, first in enumerate(sorted(weeks))
            for second in sorted(weeks)[position + 1 :]
        ),
        default=0,
    )


def maximum_teacher_week_deviation(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    selected: Iterable[CandidateData],
) -> int:
    """候補がある週の範囲で、講師ごとの最大週別出勤日数差を返す。"""
    eligible_weeks: dict[int, set[date]] = defaultdict(set)
    for candidate in generation.candidates:
        eligible_weeks[candidate.teacher_id].add(_sunday_of_week(candidate.day))
    for block in data.group_blocks:
        if block.teacher_id is not None:
            eligible_weeks[block.teacher_id].add(_sunday_of_week(block.day))
    active_days = realized_teacher_active_days(data, selected)
    return max(
        (
            abs(
                sum(_sunday_of_week(day_value) == first for day_value in active_days[teacher_id])
                - sum(_sunday_of_week(day_value) == second for day_value in active_days[teacher_id])
            )
            for teacher_id, weeks in eligible_weeks.items()
            for position, first in enumerate(sorted(weeks))
            for second in sorted(weeks)[position + 1 :]
        ),
        default=0,
    )


def _sunday_of_week(day_value: date) -> date:
    return day_value - timedelta(days=(day_value.weekday() + 1) % 7)


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

    load_bounds: dict[int, int] = {}
    for teacher_id, active_vars in sorted(active_by_teacher.items()):
        load = model.new_int_var(0, len(active_vars), f"teacher_load_{teacher_id}")
        model.add(load == cp_model.LinearExpr.sum(active_vars))
        variables.teacher_loads[teacher_id] = load
        load_bounds[teacher_id] = len(active_vars)

    capacities = teacher_availability_capacities(data, active_by_teacher)
    variables.teacher_load_capacities.update(capacities)
    deviations: list[cp_model.IntVar] = []
    teacher_ids = sorted(active_by_teacher)
    for position, first in enumerate(teacher_ids):
        for second in teacher_ids[position + 1 :]:
            bound = max(
                load_bounds[first] * capacities[second],
                load_bounds[second] * capacities[first],
            )
            deviation = model.new_int_var(
                0,
                bound,
                f"teacher_participation_deviation_{first}_{second}",
            )
            model.add_abs_equality(
                deviation,
                variables.teacher_loads[first] * capacities[second]
                - variables.teacher_loads[second] * capacities[first],
            )
            deviations.append(deviation)
            variables.teacher_load_pairwise_deviations[(first, second)] = deviation
    return data.settings.optional_balance_weight * cp_model.LinearExpr.sum(deviations)


__all__ = [
    "ObjectiveDirection",
    "ObjectiveStage",
    "TeacherLoad",
    "build_objective_stages",
    "realized_teacher_loads",
    "realized_teacher_active_days",
    "request_spacing_score",
    "worst_request_spacing_quality",
    "teacher_availability_capacities",
    "teacher_participation_imbalance",
    "teacher_preference_penalty",
    "teacher_week_imbalance",
    "student_period_imbalance",
    "maximum_student_week_deviation",
    "maximum_teacher_week_deviation",
]
