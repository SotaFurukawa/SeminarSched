"""段階的なCP-SAT最適化を、安全な結果snapshotを保持しながら実行する。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from ortools.sat.python import cp_model

from summer_scheduler.domain.time_ranges import time_ranges_overlap
from summer_scheduler.optimization.candidates import (
    CandidateGenerationCancelled,
    generate_candidates,
)
from summer_scheduler.optimization.diagnostics import diagnose_unassigned_lessons
from summer_scheduler.optimization.dto import (
    CandidateData,
    CandidateGenerationResult,
    DiagnosticReason,
    ObjectiveBreakdown,
    OptimizationInput,
    OptimizationResult,
    ScheduledAssignment,
    SolverStatus,
    UnassignedLesson,
)
from summer_scheduler.optimization.hard_constraints import (
    HardConstraintInputError,
    OptimizationBuildCancelled,
    add_hard_constraints,
)
from summer_scheduler.optimization.initial_solution import (
    InitialSolutionCancelled,
    build_initial_solution,
    validate_initial_solution,
)
from summer_scheduler.optimization.objectives import (
    ObjectiveStage,
    build_objective_stages,
    realized_teacher_loads,
    teacher_preference_penalty,
)
from summer_scheduler.optimization.result_validation import validate_optimization_result
from summer_scheduler.optimization.sessions import SessionExpansionError, expand_sessions
from summer_scheduler.optimization.variables import ModelVariables, OccupancyKey, SessionKey

Clock = Callable[[], float]
ProgressCallback = Callable[["OptimizationProgress"], None]

_STATUS_NAMES: dict[int, SolverStatus] = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}
_RETURN_RESERVE_MAX_SECONDS = 3.0
_RETURN_RESERVE_RATIO = 0.15
_MINIMUM_NEXT_STAGE_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class OptimizationProgress:
    """UIへ渡してよい、個人情報を含まない進捗情報。"""

    stage_index: int
    stage_count: int
    stage_name: str
    solver_status: SolverStatus | None
    elapsed_seconds: float
    objective_value: int | None = None


@dataclass(frozen=True, slots=True)
class _SolutionSnapshot:
    selected: tuple[CandidateData, ...]
    unassigned: frozenset[SessionKey]
    status: SolverStatus


class CancellationToken:
    """実行中のCpSolverへthread-safeに停止要求を伝える。"""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._solver: cp_model.CpSolver | None = None

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        """停止要求を記録し、solve中ならCP-SATにも伝える。"""
        self._event.set()
        with self._lock:
            solver = self._solver
        if solver is not None:
            solver.stop_search()

    def _bind(self, solver: cp_model.CpSolver) -> None:
        with self._lock:
            self._solver = solver
        if self._event.is_set():
            solver.stop_search()

    def _unbind(self, solver: cp_model.CpSolver) -> None:
        with self._lock:
            if self._solver is solver:
                self._solver = None


def solve_optimization(
    data: OptimizationInput,
    *,
    cancellation: CancellationToken | None = None,
    progress: ProgressCallback | None = None,
    clock: Clock = time.monotonic,
) -> OptimizationResult:
    """全段階で単一deadlineを共有し、検証済み実行可能解だけを返す。

    `UNKNOWN`、`INFEASIBLE`、`MODEL_INVALID`ではsolverの変数値を参照しない。
    後段が時間切れになった場合は、その前までに取得した実行可能snapshotを返す。
    """
    token = cancellation or CancellationToken()
    started_at = clock()
    deadline = started_at + data.settings.time_limit_seconds
    expected_stage_count = 6 if data.settings.optional_balance_weight > 0 else 5
    if progress is not None:
        progress(
            OptimizationProgress(
                stage_index=0,
                stage_count=expected_stage_count,
                stage_name="candidate_generation",
                solver_status=None,
                elapsed_seconds=max(0.0, clock() - started_at),
            )
        )
    try:
        generation = generate_candidates(
            data,
            is_cancelled=lambda: _stop_requested(token, clock, deadline),
        )
    except CandidateGenerationCancelled:
        generation = _cancelled_generation(data)
        cancelled = token.is_cancelled
        return _non_feasible_result(
            data,
            generation,
            status="UNKNOWN",
            elapsed_seconds=max(0.0, clock() - started_at),
            warnings=(
                ("候補生成中に最適化を中止しました",)
                if cancelled
                else ("候補生成中に全体の制限時間に到達しました",)
            ),
            cancelled=cancelled,
        )
    if generation.input_diagnostics:
        return _non_feasible_result(
            data,
            generation,
            status="MODEL_INVALID",
            elapsed_seconds=max(0.0, clock() - started_at),
            warnings=("最適化入力に不整合があるため実行しませんでした",),
            cancelled=token.is_cancelled,
        )

    preparation_warnings: list[str] = []
    initial_snapshot: _SolutionSnapshot | None = None
    if progress is not None:
        progress(
            OptimizationProgress(
                stage_index=0,
                stage_count=expected_stage_count,
                stage_name="initial_solution",
                solver_status=None,
                elapsed_seconds=max(0.0, clock() - started_at),
            )
        )
    try:
        initial_solution = build_initial_solution(
            data,
            generation,
            is_cancelled=lambda: _stop_requested(token, clock, deadline),
        )
    except InitialSolutionCancelled:
        cancelled = token.is_cancelled
        return _non_feasible_result(
            data,
            generation,
            status="UNKNOWN",
            elapsed_seconds=max(0.0, clock() - started_at),
            warnings=(
                ("初期解の構築中に最適化を中止しました",)
                if cancelled
                else ("初期解の構築中に全体の制限時間に到達しました",)
            ),
            cancelled=cancelled,
        )
    if initial_solution is not None:
        initial_report = validate_initial_solution(data, generation, initial_solution)
        if initial_report.is_valid:
            initial_snapshot = _SolutionSnapshot(
                selected=initial_solution.selected_candidates,
                unassigned=frozenset(initial_solution.unassigned_session_keys),
                status="FEASIBLE",
            )
        else:
            preparation_warnings.append(
                "初期解の独立検証に失敗したためCP-SATの結果だけを使用します"
            )
    else:
        preparation_warnings.append(
            "独立検証済みの初期実行可能解を構築できなかったためCP-SATだけを実行します"
        )

    model = cp_model.CpModel()
    variables = ModelVariables()
    if progress is not None:
        progress(
            OptimizationProgress(
                stage_index=0,
                stage_count=expected_stage_count,
                stage_name="model_build",
                solver_status=None,
                elapsed_seconds=max(0.0, clock() - started_at),
            )
        )
    try:
        add_hard_constraints(
            model,
            data,
            generation,
            variables,
            is_cancelled=lambda: _stop_requested(token, clock, deadline),
        )
        stages = build_objective_stages(model, data, generation, variables)
        if initial_snapshot is not None:
            _add_safe_initial_hint(
                model,
                data,
                variables,
                initial_snapshot.selected,
            )
        if _stop_requested(token, clock, deadline):
            raise OptimizationBuildCancelled
    except OptimizationBuildCancelled:
        cancelled = token.is_cancelled
        warning = (
            "モデル構築中に最適化を中止しました"
            if cancelled
            else "モデル構築中に全体の制限時間に到達しました"
        )
        if initial_snapshot is not None:
            return _verified_result_from_snapshot(
                data,
                generation,
                initial_snapshot,
                status="FEASIBLE",
                elapsed_seconds=max(0.0, clock() - started_at),
                warnings=(*preparation_warnings, warning),
                cancelled=cancelled,
            )
        return _non_feasible_result(
            data,
            generation,
            status="UNKNOWN",
            elapsed_seconds=max(0.0, clock() - started_at),
            warnings=(*preparation_warnings, warning),
            cancelled=cancelled,
        )
    except HardConstraintInputError as exc:
        return _non_feasible_result(
            data,
            generation,
            status="MODEL_INVALID",
            elapsed_seconds=max(0.0, clock() - started_at),
            warnings=(f"固定授業またはハード制約の入力が不正です: {exc}",),
            cancelled=token.is_cancelled,
        )

    best = initial_snapshot
    warnings = preparation_warnings
    completed_all_stages = True
    terminal_status: SolverStatus | None = None
    fatal_status: SolverStatus | None = None

    for stage_index, stage in enumerate(stages, start=1):
        if _cancel_requested(token):
            completed_all_stages = False
            warnings.append("利用者の操作により最適化を中止しました")
            break
        remaining = deadline - clock()
        if remaining <= 0:
            completed_all_stages = False
            warnings.append("全体の制限時間に到達しました")
            break
        if stage_index > 1 and best is not None and remaining < _MINIMUM_NEXT_STAGE_SECONDS:
            completed_all_stages = False
            warnings.append("残り時間が短いため次の辞書式最適化段階を開始しませんでした")
            break

        _set_objective(model, stage)
        if best is not None:
            incumbent_value = _snapshot_stage_value(data, generation, best, stage)
            if stage.direction == "minimize":
                model.add(stage.expression <= incumbent_value)
            else:
                model.add(stage.expression >= incumbent_value)
        if progress is not None:
            progress(
                OptimizationProgress(
                    stage_index=stage_index,
                    stage_count=len(stages),
                    stage_name=stage.name,
                    solver_status=None,
                    elapsed_seconds=max(0.0, clock() - started_at),
                )
            )

        if stage_index == 1 and initial_snapshot is not None and not initial_snapshot.unassigned:
            model.add(stage.expression == 0)
            terminal_status = "OPTIMAL"
            if progress is not None:
                progress(
                    OptimizationProgress(
                        stage_index=stage_index,
                        stage_count=len(stages),
                        stage_name=stage.name,
                        solver_status="OPTIMAL",
                        elapsed_seconds=max(0.0, clock() - started_at),
                        objective_value=0,
                    )
                )
            continue

        solver = cp_model.CpSolver()
        _configure_solver(solver, data, remaining)
        token._bind(solver)
        try:
            if _cancel_requested(token):
                completed_all_stages = False
                warnings.append("利用者の操作により最適化を中止しました")
                break
            raw_status = int(solver.solve(model))
        finally:
            token._unbind(solver)

        run_status = _STATUS_NAMES.get(raw_status)
        if run_status is None:
            raise RuntimeError(f"CP-SATが未知のstatusを返しました: {raw_status}")
        terminal_status = run_status

        objective_value: int | None = None
        if run_status in ("OPTIMAL", "FEASIBLE"):
            objective_value = _integer_value(solver, stage)
            best = _extract_snapshot(solver, variables, run_status)

        if progress is not None:
            progress(
                OptimizationProgress(
                    stage_index=stage_index,
                    stage_count=len(stages),
                    stage_name=stage.name,
                    solver_status=run_status,
                    elapsed_seconds=max(0.0, clock() - started_at),
                    objective_value=objective_value,
                )
            )

        if run_status == "OPTIMAL":
            if objective_value is None:
                raise RuntimeError("OPTIMALなのに目的値を取得できませんでした")
            model.add(stage.expression == objective_value)
            if best is not None:
                _add_safe_initial_hint(model, data, variables, best.selected)
            continue

        completed_all_stages = False
        if run_status == "FEASIBLE":
            warnings.append(f"段階「{stage.name}」は制限時間内に最適性を証明できませんでした")
        elif run_status == "UNKNOWN":
            warnings.append(f"段階「{stage.name}」では実行可能解を取得できませんでした")
        elif run_status == "INFEASIBLE":
            warnings.append(f"段階「{stage.name}」でモデルが実行不能と判定されました")
            fatal_status = run_status
        else:
            warnings.append(f"段階「{stage.name}」でモデル不正が検出されました")
            fatal_status = run_status
        break

    elapsed_seconds = max(0.0, clock() - started_at)
    if fatal_status is not None:
        return _non_feasible_result(
            data,
            generation,
            status=fatal_status,
            elapsed_seconds=elapsed_seconds,
            warnings=tuple(warnings),
            cancelled=token.is_cancelled,
        )
    if best is None:
        no_solution_status: SolverStatus = terminal_status or "UNKNOWN"
        return _non_feasible_result(
            data,
            generation,
            status=no_solution_status,
            elapsed_seconds=elapsed_seconds,
            warnings=tuple(warnings),
            cancelled=token.is_cancelled,
        )

    final_status: SolverStatus = (
        "OPTIMAL" if completed_all_stages and best.status == "OPTIMAL" else "FEASIBLE"
    )
    result = _result_from_snapshot(
        data,
        generation,
        best,
        status=final_status,
        elapsed_seconds=elapsed_seconds,
        warnings=tuple(warnings),
        cancelled=token.is_cancelled,
    )
    report = validate_optimization_result(data, generation, result)
    if not report.is_valid:
        codes = ", ".join(violation.code.value for violation in report.violations)
        return _non_feasible_result(
            data,
            generation,
            status="MODEL_INVALID",
            elapsed_seconds=elapsed_seconds,
            warnings=(f"独立検証でハード制約違反を検出しました: {codes}",),
            cancelled=token.is_cancelled,
        )
    return result


def _cancel_requested(token: CancellationToken) -> bool:
    """callback等による並行変更を各安全点で読み直す。"""
    return token.is_cancelled


def _stop_requested(token: CancellationToken, clock: Clock, deadline: float) -> bool:
    """候補・モデル構築にも、solve段階と同じ全体deadlineを適用する。"""
    return _cancel_requested(token) or clock() >= deadline


def _cancelled_generation(data: OptimizationInput) -> CandidateGenerationResult:
    try:
        sessions = expand_sessions(data.lesson_requests)
    except SessionExpansionError:
        sessions = ()
    return CandidateGenerationResult(
        sessions=sessions,
        candidates=(),
        diagnostics=(),
    )


def _configure_solver(
    solver: cp_model.CpSolver,
    data: OptimizationInput,
    remaining_seconds: float,
) -> None:
    # CP-SAT停止後のsnapshot抽出、独立検証、診断にも同じ全体deadline内の時間を残す。
    reserve = min(
        _RETURN_RESERVE_MAX_SECONDS,
        remaining_seconds * _RETURN_RESERVE_RATIO,
    )
    solver.parameters.max_time_in_seconds = max(0.001, remaining_seconds - reserve)
    solver.parameters.random_seed = data.settings.random_seed
    solver.parameters.num_search_workers = data.settings.num_search_workers
    solver.parameters.log_search_progress = False
    solver.parameters.log_to_stdout = False


def _set_objective(model: cp_model.CpModel, stage: ObjectiveStage) -> None:
    if stage.direction == "minimize":
        model.minimize(stage.expression)
    else:
        model.maximize(stage.expression)


def _add_safe_initial_hint(
    model: cp_model.CpModel,
    data: OptimizationInput,
    variables: ModelVariables,
    selected: tuple[CandidateData, ...] | None = None,
) -> None:
    """主変数と補助変数を含む、決定論的な完全hintを設定する。

    `selected`を省略した場合はロック済みセッションだけを元の候補へ戻す。呼出側は
    hintを実行可能解として採用する前に独立validatorを通す。ここではCP-SATがpartial
    hintの補完に探索時間を費やさないよう、全ての派生値も同じ配置から計算する。
    """
    locked_positions = {
        (
            item.lesson_request_id,
            item.session_index,
            item.day,
            item.time_slot_id,
            item.teacher_id,
        )
        for item in data.existing_assignments
        if item.is_locked
    }
    selected_candidates = (
        frozenset(selected)
        if selected is not None
        else frozenset(
            candidate
            for candidate in variables.assignments
            if (
                candidate.lesson_request_id,
                candidate.session_index,
                candidate.day,
                candidate.time_slot_id,
                candidate.teacher_id,
            )
            in locked_positions
        )
    )
    selected_sessions = {candidate.session_key for candidate in selected_candidates}
    hinted_values: dict[int, int] = {}

    def add_hint(variable: cp_model.IntVar, value: int) -> None:
        model.add_hint(variable, value)
        hinted_values[variable.index] = value

    model.clear_hints()  # type: ignore[no-untyped-call]
    for candidate, variable in variables.assignments.items():
        add_hint(variable, int(candidate in selected_candidates))
    for session_identity, variable in variables.unassigned.items():
        add_hint(variable, int(session_identity not in selected_sessions))

    student_occupancy = {
        (candidate.student_id, candidate.day, candidate.time_slot_id)
        for candidate in selected_candidates
    }
    teacher_occupancy = {
        (candidate.teacher_id, candidate.day, candidate.time_slot_id)
        for candidate in selected_candidates
    }
    slots = tuple(sorted(data.time_slots, key=lambda item: (item.sort_order, item.id)))
    for block in data.group_blocks:
        for slot in slots:
            if not time_ranges_overlap(
                slot.start_time,
                slot.end_time,
                block.start_time,
                block.end_time,
            ):
                continue
            student_occupancy.update(
                (student_id, block.day, slot.id) for student_id in block.student_ids
            )
            if block.teacher_id is not None:
                teacher_occupancy.add((block.teacher_id, block.day, slot.id))

    student_active_values: dict[OccupancyKey, int] = {}
    teacher_active_values: dict[OccupancyKey, int] = {}
    for occupancy_key, variable in variables.student_active.items():
        value = int(occupancy_key in student_occupancy)
        student_active_values[occupancy_key] = value
        add_hint(variable, value)
    for occupancy_key, variable in variables.teacher_active.items():
        value = int(occupancy_key in teacher_occupancy)
        teacher_active_values[occupancy_key] = value
        add_hint(variable, value)

    slot_position = {slot.id: position for position, slot in enumerate(slots)}
    for starts, active_values in (
        (variables.student_starts, student_active_values),
        (variables.teacher_starts, teacher_active_values),
    ):
        for occupancy_key, variable in starts.items():
            owner_id, day, slot_id = occupancy_key
            position = slot_position[slot_id]
            previous = (
                0 if position == 0 else active_values[(owner_id, day, slots[position - 1].id)]
            )
            value = int(active_values[occupancy_key] == 1 and previous == 0)
            add_hint(variable, value)

    for indicator, selections in variables.selection_indicators:
        add_hint(
            indicator,
            int(any(hinted_values[selection.index] for selection in selections)),
        )

    load_values: list[int] = []
    for teacher_id, variable in sorted(variables.teacher_loads.items()):
        value = sum(
            active
            for (owner_id, _day, _slot_id), active in teacher_active_values.items()
            if owner_id == teacher_id
        )
        load_values.append(value)
        add_hint(variable, value)
    if variables.teacher_load_maximum is not None:
        add_hint(variables.teacher_load_maximum, max(load_values, default=0))
    if variables.teacher_load_minimum is not None:
        add_hint(variables.teacher_load_minimum, min(load_values, default=0))


def _integer_value(solver: cp_model.CpSolver, stage: ObjectiveStage) -> int:
    value = solver.value(stage.expression)
    rounded = round(value)
    if abs(value - rounded) > 1e-6:
        raise RuntimeError(f"辞書式目的値が整数ではありません: {value}")
    return int(rounded)


def _snapshot_stage_value(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    snapshot: _SolutionSnapshot,
    stage: ObjectiveStage,
) -> int:
    """既知の実行可能snapshotにおける現段階の目的値を返す。"""
    breakdown = _objective_breakdown(
        data,
        generation,
        snapshot.selected,
        snapshot.unassigned,
    )
    values = {
        "unassigned_count": breakdown.unassigned_count,
        "teacher_preference_penalty": breakdown.teacher_preference_penalty,
        "active_teacher_slot_count": breakdown.active_teacher_slot_count,
        "availability_preference_score": breakdown.availability_preference_score,
        "changed_assignment_count": (
            breakdown.changed_assignment_count * data.settings.preserve_existing_assignment_weight
        ),
        "teacher_load_imbalance": (
            breakdown.optional_balance_score * data.settings.optional_balance_weight
        ),
    }
    try:
        return values[stage.name]
    except KeyError as exc:
        raise RuntimeError(f"未知の辞書式目的段階です: {stage.name}") from exc


def _extract_snapshot(
    solver: cp_model.CpSolver,
    variables: ModelVariables,
    status: SolverStatus,
) -> _SolutionSnapshot:
    selected = tuple(
        candidate
        for candidate, variable in variables.assignments.items()
        if solver.boolean_value(variable)
    )
    unassigned = frozenset(
        key for key, variable in variables.unassigned.items() if solver.boolean_value(variable)
    )
    return _SolutionSnapshot(
        selected=tuple(
            sorted(
                selected,
                key=lambda item: (
                    item.lesson_request_id,
                    item.session_index,
                    item.day,
                    item.time_slot_id,
                    item.teacher_id,
                ),
            )
        ),
        unassigned=unassigned,
        status=status,
    )


def _verified_result_from_snapshot(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    snapshot: _SolutionSnapshot,
    *,
    status: SolverStatus,
    elapsed_seconds: float,
    warnings: tuple[str, ...],
    cancelled: bool,
) -> OptimizationResult:
    """snapshotを公開結果へ変換し、返却直前にも独立検証する。"""
    result = _result_from_snapshot(
        data,
        generation,
        snapshot,
        status=status,
        elapsed_seconds=elapsed_seconds,
        warnings=warnings,
        cancelled=cancelled,
    )
    report = validate_optimization_result(data, generation, result)
    if report.is_valid:
        return result
    codes = ", ".join(violation.code.value for violation in report.violations)
    return _non_feasible_result(
        data,
        generation,
        status="MODEL_INVALID",
        elapsed_seconds=elapsed_seconds,
        warnings=(f"独立検証でハード制約違反を検出しました: {codes}",),
        cancelled=cancelled,
    )


def _result_from_snapshot(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    snapshot: _SolutionSnapshot,
    *,
    status: SolverStatus,
    elapsed_seconds: float,
    warnings: tuple[str, ...],
    cancelled: bool,
) -> OptimizationResult:
    locked_keys = {
        (item.lesson_request_id, item.session_index)
        for item in data.existing_assignments
        if item.is_locked
    }
    assignments = tuple(
        ScheduledAssignment(
            lesson_request_id=item.lesson_request_id,
            session_index=item.session_index,
            student_id=item.student_id,
            subject_id=item.subject_id,
            teacher_id=item.teacher_id,
            day=item.day,
            time_slot_id=item.time_slot_id,
            is_locked=(item.lesson_request_id, item.session_index) in locked_keys,
        )
        for item in snapshot.selected
    )
    preliminary_unassigned = tuple(
        UnassignedLesson(
            lesson_request_id=session.lesson_request_id,
            session_index=session.session_index,
            student_id=session.student_id,
            subject_id=session.subject_id,
            reasons=(),
        )
        for session in generation.sessions
        if session.key in snapshot.unassigned
    )
    preliminary = OptimizationResult(
        solver_status=status,
        assignments=assignments,
        unassigned_lessons=preliminary_unassigned,
        objective_breakdown=_objective_breakdown(
            data,
            generation,
            snapshot.selected,
            snapshot.unassigned,
        ),
        elapsed_seconds=elapsed_seconds,
        warnings=warnings,
        cancelled=cancelled,
    )
    return replace(
        preliminary,
        unassigned_lessons=diagnose_unassigned_lessons(data, generation, preliminary),
    )


def _objective_breakdown(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    selected: tuple[CandidateData, ...],
    unassigned: frozenset[SessionKey],
) -> ObjectiveBreakdown:
    requests = {item.id: item for item in data.lesson_requests}
    settings = data.settings
    preference_penalty = 0
    availability_score = 0
    for candidate in selected:
        request = requests[candidate.lesson_request_id]
        preference_penalty += teacher_preference_penalty(
            request,
            candidate.teacher_id,
            settings,
        )
        if candidate.student_availability_level == 2:
            availability_score += settings.student_preferred_time_weight
        if candidate.teacher_availability_level == 2:
            availability_score += settings.teacher_preferred_time_weight

    selected_keys = {
        (
            item.lesson_request_id,
            item.session_index,
            item.day,
            item.time_slot_id,
            item.teacher_id,
        )
        for item in selected
    }
    changed = sum(
        (
            item.lesson_request_id,
            item.session_index,
            item.day,
            item.time_slot_id,
            item.teacher_id,
        )
        not in selected_keys
        for item in data.existing_assignments
        if not item.is_locked
    )
    loads = realized_teacher_loads(data, generation, selected)
    balance_score = max(loads.values(), default=0) - min(loads.values(), default=0)
    return ObjectiveBreakdown(
        unassigned_count=len(unassigned),
        teacher_preference_penalty=preference_penalty,
        active_teacher_slot_count=sum(loads.values()),
        availability_preference_score=availability_score,
        changed_assignment_count=changed,
        optional_balance_score=balance_score,
    )


def _non_feasible_result(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    *,
    status: SolverStatus,
    elapsed_seconds: float,
    warnings: tuple[str, ...],
    cancelled: bool,
) -> OptimizationResult:
    request_by_id = {item.id: item for item in data.lesson_requests}
    unassigned: list[UnassignedLesson] = []
    for session in generation.sessions:
        diagnostic = generation.diagnostics_for(*session.key)
        reasons: tuple[DiagnosticReason, ...] = (
            diagnostic.reasons if diagnostic is not None else generation.input_diagnostics
        )
        request = request_by_id.get(session.lesson_request_id)
        unassigned.append(
            UnassignedLesson(
                lesson_request_id=session.lesson_request_id,
                session_index=session.session_index,
                student_id=session.student_id if request is None else request.student_id,
                subject_id=session.subject_id if request is None else request.subject_id,
                reasons=reasons,
            )
        )
    return OptimizationResult(
        solver_status=status,
        assignments=(),
        unassigned_lessons=tuple(unassigned),
        objective_breakdown=ObjectiveBreakdown(unassigned_count=len(unassigned)),
        elapsed_seconds=elapsed_seconds,
        warnings=warnings,
        cancelled=cancelled,
    )


__all__ = [
    "CancellationToken",
    "OptimizationProgress",
    "ProgressCallback",
    "solve_optimization",
]
