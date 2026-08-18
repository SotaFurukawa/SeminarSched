"""独立検証済み初期解から作るCP-SAT完全hintの契約。"""

from __future__ import annotations

from dataclasses import replace

from ortools.sat.python import cp_model
from tools.benchmark_phase4 import BenchmarkConfig, build_synthetic_input

from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.hard_constraints import add_hard_constraints
from summer_scheduler.optimization.initial_solution import (
    build_initial_solution,
    validate_initial_solution,
)
from summer_scheduler.optimization.objectives import build_objective_stages
from summer_scheduler.optimization.solver import (
    _add_safe_initial_hint,
    _configure_solver,
    _snapshot_stage_value,
    _SolutionSnapshot,
)
from summer_scheduler.optimization.variables import ModelVariables


def test_verified_initial_solution_produces_complete_feasible_hint() -> None:
    data = build_synthetic_input(
        BenchmarkConfig(
            students=2,
            teachers=2,
            days=2,
            slots_per_day=2,
            subjects=2,
            requests_per_student=1,
            sessions_pattern=(1,),
            student_available_days=2,
            student_slots_per_day=2,
            teacher_available_day_ratio=1.0,
            teacher_slots_per_day=2,
            qualifications_per_teacher=2,
            time_limit_seconds=5,
        )
    )
    generation = generate_candidates(data)
    initial = build_initial_solution(data, generation)

    assert initial is not None
    assert validate_initial_solution(data, generation, initial).is_valid

    model = cp_model.CpModel()
    variables = ModelVariables()
    add_hard_constraints(model, data, generation, variables)
    stages = build_objective_stages(model, data, generation, variables)
    _add_safe_initial_hint(model, data, variables, initial.selected_candidates)
    model.minimize(stages[0].expression)

    hint_indices = list(model.proto.solution_hint.vars)
    assert len(hint_indices) == len(set(hint_indices))
    missing = set(range(len(model.proto.variables))) - set(hint_indices)
    assert all(
        len(model.proto.variables[index].domain) == 2
        and model.proto.variables[index].domain[0] == model.proto.variables[index].domain[1]
        for index in missing
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    solver.parameters.num_search_workers = 1
    solver.parameters.fix_variables_to_their_hinted_value = True
    status = solver.solve(model)

    assert status in {cp_model.FEASIBLE, cp_model.OPTIMAL}
    assert round(solver.objective_value) == len(initial.unassigned_session_keys)


def test_optional_balance_variables_are_also_hinted() -> None:
    data = build_synthetic_input(
        BenchmarkConfig(
            students=1,
            teachers=2,
            days=1,
            slots_per_day=1,
            subjects=1,
            requests_per_student=1,
            sessions_pattern=(1,),
            student_available_days=1,
            student_slots_per_day=1,
            teacher_available_day_ratio=1.0,
            teacher_slots_per_day=1,
            qualifications_per_teacher=1,
            time_limit_seconds=5,
        )
    )
    data = replace(
        data,
        settings=replace(data.settings, optional_balance_weight=1),
    )
    generation = generate_candidates(data)
    initial = build_initial_solution(data, generation)
    assert initial is not None

    model = cp_model.CpModel()
    variables = ModelVariables()
    add_hard_constraints(model, data, generation, variables)
    stages = build_objective_stages(model, data, generation, variables)
    _add_safe_initial_hint(model, data, variables, initial.selected_candidates)

    hinted = set(model.proto.solution_hint.vars)
    assert all(variable.index in hinted for variable in variables.teacher_loads.values())
    assert variables.teacher_load_pairwise_deviations
    assert all(
        variable.index in hinted for variable in variables.teacher_load_pairwise_deviations.values()
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    solver.parameters.num_search_workers = 1
    solver.parameters.fix_variables_to_their_hinted_value = True
    assert solver.solve(model) in {cp_model.FEASIBLE, cp_model.OPTIMAL}

    snapshot = _SolutionSnapshot(
        selected=initial.selected_candidates,
        unassigned=frozenset(initial.unassigned_session_keys),
        status="FEASIBLE",
    )
    for stage in stages:
        assert round(solver.value(stage.expression)) == _snapshot_stage_value(
            data,
            generation,
            snapshot,
            stage,
        )


def test_solver_reserves_time_for_result_validation() -> None:
    data = build_synthetic_input(
        BenchmarkConfig(
            students=1,
            teachers=1,
            days=1,
            slots_per_day=1,
            subjects=1,
            requests_per_student=1,
            sessions_pattern=(1,),
            student_available_days=1,
            student_slots_per_day=1,
            teacher_available_day_ratio=1.0,
            teacher_slots_per_day=1,
            qualifications_per_teacher=1,
            time_limit_seconds=30,
        )
    )
    solver = cp_model.CpSolver()

    _configure_solver(solver, data, 20.0)

    assert solver.parameters.max_time_in_seconds == 17.0
