"""時間割のハード制約をCP-SATへ追加する。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date

from ortools.sat.python import cp_model

from summer_scheduler.domain.time_ranges import time_ranges_overlap
from summer_scheduler.optimization.dto import (
    CandidateData,
    CandidateGenerationResult,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    OptimizationInput,
    StudentData,
    TeacherData,
    TimeSlotData,
)
from summer_scheduler.optimization.variables import ModelVariables, OccupancyKey, session_key


class HardConstraintInputError(ValueError):
    """固定授業等をハード制約として表現できない入力。"""


class OptimizationBuildCancelled(RuntimeError):
    """CP-SATモデル構築が利用者の要求で安全に中止された。"""


def add_hard_constraints(
    model: cp_model.CpModel,
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    variables: ModelVariables,
    *,
    is_cancelled: Callable[[], bool] | None = None,
) -> None:
    """全ハード制約を追加する。

    単一候補で判定できる可用性、資格、優先度5、開校日、集団授業重複は候補生成で
    除外済みである。この関数では、候補同士の容量、1対1、固定、連続、空きコマを
    solver上の絶対条件として表現する。
    """
    requests = {item.id: item for item in data.lesson_requests}
    students = {item.id: item for item in data.students}
    teachers = {item.id: item for item in data.teachers}
    slots = tuple(sorted(data.time_slots, key=lambda item: (item.sort_order, item.id)))
    candidates_by_session: dict[tuple[int, int], list[CandidateData]] = defaultdict(list)

    for index, candidate in enumerate(generation.candidates):
        if index % 256 == 0:
            _raise_if_cancelled(is_cancelled)
        candidate_var = model.new_bool_var(
            "x_"
            f"{candidate.lesson_request_id}_{candidate.session_index}_"
            f"{candidate.day.isoformat()}_{candidate.time_slot_id}_{candidate.teacher_id}_{index}"
        )
        variables.assignments[candidate] = candidate_var
        candidates_by_session[session_key(candidate)].append(candidate)

    for session in generation.sessions:
        _raise_if_cancelled(is_cancelled)
        key = session.key
        unassigned = model.new_bool_var(f"u_{key[0]}_{key[1]}")
        variables.unassigned[key] = unassigned
        candidate_vars = [
            variables.assignments[candidate] for candidate in candidates_by_session.get(key, ())
        ]
        model.add(sum(candidate_vars) + unassigned == 1)

    _fix_locked_assignments(
        model,
        data.existing_assignments,
        candidates_by_session,
        variables,
    )
    _raise_if_cancelled(is_cancelled)

    days = _model_days(data, generation)
    relevant_students = {session.student_id for session in generation.sessions} | {
        student_id for block in data.group_blocks for student_id in block.student_ids
    }
    relevant_teachers = {candidate.teacher_id for candidate in generation.candidates} | {
        block.teacher_id for block in data.group_blocks if block.teacher_id is not None
    }
    student_candidates: dict[OccupancyKey, list[CandidateData]] = defaultdict(list)
    teacher_candidates: dict[OccupancyKey, list[CandidateData]] = defaultdict(list)
    for candidate in generation.candidates:
        student_candidates[(candidate.student_id, candidate.day, candidate.time_slot_id)].append(
            candidate
        )
        teacher_candidates[(candidate.teacher_id, candidate.day, candidate.time_slot_id)].append(
            candidate
        )

    fixed_students, fixed_teachers = _group_occupancy(data.group_blocks, slots)
    _add_student_occupancy(
        model,
        relevant_students,
        days,
        slots,
        student_candidates,
        fixed_students,
        variables,
    )
    _raise_if_cancelled(is_cancelled)
    _add_teacher_occupancy_and_capacity(
        model,
        relevant_teachers,
        days,
        slots,
        teacher_candidates,
        fixed_teachers,
        requests,
        variables,
    )
    _raise_if_cancelled(is_cancelled)
    _add_start_variables(
        model,
        relevant_students,
        relevant_teachers,
        days,
        slots,
        variables,
    )
    _raise_if_cancelled(is_cancelled)
    _add_student_gap_constraints(
        model,
        data,
        generation,
        days,
        slots,
        students,
        requests,
        fixed_students,
        variables,
    )
    _raise_if_cancelled(is_cancelled)
    _add_teacher_gap_constraints(
        model,
        relevant_teachers,
        days,
        slots,
        teachers,
        variables,
    )
    _raise_if_cancelled(is_cancelled)
    _add_student_consecutive_constraints(
        model,
        data,
        generation,
        slots,
        students,
        requests,
        fixed_students,
        variables,
    )
    _raise_if_cancelled(is_cancelled)


def _fix_locked_assignments(
    model: cp_model.CpModel,
    existing: tuple[ExistingAssignmentData, ...],
    candidates_by_session: dict[tuple[int, int], list[CandidateData]],
    variables: ModelVariables,
) -> None:
    for locked in (item for item in existing if item.is_locked):
        matches = [
            candidate
            for candidate in candidates_by_session.get(
                (locked.lesson_request_id, locked.session_index),
                (),
            )
            if (
                candidate.day == locked.day
                and candidate.time_slot_id == locked.time_slot_id
                and candidate.teacher_id == locked.teacher_id
            )
        ]
        if len(matches) != 1:
            raise HardConstraintInputError(
                "ロック済みAssignmentが現在の必須条件を満たす候補に一致しません"
            )
        model.add(variables.assignments[matches[0]] == 1)


def _add_student_occupancy(
    model: cp_model.CpModel,
    student_ids: set[int],
    days: tuple[date, ...],
    slots: tuple[TimeSlotData, ...],
    indexed: dict[OccupancyKey, list[CandidateData]],
    fixed: set[OccupancyKey],
    variables: ModelVariables,
) -> None:
    for student_id in sorted(student_ids):
        for day in days:
            for slot in slots:
                key = (student_id, day, slot.id)
                active = model.new_bool_var(
                    f"student_active_{student_id}_{day.isoformat()}_{slot.id}"
                )
                variables.student_active[key] = active
                candidate_vars = [
                    variables.assignments[candidate] for candidate in indexed.get(key, ())
                ]
                model.add(sum(candidate_vars) <= 1)
                if key in fixed:
                    model.add(sum(candidate_vars) == 0)
                    model.add(active == 1)
                else:
                    model.add(active == sum(candidate_vars))


def _add_teacher_occupancy_and_capacity(
    model: cp_model.CpModel,
    teacher_ids: set[int],
    days: tuple[date, ...],
    slots: tuple[TimeSlotData, ...],
    indexed: dict[OccupancyKey, list[CandidateData]],
    fixed: set[OccupancyKey],
    requests: dict[int, LessonRequestData],
    variables: ModelVariables,
) -> None:
    for teacher_id in sorted(teacher_ids):
        for day in days:
            for slot in slots:
                key = (teacher_id, day, slot.id)
                active = model.new_bool_var(
                    f"teacher_active_{teacher_id}_{day.isoformat()}_{slot.id}"
                )
                variables.teacher_active[key] = active
                candidates = indexed.get(key, ())
                candidate_vars = [variables.assignments[item] for item in candidates]
                count = sum(candidate_vars)
                if key in fixed:
                    model.add(count == 0)
                    model.add(active == 1)
                    continue
                model.add(count <= 2)
                one_to_one_vars = [
                    variables.assignments[item]
                    for item in candidates
                    if requests[item.lesson_request_id].one_to_one_required
                ]
                model.add(count + sum(one_to_one_vars) <= 2)
                model.add(count <= 2 * active)
                model.add(count >= active)


def _add_start_variables(
    model: cp_model.CpModel,
    student_ids: set[int],
    teacher_ids: set[int],
    days: tuple[date, ...],
    slots: tuple[TimeSlotData, ...],
    variables: ModelVariables,
) -> None:
    for owner, owner_ids, active_map, start_map in (
        ("student", student_ids, variables.student_active, variables.student_starts),
        ("teacher", teacher_ids, variables.teacher_active, variables.teacher_starts),
    ):
        for owner_id in sorted(owner_ids):
            for day in days:
                previous: cp_model.IntVar | None = None
                for slot in slots:
                    key = (owner_id, day, slot.id)
                    active = active_map[key]
                    start = model.new_bool_var(
                        f"{owner}_start_{owner_id}_{day.isoformat()}_{slot.id}"
                    )
                    start_map[key] = start
                    if previous is None:
                        model.add(start == active)
                    else:
                        model.add(start >= active - previous)
                        model.add(start <= active)
                        model.add(start <= 1 - previous)
                    previous = active


def _add_student_gap_constraints(
    model: cp_model.CpModel,
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    days: tuple[date, ...],
    slots: tuple[TimeSlotData, ...],
    students: dict[int, StudentData],
    requests: dict[int, LessonRequestData],
    fixed_students: set[OccupancyKey],
    variables: ModelVariables,
) -> None:
    strict_candidates_by_student_day: dict[
        tuple[int, date],
        list[cp_model.IntVar],
    ] = defaultdict(list)
    for candidate in generation.candidates:
        student = students[candidate.student_id]
        request = requests[candidate.lesson_request_id]
        allow_gap = (
            request.allow_gap_override
            if request.allow_gap_override is not None
            else student.allow_gap
        )
        if not allow_gap:
            strict_candidates_by_student_day[(candidate.student_id, candidate.day)].append(
                variables.assignments[candidate]
            )

    multiplier = max(1, len(slots))
    for student_id in sorted({session.student_id for session in generation.sessions}):
        student = students[student_id]
        for day in days:
            starts = [variables.student_starts[(student_id, day, slot.id)] for slot in slots]
            strict_group = not student.allow_gap and any(
                (student_id, day, slot.id) in fixed_students for slot in slots
            )
            if strict_group:
                model.add(sum(starts) <= 1)
                continue
            strict_candidates = strict_candidates_by_student_day.get((student_id, day), ())
            if not strict_candidates:
                continue
            strict_selected = _selection_indicator(
                model,
                strict_candidates,
                name=f"student_gap_strict_{student_id}_{day.isoformat()}",
                variables=variables,
            )
            model.add(sum(starts) <= 1 + multiplier * (1 - strict_selected))


def _add_teacher_gap_constraints(
    model: cp_model.CpModel,
    teacher_ids: set[int],
    days: tuple[date, ...],
    slots: tuple[TimeSlotData, ...],
    teachers: dict[int, TeacherData],
    variables: ModelVariables,
) -> None:
    for teacher_id in sorted(teacher_ids):
        teacher = teachers[teacher_id]
        if teacher.allow_gap:
            continue
        for day in days:
            model.add(
                sum(variables.teacher_starts[(teacher_id, day, slot.id)] for slot in slots) <= 1
            )


def _add_student_consecutive_constraints(
    model: cp_model.CpModel,
    data: OptimizationInput,
    generation: CandidateGenerationResult,
    slots: tuple[TimeSlotData, ...],
    students: dict[int, StudentData],
    requests: dict[int, LessonRequestData],
    fixed_students: set[OccupancyKey],
    variables: ModelVariables,
) -> None:
    slot_position = {slot.id: position for position, slot in enumerate(slots)}
    conditional_windows: dict[
        tuple[int, date, int, int],
        list[cp_model.IntVar],
    ] = defaultdict(list)
    for candidate in generation.candidates:
        request = requests[candidate.lesson_request_id]
        student = students[candidate.student_id]
        limit = (
            request.max_consecutive_slots_override
            if request.max_consecutive_slots_override is not None
            else student.default_max_consecutive_slots
        )
        if limit <= 0:
            raise HardConstraintInputError("最大連続コマ数は1以上である必要があります")
        for window_start in _windows_containing(
            slot_position[candidate.time_slot_id],
            limit,
            len(slots),
        ):
            key = (candidate.student_id, candidate.day, window_start, limit)
            conditional_windows[key].append(variables.assignments[candidate])

    fixed_windows: set[tuple[int, date, int, int]] = set()
    for student_id, day, slot_id in sorted(fixed_students):
        group_student = students.get(student_id)
        if group_student is None:
            continue
        limit = group_student.default_max_consecutive_slots
        position = slot_position[slot_id]
        for window_start in _windows_containing(position, limit, len(slots)):
            fixed_windows.add((student_id, day, window_start, limit))

    for student_id, day, window_start, limit in sorted(fixed_windows | set(conditional_windows)):
        key = (student_id, day, window_start, limit)
        window = slots[window_start : window_start + limit + 1]
        active_count = sum(variables.student_active[(student_id, day, slot.id)] for slot in window)
        if key in fixed_windows:
            model.add(active_count <= limit)
            continue
        selected = _selection_indicator(
            model,
            conditional_windows[key],
            name=(
                f"student_consecutive_trigger_{student_id}_{day.isoformat()}_{window_start}_{limit}"
            ),
            variables=variables,
        )
        model.add(active_count <= limit + (limit + 1) * (1 - selected))


def _selection_indicator(
    model: cp_model.CpModel,
    selections: Iterable[cp_model.IntVar],
    *,
    name: str,
    variables: ModelVariables,
) -> cp_model.IntVar:
    selection_list = list(selections)
    if not selection_list:
        raise ValueError("selection indicatorには1件以上の変数が必要です")
    if len(selection_list) == 1:
        return selection_list[0]
    indicator = model.new_bool_var(name)
    model.add_max_equality(indicator, selection_list)
    variables.selection_indicators.append((indicator, tuple(selection_list)))
    return indicator


def _windows_containing(position: int, limit: int, slot_count: int) -> range:
    window_size = limit + 1
    if window_size > slot_count:
        return range(0)
    first = max(0, position - limit)
    last = min(position, slot_count - window_size)
    return range(first, last + 1)


def _model_days(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
) -> tuple[date, ...]:
    days = set(data.open_dates)
    days.update(candidate.day for candidate in generation.candidates)
    days.update(block.day for block in data.group_blocks)
    days.update(item.day for item in data.existing_assignments if item.is_locked)
    return tuple(sorted(days))


def _group_occupancy(
    blocks: Iterable[GroupBlockData],
    slots: tuple[TimeSlotData, ...],
) -> tuple[set[OccupancyKey], set[OccupancyKey]]:
    students: set[OccupancyKey] = set()
    teachers: set[OccupancyKey] = set()
    for block in blocks:
        for slot in slots:
            if not time_ranges_overlap(
                slot.start_time,
                slot.end_time,
                block.start_time,
                block.end_time,
            ):
                continue
            students.update((student_id, block.day, slot.id) for student_id in block.student_ids)
            if block.teacher_id is not None:
                teachers.add((block.teacher_id, block.day, slot.id))
    return students, teachers


def _raise_if_cancelled(is_cancelled: Callable[[], bool] | None) -> None:
    if is_cancelled is not None and is_cancelled():
        raise OptimizationBuildCancelled


__all__ = [
    "HardConstraintInputError",
    "OptimizationBuildCancelled",
    "add_hard_constraints",
]
