"""集団授業と個別授業候補で共有する半開区間の時刻判定。"""

from __future__ import annotations

from datetime import time


class InvalidTimeRangeError(ValueError):
    """開始が終了より前でない時刻区間。"""


def time_ranges_overlap(
    left_start: time,
    left_end: time,
    right_start: time,
    right_end: time,
) -> bool:
    """2つの ``[start, end)`` が重なるか返す。

    終了時刻と別区間の開始時刻が同じ場合は、境界が接するだけなので重複しない。
    日をまたぐ区間は初期版の講習時間帯として扱わず、呼出側の入力エラーにする。
    """
    _require_valid_range(left_start, left_end)
    _require_valid_range(right_start, right_end)
    return left_start < right_end and right_start < left_end


def _require_valid_range(start: time, end: time) -> None:
    if start >= end:
        raise InvalidTimeRangeError("終了時刻は開始時刻より後にしてください")


__all__ = ["InvalidTimeRangeError", "time_ranges_overlap"]
