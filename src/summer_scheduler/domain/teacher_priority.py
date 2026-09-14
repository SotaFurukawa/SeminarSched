"""通常担当講師の優先度を最低担当回数へ変換する。"""

from __future__ import annotations

_MINIMUM_NUMERATOR_BY_PRIORITY = {
    1: 0,
    2: 1,
    3: 2,
    4: 3,
    5: 4,
}
_DENOMINATOR = 4


def minimum_regular_teacher_sessions(required_sessions: int, priority: int) -> int:
    """通常担当へ必ず割り当てる回数を25%刻み・端数切上げで返す。"""
    if required_sessions < 0:
        raise ValueError("必要授業回数は0以上で指定してください")
    try:
        numerator = _MINIMUM_NUMERATOR_BY_PRIORITY[priority]
    except KeyError as exc:
        raise ValueError("通常担当講師の優先度は1～5で指定してください") from exc
    return (required_sessions * numerator + _DENOMINATOR - 1) // _DENOMINATOR


def maximum_other_teacher_sessions(required_sessions: int, priority: int) -> int:
    """通常担当以外へ割り当ててもよい最大回数を返す。"""
    return required_sessions - minimum_regular_teacher_sessions(required_sessions, priority)


__all__ = ["maximum_other_teacher_sessions", "minimum_regular_teacher_sessions"]
