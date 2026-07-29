"""半開区間の時刻重複判定。"""

from datetime import time

import pytest

from summer_scheduler.domain.time_ranges import (
    InvalidTimeRangeError,
    time_ranges_overlap,
)


def test_overlapping_ranges_are_detected_in_both_orders() -> None:
    assert time_ranges_overlap(
        time(14, 10),
        time(15, 30),
        time(15, 0),
        time(16, 0),
    )
    assert time_ranges_overlap(
        time(15, 0),
        time(16, 0),
        time(14, 10),
        time(15, 30),
    )


def test_touching_boundaries_do_not_overlap() -> None:
    assert not time_ranges_overlap(
        time(14, 10),
        time(15, 30),
        time(15, 30),
        time(16, 0),
    )


def test_invalid_range_is_rejected() -> None:
    with pytest.raises(InvalidTimeRangeError, match="終了時刻"):
        time_ranges_overlap(
            time(15, 30),
            time(15, 30),
            time(16, 0),
            time(17, 0),
        )
