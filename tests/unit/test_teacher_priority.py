from __future__ import annotations

import pytest

from summer_scheduler.domain.teacher_priority import (
    maximum_other_teacher_sessions,
    minimum_regular_teacher_sessions,
)


@pytest.mark.parametrize(
    ("priority", "minimum", "maximum_other"),
    ((1, 0, 4), (2, 1, 3), (3, 2, 2), (4, 3, 1), (5, 4, 0)),
)
def test_four_sessions_follow_priority_percentages(
    priority: int,
    minimum: int,
    maximum_other: int,
) -> None:
    assert minimum_regular_teacher_sessions(4, priority) == minimum
    assert maximum_other_teacher_sessions(4, priority) == maximum_other


@pytest.mark.parametrize(
    ("priority", "minimum"),
    ((1, 0), (2, 2), (3, 3), (4, 4), (5, 5)),
)
def test_fractional_minimums_are_rounded_up(priority: int, minimum: int) -> None:
    assert minimum_regular_teacher_sessions(5, priority) == minimum


@pytest.mark.parametrize(("sessions", "priority"), ((-1, 3), (4, 0), (4, 6)))
def test_invalid_values_are_rejected(sessions: int, priority: int) -> None:
    with pytest.raises(ValueError):
        minimum_regular_teacher_sessions(sessions, priority)
