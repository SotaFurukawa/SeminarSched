"""段階目的関数の係数と固定予定の扱いを検証する。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time

from ortools.sat.python import cp_model

from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    CandidateData,
    CandidateGenerationResult,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    LessonSessionData,
    OptimizationInput,
    OptimizationSettings,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
)
from summer_scheduler.optimization.hard_constraints import add_hard_constraints
from summer_scheduler.optimization.objectives import (
    ObjectiveStage,
    build_objective_stages,
    realized_teacher_loads,
    teacher_preference_penalty,
)
from summer_scheduler.optimization.variables import ModelVariables

DAY = date(2026, 8, 3)
SLOTS = (
    TimeSlotData(
        id=100,
        code="Y",
        display_name="Yコマ",
        start_time=time(14, 0),
        end_time=time(15, 0),
        sort_order=1,
    ),
    TimeSlotData(
        id=101,
        code="Z",
        display_name="Zコマ",
        start_time=time(15, 10),
        end_time=time(16, 10),
        sort_order=2,
    ),
)


def test_builds_required_stages_and_enables_balance_only_for_positive_weight() -> None:
    data = _input()
    model = cp_model.CpModel()

    stages = build_objective_stages(
        model,
        data,
        CandidateGenerationResult(sessions=(), candidates=(), diagnostics=()),
        ModelVariables(),
    )

    assert [(stage.name, stage.direction) for stage in stages] == [
        ("unassigned_count", "minimize"),
        ("teacher_preference_penalty", "minimize"),
        ("active_teacher_slot_count", "minimize"),
        ("availability_preference_score", "maximize"),
        ("changed_assignment_count", "minimize"),
    ]

    enabled = replace(
        data,
        settings=replace(data.settings, optional_balance_weight=2),
    )
    enabled_stages = build_objective_stages(
        cp_model.CpModel(),
        enabled,
        CandidateGenerationResult(sessions=(), candidates=(), diagnostics=()),
        ModelVariables(),
    )
    assert enabled_stages[-1].name == "teacher_load_imbalance"
    assert enabled_stages[-1].direction == "minimize"


def test_teacher_preference_uses_request_max_and_never_adds_duplicate_scores() -> None:
    settings = _settings()
    request = _request(
        regular_teacher_id=10,
        regular_teacher_priority=4,
        preferred_teacher_ids=(10, 20, 10),
    )

    assert teacher_preference_penalty(request, 10, settings) == 0
    assert teacher_preference_penalty(request, 20, settings) == 4
    assert teacher_preference_penalty(request, 30, settings) == 10

    rank_hole = _request(preferred_teacher_ids=(None, 20, None))
    assert teacher_preference_penalty(rank_hole, 20, settings) == 0
    assert teacher_preference_penalty(rank_hole, 30, settings) == 6
    hard_priority = _request(
        regular_teacher_id=10,
        regular_teacher_priority=5,
        preferred_teacher_ids=(20, None, None),
    )
    assert teacher_preference_penalty(hard_priority, 10, settings) == 0

    candidate = _candidate(teacher_id=20)
    model, stages = _fixed_candidate_model(request, (candidate,), selected=candidate)
    assert _solve_value(model, _stage(stages, "teacher_preference_penalty")) == 4


def test_unassigned_and_level_two_availability_have_separate_integer_objectives() -> None:
    request = _request()
    candidate = _candidate(
        teacher_id=10,
        student_availability_level=2,
        teacher_availability_level=2,
    )
    data = _input(
        requests=(request,),
        settings=replace(
            _settings(),
            student_preferred_time_weight=2,
            teacher_preferred_time_weight=3,
        ),
    )

    selected_model, selected_stages = _fixed_candidate_model(
        request,
        (candidate,),
        selected=candidate,
        data=data,
    )
    assert (
        _solve_value(
            selected_model,
            _stage(selected_stages, "unassigned_count"),
        )
        == 0
    )
    assert (
        _solve_value(
            selected_model,
            _stage(selected_stages, "availability_preference_score"),
        )
        == 5
    )

    unassigned_model, unassigned_stages = _fixed_candidate_model(
        request,
        (candidate,),
        selected=None,
        data=data,
    )
    assert (
        _solve_value(
            unassigned_model,
            _stage(unassigned_stages, "unassigned_count"),
        )
        == 1
    )
    assert (
        _solve_value(
            unassigned_model,
            _stage(unassigned_stages, "availability_preference_score"),
        )
        == 0
    )


def test_existing_unlocked_assignment_penalizes_every_non_exact_result() -> None:
    request = _request()
    exact = _candidate(teacher_id=10, time_slot_id=100)
    alternative = _candidate(teacher_id=20, time_slot_id=101)
    existing = ExistingAssignmentData(
        id=1,
        lesson_request_id=request.id,
        session_index=1,
        day=DAY,
        time_slot_id=100,
        teacher_id=10,
    )
    data = _input(
        requests=(request,),
        existing=(existing,),
        settings=replace(_settings(), preserve_existing_assignment_weight=3),
    )

    exact_model, exact_stages = _fixed_candidate_model(
        request,
        (exact, alternative),
        selected=exact,
        data=data,
    )
    assert (
        _solve_value(
            exact_model,
            _stage(exact_stages, "changed_assignment_count"),
        )
        == 0
    )

    changed_model, changed_stages = _fixed_candidate_model(
        request,
        (exact, alternative),
        selected=alternative,
        data=data,
    )
    assert (
        _solve_value(
            changed_model,
            _stage(changed_stages, "changed_assignment_count"),
        )
        == 3
    )

    unassigned_model, unassigned_stages = _fixed_candidate_model(
        request,
        (exact, alternative),
        selected=None,
        data=data,
    )
    assert (
        _solve_value(
            unassigned_model,
            _stage(unassigned_stages, "changed_assignment_count"),
        )
        == 3
    )


def test_fixed_group_slots_are_constants_in_active_count_and_load_balance() -> None:
    request = _request()
    group = GroupBlockData(
        id=1,
        day=DAY,
        start_time=time(14, 30),
        end_time=time(16, 0),
        teacher_id=20,
    )
    data = _input(
        requests=(request,),
        groups=(group,),
        settings=replace(_settings(), optional_balance_weight=3),
        availabilities=(
            AvailabilityData("student", 1, DAY, 100, 1),
            AvailabilityData("teacher", 10, DAY, 100, 1),
        ),
    )
    generation = generate_candidates(data)
    assert len(generation.candidates) == 1

    model = cp_model.CpModel()
    variables = ModelVariables()
    add_hard_constraints(model, data, generation, variables)
    selected = generation.candidates[0]
    model.add(variables.assignments[selected] == 1)
    stages = build_objective_stages(model, data, generation, variables)

    assert _solve_value(model, _stage(stages, "active_teacher_slot_count")) == 3
    assert _solve_value(model, _stage(stages, "teacher_load_imbalance")) == 3
    assert realized_teacher_loads(data, generation, (selected,)) == {10: 1, 20: 2}


def _fixed_candidate_model(
    request: LessonRequestData,
    candidates: tuple[CandidateData, ...],
    *,
    selected: CandidateData | None,
    data: OptimizationInput | None = None,
) -> tuple[cp_model.CpModel, tuple[ObjectiveStage, ...]]:
    source = data or _input(requests=(request,))
    session = LessonSessionData(
        lesson_request_id=request.id,
        session_index=1,
        student_id=request.student_id,
        subject_id=request.subject_id,
        one_to_one_required=request.one_to_one_required,
        max_consecutive_slots_override=request.max_consecutive_slots_override,
        allow_gap_override=request.allow_gap_override,
    )
    generation = CandidateGenerationResult(
        sessions=(session,),
        candidates=candidates,
        diagnostics=(),
    )
    model = cp_model.CpModel()
    variables = ModelVariables(
        assignments={
            candidate: model.new_bool_var(f"candidate_{index}")
            for index, candidate in enumerate(candidates)
        },
        unassigned={session.key: model.new_bool_var("unassigned")},
    )
    for candidate, variable in variables.assignments.items():
        model.add(variable == int(candidate == selected))
    model.add(variables.unassigned[session.key] == int(selected is None))
    return model, build_objective_stages(model, source, generation, variables)


def _solve_value(model: cp_model.CpModel, stage: ObjectiveStage) -> int:
    solver = cp_model.CpSolver()
    assert solver.solve(model) == cp_model.OPTIMAL
    return int(solver.value(stage.expression))


def _stage(stages: tuple[ObjectiveStage, ...], name: str) -> ObjectiveStage:
    return next(stage for stage in stages if stage.name == name)


def _input(
    *,
    requests: tuple[LessonRequestData, ...] = (),
    existing: tuple[ExistingAssignmentData, ...] = (),
    groups: tuple[GroupBlockData, ...] = (),
    settings: OptimizationSettings | None = None,
    availabilities: tuple[AvailabilityData, ...] = (),
) -> OptimizationInput:
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY,),
        time_slots=SLOTS,
        students=(StudentData(id=1, display_name="架空生徒"),),
        teachers=tuple(
            TeacherData(
                id=teacher_id,
                display_name=f"架空講師{teacher_id}",
                qualified_subject_ids=frozenset({500}),
            )
            for teacher_id in (10, 20, 30)
        ),
        subjects=(SubjectData(id=500, code="MATH", display_name="数学"),),
        lesson_requests=requests,
        availabilities=availabilities,
        group_blocks=groups,
        existing_assignments=existing,
        settings=settings or _settings(),
    )


def _settings() -> OptimizationSettings:
    return OptimizationSettings(
        time_limit_seconds=30,
        random_seed=7,
        num_search_workers=1,
        regular_teacher_priority_weights=(1, 3, 6, 10),
        preferred_teacher_rank_weights=(9, 6, 3),
        student_preferred_time_weight=1,
        teacher_preferred_time_weight=1,
        preserve_existing_assignment_weight=1,
        optional_balance_weight=0,
    )


def _request(
    *,
    regular_teacher_id: int | None = None,
    regular_teacher_priority: int = 1,
    preferred_teacher_ids: tuple[int | None, int | None, int | None] = (
        None,
        None,
        None,
    ),
) -> LessonRequestData:
    return LessonRequestData(
        id=1000,
        student_id=1,
        subject_id=500,
        required_sessions=1,
        regular_teacher_id=regular_teacher_id,
        regular_teacher_priority=regular_teacher_priority,
        preferred_teacher_ids=preferred_teacher_ids,
    )


def _candidate(
    *,
    teacher_id: int,
    time_slot_id: int = 100,
    student_availability_level: int = 1,
    teacher_availability_level: int = 1,
) -> CandidateData:
    return CandidateData(
        lesson_request_id=1000,
        session_index=1,
        student_id=1,
        subject_id=500,
        teacher_id=teacher_id,
        day=DAY,
        time_slot_id=time_slot_id,
        student_availability_level=student_availability_level,
        teacher_availability_level=teacher_availability_level,
    )
