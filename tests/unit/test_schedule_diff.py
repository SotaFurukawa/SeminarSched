"""session単位の時間割差分分類を検証する。"""

from __future__ import annotations

from datetime import date

import pytest

from summer_scheduler.optimization.dto import ScheduledAssignment, UnassignedLesson
from summer_scheduler.optimization.manual_edit import EditSchedule
from summer_scheduler.optimization.schedule_diff import ScheduleDiffKind, diff_schedules

DAY_1 = date(2026, 8, 3)
DAY_2 = date(2026, 8, 4)


def test_diff_classifies_all_required_changes_in_stable_session_order() -> None:
    before = EditSchedule(
        assignments=(
            _assignment(2, DAY_1, 100, 10),
            _assignment(3, DAY_1, 100, 30),
            _assignment(4, DAY_1, 101, 40),
            _assignment(5, DAY_1, 101, 50),
        ),
        unassigned_lessons=(_unassigned(1), _unassigned(6)),
    )
    after = EditSchedule(
        assignments=(
            _assignment(1, DAY_1, 102, 10),
            _assignment(2, DAY_2, 101, 20),
            _assignment(4, DAY_1, 101, 40),
            _assignment(5, DAY_1, 101, 40),
        ),
        unassigned_lessons=(_unassigned(3), _unassigned(6)),
    )

    entries = diff_schedules(before, after)

    assert [entry.session_key for entry in entries] == [(item, 1) for item in range(1, 7)]
    assert entries[0].change_kinds == (ScheduleDiffKind.NEW_ASSIGNMENT,)
    assert entries[1].change_kinds == (
        ScheduleDiffKind.DATE_TIME_CHANGED,
        ScheduleDiffKind.TEACHER_CHANGED,
    )
    assert entries[2].change_kinds == (ScheduleDiffKind.BECAME_UNASSIGNED,)
    assert entries[3].change_kinds == (ScheduleDiffKind.PAIRING_CHANGED,)
    assert entries[3].before_pairing_size == 1
    assert entries[3].after_pairing_size == 2
    assert entries[4].change_kinds == (
        ScheduleDiffKind.TEACHER_CHANGED,
        ScheduleDiffKind.PAIRING_CHANGED,
    )
    assert entries[5].change_kinds == (ScheduleDiffKind.UNCHANGED,)


def test_pairing_change_propagates_to_unchanged_assignment_in_same_cell() -> None:
    first = _assignment(1, DAY_1, 100, 10)
    second = _assignment(2, DAY_1, 101, 10)
    before = EditSchedule((first, second), ())
    after = EditSchedule((first, _assignment(2, DAY_1, 100, 10)), ())

    entries = diff_schedules(before, after)

    assert entries[0].change_kinds == (ScheduleDiffKind.PAIRING_CHANGED,)
    assert entries[1].change_kinds == (
        ScheduleDiffKind.DATE_TIME_CHANGED,
        ScheduleDiffKind.PAIRING_CHANGED,
    )


def test_new_and_unassigned_do_not_receive_redundant_pairing_category() -> None:
    before = EditSchedule((), (_unassigned(1),))
    after = EditSchedule((_assignment(1, DAY_1, 100, 10),), ())
    new_entry = diff_schedules(before, after)[0]
    removed_entry = diff_schedules(after, before)[0]

    assert new_entry.change_kinds == (ScheduleDiffKind.NEW_ASSIGNMENT,)
    assert removed_entry.change_kinds == (ScheduleDiffKind.BECAME_UNASSIGNED,)


def test_duplicate_assignment_session_is_rejected_instead_of_hidden() -> None:
    duplicate = EditSchedule(
        (
            _assignment(1, DAY_1, 100, 10),
            _assignment(1, DAY_1, 101, 20),
        ),
        (),
    )

    with pytest.raises(ValueError, match="重複session"):
        diff_schedules(duplicate, EditSchedule((), (_unassigned(1),)))


def test_assignment_and_unassigned_overlap_is_rejected_instead_of_hidden() -> None:
    overlap = EditSchedule(
        (_assignment(1, DAY_1, 100, 10),),
        (_unassigned(1),),
    )

    with pytest.raises(ValueError, match="配置・未配置の両方"):
        diff_schedules(overlap, EditSchedule((), (_unassigned(1),)))


def _assignment(
    request_id: int,
    day: date,
    slot_id: int,
    teacher_id: int,
) -> ScheduledAssignment:
    return ScheduledAssignment(
        lesson_request_id=request_id,
        session_index=1,
        student_id=request_id,
        subject_id=500,
        teacher_id=teacher_id,
        day=day,
        time_slot_id=slot_id,
    )


def _unassigned(request_id: int) -> UnassignedLesson:
    return UnassignedLesson(
        lesson_request_id=request_id,
        session_index=1,
        student_id=request_id,
        subject_id=500,
        reasons=(),
    )
