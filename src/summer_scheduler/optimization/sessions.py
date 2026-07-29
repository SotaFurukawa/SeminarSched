"""LessonRequestをsolverの個別セッションへ展開する純粋関数。"""

from __future__ import annotations

from collections.abc import Iterable

from summer_scheduler.optimization.dto import LessonRequestData, LessonSessionData


class SessionExpansionError(ValueError):
    """セッション展開前に検出した不正なLessonRequest。"""


def expand_sessions(
    lesson_requests: Iterable[LessonRequestData],
) -> tuple[LessonSessionData, ...]:
    """必要回数を1始まりの個別セッションへ決定論的に展開する。

    入力順序に依存しないスナップショットを得るため、request ID順に並べる。
    必要回数0以下は、黙って授業を消さず入力エラーにする。
    """
    requests = tuple(lesson_requests)
    duplicate_ids = _duplicate_ids(request.id for request in requests)
    if duplicate_ids:
        rendered = ", ".join(str(request_id) for request_id in sorted(duplicate_ids))
        raise SessionExpansionError(f"LessonRequest IDが重複しています: {rendered}")

    sessions: list[LessonSessionData] = []
    for request in sorted(requests, key=lambda item: item.id):
        if request.required_sessions <= 0:
            raise SessionExpansionError(
                f"LessonRequest {request.id} の必要回数は1以上にしてください"
            )
        sessions.extend(
            LessonSessionData(
                lesson_request_id=request.id,
                session_index=session_index,
                student_id=request.student_id,
                subject_id=request.subject_id,
                one_to_one_required=request.one_to_one_required,
                max_consecutive_slots_override=request.max_consecutive_slots_override,
                allow_gap_override=request.allow_gap_override,
            )
            for session_index in range(1, request.required_sessions + 1)
        )
    return tuple(sessions)


def _duplicate_ids(ids: Iterable[int]) -> set[int]:
    seen: set[int] = set()
    duplicates: set[int] = set()
    for value in ids:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


__all__ = ["SessionExpansionError", "expand_sessions"]
