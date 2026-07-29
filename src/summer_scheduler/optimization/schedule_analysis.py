"""結果検証と診断で共有する、solver非依存の時間割状態解析。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from summer_scheduler.domain.time_ranges import time_ranges_overlap
from summer_scheduler.optimization.dto import (
    CandidateData,
    LessonRequestData,
    OptimizationInput,
    ScheduledAssignment,
    StudentData,
    TimeSlotData,
)

type SessionKey = tuple[int, int]
type OccupancyKey = tuple[int, date, int]


@dataclass(slots=True)
class ScheduleState:
    requests: dict[int, LessonRequestData]
    students: dict[int, StudentData]
    slots: tuple[TimeSlotData, ...]
    slot_by_id: dict[int, TimeSlotData]
    slot_position: dict[int, int]
    assignments_by_session: dict[SessionKey, list[ScheduledAssignment]]
    assignments_by_student_day: dict[tuple[int, date], list[ScheduledAssignment]]
    assignments_by_teacher_day: dict[tuple[int, date], list[ScheduledAssignment]]
    student_occupancy: dict[OccupancyKey, list[ScheduledAssignment]]
    teacher_occupancy: dict[OccupancyKey, list[ScheduledAssignment]]
    group_student_occupancy: set[OccupancyKey]
    group_teacher_occupancy: set[OccupancyKey]


def build_schedule_state(
    data: OptimizationInput,
    assignments: tuple[ScheduledAssignment, ...],
) -> ScheduleState:
    requests = {item.id: item for item in data.lesson_requests}
    students = {item.id: item for item in data.students}
    slots = tuple(sorted(data.time_slots, key=lambda item: (item.sort_order, item.id)))
    assignments_by_session: dict[SessionKey, list[ScheduledAssignment]] = defaultdict(list)
    assignments_by_student_day: dict[tuple[int, date], list[ScheduledAssignment]] = defaultdict(
        list
    )
    assignments_by_teacher_day: dict[tuple[int, date], list[ScheduledAssignment]] = defaultdict(
        list
    )
    student_occupancy: dict[OccupancyKey, list[ScheduledAssignment]] = defaultdict(list)
    teacher_occupancy: dict[OccupancyKey, list[ScheduledAssignment]] = defaultdict(list)

    for assignment in assignments:
        assignments_by_session[(assignment.lesson_request_id, assignment.session_index)].append(
            assignment
        )
        assignments_by_student_day[(assignment.student_id, assignment.day)].append(assignment)
        assignments_by_teacher_day[(assignment.teacher_id, assignment.day)].append(assignment)
        student_occupancy[(assignment.student_id, assignment.day, assignment.time_slot_id)].append(
            assignment
        )
        teacher_occupancy[(assignment.teacher_id, assignment.day, assignment.time_slot_id)].append(
            assignment
        )

    group_students: set[OccupancyKey] = set()
    group_teachers: set[OccupancyKey] = set()
    for block in data.group_blocks:
        for slot in slots:
            if not time_ranges_overlap(
                slot.start_time,
                slot.end_time,
                block.start_time,
                block.end_time,
            ):
                continue
            group_students.update(
                (student_id, block.day, slot.id) for student_id in block.student_ids
            )
            if block.teacher_id is not None:
                group_teachers.add((block.teacher_id, block.day, slot.id))

    return ScheduleState(
        requests=requests,
        students=students,
        slots=slots,
        slot_by_id={slot.id: slot for slot in slots},
        slot_position={slot.id: index for index, slot in enumerate(slots)},
        assignments_by_session=dict(assignments_by_session),
        assignments_by_student_day=dict(assignments_by_student_day),
        assignments_by_teacher_day=dict(assignments_by_teacher_day),
        student_occupancy=dict(student_occupancy),
        teacher_occupancy=dict(teacher_occupancy),
        group_student_occupancy=group_students,
        group_teacher_occupancy=group_teachers,
    )


def student_occupied_slots(
    state: ScheduleState,
    student_id: int,
    day: date,
    *,
    additional_slot_id: int | None = None,
) -> set[int]:
    occupied = {
        slot_id
        for owner_id, occupied_day, slot_id in state.group_student_occupancy
        if owner_id == student_id and occupied_day == day
    }
    occupied.update(
        assignment.time_slot_id
        for assignment in state.assignments_by_student_day.get((student_id, day), ())
    )
    if additional_slot_id is not None:
        occupied.add(additional_slot_id)
    return occupied


def teacher_occupied_slots(
    state: ScheduleState,
    teacher_id: int,
    day: date,
    *,
    additional_slot_id: int | None = None,
) -> set[int]:
    occupied = {
        slot_id
        for owner_id, occupied_day, slot_id in state.group_teacher_occupancy
        if owner_id == teacher_id and occupied_day == day
    }
    occupied.update(
        assignment.time_slot_id
        for assignment in state.assignments_by_teacher_day.get((teacher_id, day), ())
    )
    if additional_slot_id is not None:
        occupied.add(additional_slot_id)
    return occupied


def student_day_requires_no_gap(
    state: ScheduleState,
    student_id: int,
    day: date,
    *,
    additional_request: LessonRequestData | None = None,
) -> bool:
    student = state.students.get(student_id)
    if student is None:
        return True
    has_group = any(
        owner_id == student_id and occupied_day == day
        for owner_id, occupied_day, _slot_id in state.group_student_occupancy
    )
    if has_group and not student.allow_gap:
        return True
    requests = [
        state.requests.get(assignment.lesson_request_id)
        for assignment in state.assignments_by_student_day.get((student_id, day), ())
    ]
    if additional_request is not None:
        requests.append(additional_request)
    return any(
        request is None or not effective_student_allow_gap(student, request) for request in requests
    )


def effective_student_allow_gap(
    student: StudentData,
    request: LessonRequestData,
) -> bool:
    if request.allow_gap_override is not None:
        return request.allow_gap_override
    return student.allow_gap


def effective_student_consecutive_limit(
    student: StudentData,
    request: LessonRequestData,
) -> int:
    if request.max_consecutive_slots_override is not None:
        return request.max_consecutive_slots_override
    return student.default_max_consecutive_slots


def occupied_slots_are_contiguous(
    state: ScheduleState,
    occupied_slot_ids: set[int],
) -> bool:
    if len(occupied_slot_ids) <= 1:
        return True
    positions = sorted(
        state.slot_position[slot_id]
        for slot_id in occupied_slot_ids
        if slot_id in state.slot_position
    )
    if len(positions) != len(occupied_slot_ids):
        return False
    return positions[-1] - positions[0] + 1 == len(positions)


def student_consecutive_limit_is_violated(
    state: ScheduleState,
    student_id: int,
    day: date,
    *,
    additional_candidate: CandidateData | None = None,
) -> bool:
    student = state.students.get(student_id)
    if student is None:
        return True
    occupied = student_occupied_slots(
        state,
        student_id,
        day,
        additional_slot_id=(
            additional_candidate.time_slot_id if additional_candidate is not None else None
        ),
    )
    constrained_slots: list[tuple[int, int]] = []
    for assignment in state.assignments_by_student_day.get((student_id, day), ()):
        request = state.requests.get(assignment.lesson_request_id)
        if request is None:
            return True
        constrained_slots.append(
            (
                assignment.time_slot_id,
                effective_student_consecutive_limit(student, request),
            )
        )
    constrained_slots.extend(
        (slot_id, student.default_max_consecutive_slots)
        for owner_id, occupied_day, slot_id in state.group_student_occupancy
        if owner_id == student_id and occupied_day == day
    )
    if additional_candidate is not None:
        request = state.requests.get(additional_candidate.lesson_request_id)
        if request is None:
            return True
        constrained_slots.append(
            (
                additional_candidate.time_slot_id,
                effective_student_consecutive_limit(student, request),
            )
        )
    return any(
        limit <= 0 or _run_length(state, occupied, slot_id) > limit
        for slot_id, limit in constrained_slots
    )


def candidate_group_conflict(
    state: ScheduleState,
    candidate: CandidateData,
) -> bool:
    student_key = (candidate.student_id, candidate.day, candidate.time_slot_id)
    teacher_key = (candidate.teacher_id, candidate.day, candidate.time_slot_id)
    return (
        student_key in state.group_student_occupancy or teacher_key in state.group_teacher_occupancy
    )


def _run_length(
    state: ScheduleState,
    occupied_slot_ids: set[int],
    target_slot_id: int,
) -> int:
    target = state.slot_position.get(target_slot_id)
    if target is None:
        return len(state.slots) + 1
    positions = {
        state.slot_position[slot_id]
        for slot_id in occupied_slot_ids
        if slot_id in state.slot_position
    }
    if target not in positions:
        return 0
    left = target
    right = target
    while left - 1 in positions:
        left -= 1
    while right + 1 in positions:
        right += 1
    return right - left + 1


__all__ = [
    "OccupancyKey",
    "ScheduleState",
    "SessionKey",
    "build_schedule_state",
    "candidate_group_conflict",
    "effective_student_allow_gap",
    "effective_student_consecutive_limit",
    "occupied_slots_are_contiguous",
    "student_consecutive_limit_is_violated",
    "student_day_requires_no_gap",
    "student_occupied_slots",
    "teacher_occupied_slots",
]
