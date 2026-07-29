"""Phase 4の上書き規則、固定予定、中断時snapshotの境界シナリオ。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time
from typing import Any, ClassVar

import pytest
from ortools.sat.python import cp_model

from summer_scheduler.optimization.dto import (
    AvailabilityData,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    OptimizationInput,
    OptimizationSettings,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
)
from summer_scheduler.optimization.solver import (
    CancellationToken,
    OptimizationProgress,
    solve_optimization,
)

DAY = date(2026, 8, 3)
SUBJECT = SubjectData(id=1, code="MATH", display_name="架空数学")
_REAL_CP_SOLVER = cp_model.CpSolver


def test_request_override_three_takes_priority_over_student_default_two() -> None:
    request = replace(
        _request(sessions=3),
        max_consecutive_slots_override=3,
    )
    source = _input(
        student=_student(max_consecutive=2),
        teacher=_teacher(),
        requests=(request,),
        slots=_slots(3),
    )

    result = solve_optimization(source)

    assert result.solver_status == "OPTIMAL"
    assert len(result.assignments) == 3
    assert not result.unassigned_lessons
    assert {assignment.time_slot_id for assignment in result.assignments} == {1, 2, 3}


def test_request_allow_gap_true_overrides_strict_student_default() -> None:
    request = replace(_request(sessions=2), allow_gap_override=True)
    source = _input(
        student=_student(allow_gap=False),
        teacher=_teacher(allow_gap=True),
        requests=(request,),
        slots=_slots(3),
        student_slots={1, 3},
        teacher_slots={1, 3},
    )

    result = solve_optimization(source)

    assert result.solver_status == "OPTIMAL"
    assert len(result.assignments) == 2
    assert not result.unassigned_lessons
    assert {assignment.time_slot_id for assignment in result.assignments} == {1, 3}


def test_one_strict_request_keeps_mixed_student_day_contiguous() -> None:
    strict = replace(
        _request(request_id=1),
        allow_gap_override=False,
    )
    permissive = replace(
        _request(request_id=2),
        allow_gap_override=True,
    )
    source = _input(
        student=_student(allow_gap=True),
        teacher=_teacher(allow_gap=True),
        requests=(strict, permissive),
        slots=_slots(3),
        student_slots={1, 3},
        teacher_slots={1, 3},
    )

    result = solve_optimization(source)

    assert result.solver_status == "OPTIMAL"
    assert len(result.assignments) == 1
    assert len(result.unassigned_lessons) == 1
    assert {assignment.time_slot_id for assignment in result.assignments} <= {1, 3}


def test_disabled_middle_slot_does_not_make_outer_slots_adjacent() -> None:
    first, middle, last = _slots(3)
    slots = (first, replace(middle, enabled=False), last)
    source = _input(
        student=_student(allow_gap=False),
        teacher=_teacher(allow_gap=True),
        requests=(_request(sessions=2),),
        slots=slots,
        student_slots={1, 3},
        teacher_slots={1, 3},
    )

    result = solve_optimization(source)

    assert result.solver_status == "OPTIMAL"
    assert len(result.assignments) == 1
    assert len(result.unassigned_lessons) == 1
    assert all(assignment.time_slot_id != 2 for assignment in result.assignments)


def test_fixed_group_in_middle_fills_the_student_gap() -> None:
    slots = _slots(3)
    source = _input(
        student=_student(max_consecutive=3, allow_gap=False),
        teacher=_teacher(allow_gap=True),
        requests=(_request(sessions=2),),
        slots=slots,
        student_slots={1, 3},
        teacher_slots={1, 3},
        groups=(
            GroupBlockData(
                id=1,
                day=DAY,
                start_time=slots[1].start_time,
                end_time=slots[1].end_time,
                student_ids=frozenset({1}),
            ),
        ),
    )

    result = solve_optimization(source)

    assert result.solver_status == "OPTIMAL"
    assert len(result.assignments) == 2
    assert not result.unassigned_lessons
    assert {assignment.time_slot_id for assignment in result.assignments} == {1, 3}


def test_locked_assignment_conflicting_with_group_fails_closed() -> None:
    slot = _slots(1)[0]
    source = _input(
        student=_student(),
        teacher=_teacher(),
        requests=(_request(),),
        slots=(slot,),
        groups=(
            GroupBlockData(
                id=1,
                day=DAY,
                start_time=slot.start_time,
                end_time=slot.end_time,
                teacher_id=1,
            ),
        ),
        existing=(
            ExistingAssignmentData(
                id=1,
                lesson_request_id=1,
                session_index=1,
                day=DAY,
                time_slot_id=1,
                teacher_id=1,
                is_locked=True,
            ),
        ),
    )

    result = solve_optimization(source)

    assert result.solver_status == "MODEL_INVALID"
    assert not result.assignments
    assert len(result.unassigned_lessons) == 1
    assert any("固定授業" in warning for warning in result.warnings)


def test_cancellation_before_first_solution_returns_no_assignment() -> None:
    source = _input(
        student=_student(),
        teacher=_teacher(),
        requests=(_request(),),
        slots=_slots(1),
    )
    cancellation = CancellationToken()

    def cancel_at_first_stage(progress: OptimizationProgress) -> None:
        if progress.solver_status is None:
            cancellation.cancel()

    result = solve_optimization(
        source,
        cancellation=cancellation,
        progress=cancel_at_first_stage,
    )

    assert result.solver_status == "UNKNOWN"
    assert result.cancelled
    assert not result.assignments
    assert len(result.unassigned_lessons) == 1
    assert any("中止" in warning for warning in result.warnings)


def test_unknown_in_later_stage_returns_previous_verified_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _OptimalThenUnknownCpSolver.solve_count = 0
    monkeypatch.setattr(
        cp_model,
        "CpSolver",
        _OptimalThenUnknownCpSolver,
    )
    source = _input(
        student=_student(),
        teacher=_teacher(),
        requests=(_request(),),
        slots=_slots(1),
    )

    result = solve_optimization(source)

    assert _OptimalThenUnknownCpSolver.solve_count == 2
    assert result.solver_status == "FEASIBLE"
    assert len(result.assignments) == 1
    assert not result.unassigned_lessons
    assert any("実行可能解を取得できませんでした" in warning for warning in result.warnings)


def test_unknown_before_cp_sat_solution_returns_verified_initial_incumbent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cp_model, "CpSolver", _AlwaysUnknownCpSolver)
    source = _input(
        student=_student(),
        teacher=_teacher(),
        requests=(_request(),),
        slots=_slots(1),
    )

    result = solve_optimization(source)

    assert result.solver_status == "FEASIBLE"
    assert len(result.assignments) == 1
    assert not result.unassigned_lessons
    assert any("実行可能解を取得できませんでした" in warning for warning in result.warnings)


def test_model_invalid_in_later_stage_is_not_hidden_by_previous_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _OptimalThenModelInvalidCpSolver.solve_count = 0
    monkeypatch.setattr(
        cp_model,
        "CpSolver",
        _OptimalThenModelInvalidCpSolver,
    )
    source = _input(
        student=_student(),
        teacher=_teacher(),
        requests=(_request(),),
        slots=_slots(1),
    )

    result = solve_optimization(source)

    assert result.solver_status == "MODEL_INVALID"
    assert not result.assignments
    assert len(result.unassigned_lessons) == 1
    assert any("モデル不正" in warning for warning in result.warnings)


def test_overall_deadline_after_first_stage_returns_previous_snapshot() -> None:
    clock = _ManualClock()
    source = replace(
        _input(
            student=_student(),
            teacher=_teacher(),
            requests=(_request(),),
            slots=_slots(1),
        ),
        settings=replace(_settings(), time_limit_seconds=5),
    )

    def expire_after_first_stage(progress: OptimizationProgress) -> None:
        if progress.stage_index == 1 and progress.solver_status == "OPTIMAL":
            clock.now = 6.0

    result = solve_optimization(
        source,
        progress=expire_after_first_stage,
        clock=clock,
    )

    assert result.solver_status == "FEASIBLE"
    assert len(result.assignments) == 1
    assert not result.unassigned_lessons
    assert any("制限時間" in warning for warning in result.warnings)


@pytest.mark.parametrize(
    ("expire_stage", "warning_fragment", "expected_status", "expected_assignments"),
    (
        ("candidate_generation", "候補生成中", "UNKNOWN", 0),
        ("model_build", "モデル構築中", "FEASIBLE", 1),
    ),
)
def test_overall_deadline_applies_before_solver_search(
    expire_stage: str,
    warning_fragment: str,
    expected_status: str,
    expected_assignments: int,
) -> None:
    clock = _ManualClock()
    source = replace(
        _input(
            student=_student(),
            teacher=_teacher(),
            requests=(_request(),),
            slots=_slots(1),
        ),
        settings=replace(_settings(), time_limit_seconds=5),
    )

    def expire_during_preparation(progress: OptimizationProgress) -> None:
        if progress.stage_name == expire_stage:
            clock.now = 5.0

    result = solve_optimization(
        source,
        progress=expire_during_preparation,
        clock=clock,
    )

    assert result.solver_status == expected_status
    assert not result.cancelled
    assert len(result.assignments) == expected_assignments
    assert len(result.unassigned_lessons) == 1 - expected_assignments
    assert any(warning_fragment in warning and "制限時間" in warning for warning in result.warnings)


class _OptimalThenUnknownCpSolver:
    """初段だけ実CP-SATを解き、次段を決定論的にUNKNOWNにする。"""

    solve_count: ClassVar[int] = 0

    def __init__(self) -> None:
        self._delegate = _REAL_CP_SOLVER()

    @property
    def parameters(self) -> Any:
        return self._delegate.parameters

    def solve(self, model: cp_model.CpModel) -> int:
        type(self).solve_count += 1
        if self.solve_count == 1:
            return int(self._delegate.solve(model))
        return int(cp_model.UNKNOWN)

    def value(self, expression: cp_model.LinearExpr) -> int:
        return int(self._delegate.value(expression))

    def boolean_value(self, literal: cp_model.IntVar) -> bool:
        return self._delegate.boolean_value(literal)

    def stop_search(self) -> None:
        self._delegate.stop_search()


class _AlwaysUnknownCpSolver:
    def __init__(self) -> None:
        self._delegate = _REAL_CP_SOLVER()

    @property
    def parameters(self) -> Any:
        return self._delegate.parameters

    def solve(self, model: cp_model.CpModel) -> int:
        del model
        return int(cp_model.UNKNOWN)

    def stop_search(self) -> None:
        self._delegate.stop_search()


class _OptimalThenModelInvalidCpSolver(_OptimalThenUnknownCpSolver):
    def solve(self, model: cp_model.CpModel) -> int:
        type(self).solve_count += 1
        if self.solve_count == 1:
            return int(self._delegate.solve(model))
        return int(cp_model.MODEL_INVALID)


class _ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _settings() -> OptimizationSettings:
    return OptimizationSettings(
        time_limit_seconds=10,
        random_seed=20260729,
        num_search_workers=1,
        regular_teacher_priority_weights=(1, 3, 6, 10),
        preferred_teacher_rank_weights=(9, 6, 3),
        student_preferred_time_weight=1,
        teacher_preferred_time_weight=1,
        preserve_existing_assignment_weight=1,
    )


def _student(
    *,
    max_consecutive: int = 2,
    allow_gap: bool = False,
) -> StudentData:
    return StudentData(
        id=1,
        display_name="架空生徒1",
        default_max_consecutive_slots=max_consecutive,
        allow_gap=allow_gap,
    )


def _teacher(*, allow_gap: bool = False) -> TeacherData:
    return TeacherData(
        id=1,
        display_name="架空講師1",
        qualified_subject_ids=frozenset({1}),
        allow_gap=allow_gap,
    )


def _request(
    *,
    request_id: int = 1,
    sessions: int = 1,
) -> LessonRequestData:
    return LessonRequestData(
        id=request_id,
        student_id=1,
        subject_id=1,
        required_sessions=sessions,
    )


def _slots(count: int) -> tuple[TimeSlotData, ...]:
    starts = (time(9), time(10), time(11), time(12))
    return tuple(
        TimeSlotData(
            id=index,
            code=chr(ord("A") + index - 1),
            display_name=f"{chr(ord('A') + index - 1)}コマ",
            start_time=starts[index - 1],
            end_time=time(starts[index - 1].hour, 50),
            sort_order=index,
        )
        for index in range(1, count + 1)
    )


def _input(
    *,
    student: StudentData,
    teacher: TeacherData,
    requests: tuple[LessonRequestData, ...],
    slots: tuple[TimeSlotData, ...],
    student_slots: set[int] | None = None,
    teacher_slots: set[int] | None = None,
    groups: tuple[GroupBlockData, ...] = (),
    existing: tuple[ExistingAssignmentData, ...] = (),
) -> OptimizationInput:
    selected_student_slots = student_slots or {slot.id for slot in slots}
    selected_teacher_slots = teacher_slots or {slot.id for slot in slots}
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY,),
        time_slots=slots,
        students=(student,),
        teachers=(teacher,),
        subjects=(SUBJECT,),
        lesson_requests=requests,
        availabilities=tuple(
            [
                *(
                    AvailabilityData("student", student.id, DAY, slot_id, 1)
                    for slot_id in sorted(selected_student_slots)
                ),
                *(
                    AvailabilityData("teacher", teacher.id, DAY, slot_id, 1)
                    for slot_id in sorted(selected_teacher_slots)
                ),
            ]
        ),
        group_blocks=groups,
        existing_assignments=existing,
        settings=_settings(),
    )
