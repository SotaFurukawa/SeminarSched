"""編集・再最適化前後のsession単位差分を返す純粋関数。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from summer_scheduler.optimization.dto import ScheduledAssignment, UnassignedLesson
from summer_scheduler.optimization.manual_edit import EditSchedule

type SessionKey = tuple[int, int]


class ScheduleDiffKind(StrEnum):
    NEW_ASSIGNMENT = "new"
    DATE_TIME_CHANGED = "date"
    TEACHER_CHANGED = "teacher"
    BECAME_UNASSIGNED = "unassigned"
    PAIRING_CHANGED = "pairing"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class ScheduleDiffEntry:
    lesson_request_id: int
    session_index: int
    change_kinds: tuple[ScheduleDiffKind, ...]
    before: ScheduledAssignment | None
    after: ScheduledAssignment | None
    before_pairing_size: int | None
    after_pairing_size: int | None

    @property
    def session_key(self) -> SessionKey:
        return (self.lesson_request_id, self.session_index)

    @property
    def changed(self) -> bool:
        return self.change_kinds != (ScheduleDiffKind.UNCHANGED,)


_KIND_ORDER = (
    ScheduleDiffKind.NEW_ASSIGNMENT,
    ScheduleDiffKind.DATE_TIME_CHANGED,
    ScheduleDiffKind.TEACHER_CHANGED,
    ScheduleDiffKind.BECAME_UNASSIGNED,
    ScheduleDiffKind.PAIRING_CHANGED,
    ScheduleDiffKind.UNCHANGED,
)
_KIND_INDEX = {kind: index for index, kind in enumerate(_KIND_ORDER)}


def diff_schedules(
    before: EditSchedule,
    after: EditSchedule,
) -> tuple[ScheduleDiffEntry, ...]:
    """全sessionを安定順で比較し、pair人数の波及変更もsessionごとに返す。"""
    before_assignments = _assignments_by_session(before.assignments)
    after_assignments = _assignments_by_session(after.assignments)
    before_keys = _validated_schedule_keys(before, before_assignments)
    after_keys = _validated_schedule_keys(after, after_assignments)
    keys = before_keys | after_keys
    before_occupancy = _occupancy(before.assignments)
    after_occupancy = _occupancy(after.assignments)
    entries: list[ScheduleDiffEntry] = []
    for key in sorted(keys):
        before_assignment = before_assignments.get(key)
        after_assignment = after_assignments.get(key)
        before_pairing = _pairing_size(before_assignment, before_occupancy)
        after_pairing = _pairing_size(after_assignment, after_occupancy)
        kinds = _change_kinds(
            before_assignment,
            after_assignment,
            before_pairing,
            after_pairing,
        )
        entries.append(
            ScheduleDiffEntry(
                lesson_request_id=key[0],
                session_index=key[1],
                change_kinds=kinds,
                before=before_assignment,
                after=after_assignment,
                before_pairing_size=before_pairing,
                after_pairing_size=after_pairing,
            )
        )
    return tuple(entries)


def _change_kinds(
    before: ScheduledAssignment | None,
    after: ScheduledAssignment | None,
    before_pairing: int | None,
    after_pairing: int | None,
) -> tuple[ScheduleDiffKind, ...]:
    kinds: list[ScheduleDiffKind] = []
    if before is None and after is not None:
        kinds.append(ScheduleDiffKind.NEW_ASSIGNMENT)
    elif before is not None and after is None:
        kinds.append(ScheduleDiffKind.BECAME_UNASSIGNED)
    elif before is not None and after is not None:
        if (before.day, before.time_slot_id) != (after.day, after.time_slot_id):
            kinds.append(ScheduleDiffKind.DATE_TIME_CHANGED)
        if before.teacher_id != after.teacher_id:
            kinds.append(ScheduleDiffKind.TEACHER_CHANGED)
        if before_pairing != after_pairing:
            kinds.append(ScheduleDiffKind.PAIRING_CHANGED)
    if not kinds:
        kinds.append(ScheduleDiffKind.UNCHANGED)
    return tuple(sorted(kinds, key=_KIND_INDEX.__getitem__))


def _assignments_by_session(
    assignments: tuple[ScheduledAssignment, ...],
) -> dict[SessionKey, ScheduledAssignment]:
    result: dict[SessionKey, ScheduledAssignment] = {}
    for assignment in assignments:
        key = _assignment_key(assignment)
        if key in result:
            raise ValueError(f"差分元に重複sessionがあります: {key[0]}-{key[1]}")
        result[key] = assignment
    return result


def _validated_schedule_keys(
    schedule: EditSchedule,
    assignments: dict[SessionKey, ScheduledAssignment],
) -> set[SessionKey]:
    unassigned_keys = [_unassigned_key(item) for item in schedule.unassigned_lessons]
    if len(unassigned_keys) != len(set(unassigned_keys)):
        raise ValueError("差分元の未配置一覧に重複sessionがあります")
    overlap = set(assignments) & set(unassigned_keys)
    if overlap:
        key = min(overlap)
        raise ValueError(f"差分元でsessionが配置・未配置の両方に含まれます: {key[0]}-{key[1]}")
    return set(assignments) | set(unassigned_keys)


def _occupancy(
    assignments: tuple[ScheduledAssignment, ...],
) -> Counter[tuple[int, date, int]]:
    return Counter((item.teacher_id, item.day, item.time_slot_id) for item in assignments)


def _pairing_size(
    assignment: ScheduledAssignment | None,
    occupancy: Counter[tuple[int, date, int]],
) -> int | None:
    if assignment is None:
        return None
    return occupancy[(assignment.teacher_id, assignment.day, assignment.time_slot_id)]


def _assignment_key(item: ScheduledAssignment) -> SessionKey:
    return (item.lesson_request_id, item.session_index)


def _unassigned_key(item: UnassignedLesson) -> SessionKey:
    return (item.lesson_request_id, item.session_index)


__all__ = [
    "ScheduleDiffEntry",
    "ScheduleDiffKind",
    "diff_schedules",
]
