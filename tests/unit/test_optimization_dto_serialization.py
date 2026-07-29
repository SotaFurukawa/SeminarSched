from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date, time

import pytest

from summer_scheduler.optimization._serialization_helpers import MAX_SNAPSHOT_BYTES
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    DiagnosticCode,
    DiagnosticReason,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    ObjectiveBreakdown,
    OptimizationInput,
    OptimizationResult,
    OptimizationSettings,
    ScheduledAssignment,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
    UnassignedLesson,
)
from summer_scheduler.optimization.serialization import (
    SnapshotDecodeError,
    optimization_input_from_json,
    optimization_input_to_json,
    optimization_result_from_json,
    optimization_result_to_json,
)
from summer_scheduler.optimization.sessions import (
    SessionExpansionError,
    expand_sessions,
)


def test_required_sessions_are_expanded_to_one_based_immutable_sessions() -> None:
    requests = (
        _request(request_id=20, required_sessions=2),
        _request(request_id=10, required_sessions=3),
    )

    sessions = expand_sessions(requests)

    assert [(item.lesson_request_id, item.session_index) for item in sessions] == [
        (10, 1),
        (10, 2),
        (10, 3),
        (20, 1),
        (20, 2),
    ]
    with pytest.raises(FrozenInstanceError):
        sessions[0].session_index = 99  # type: ignore[misc]


@pytest.mark.parametrize("required_sessions", [0, -1])
def test_session_expansion_rejects_non_positive_required_sessions(
    required_sessions: int,
) -> None:
    with pytest.raises(SessionExpansionError, match="必要回数は1以上"):
        expand_sessions((_request(required_sessions=required_sessions),))


def test_session_expansion_rejects_duplicate_request_ids() -> None:
    with pytest.raises(SessionExpansionError, match="IDが重複"):
        expand_sessions((_request(), _request()))


def test_optimization_input_json_round_trip_preserves_japanese_fictional_data() -> None:
    source = _japanese_input()

    payload = optimization_input_to_json(source)
    restored = optimization_input_from_json(payload)

    assert restored == source
    assert "架空生徒・青空" in payload
    assert "架空講師・若葉" in payload
    assert "\\u67b6" not in payload


def test_optimization_result_json_round_trip_preserves_diagnostics() -> None:
    result = OptimizationResult(
        solver_status="FEASIBLE",
        assignments=(
            ScheduledAssignment(
                lesson_request_id=10,
                session_index=1,
                student_id=1,
                subject_id=100,
                teacher_id=2,
                day=date(2026, 8, 3),
                time_slot_id=11,
                is_locked=True,
            ),
        ),
        unassigned_lessons=(
            UnassignedLesson(
                lesson_request_id=10,
                session_index=2,
                student_id=1,
                subject_id=100,
                reasons=(
                    DiagnosticReason(
                        code=DiagnosticCode.PRIORITY_5_COMMON_SLOT_UNAVAILABLE,
                        message="担当必須講師との共通枠なし",
                        excluded_candidate_count=4,
                        details=(("講師", "架空講師・若葉"),),
                    ),
                ),
            ),
        ),
        objective_breakdown=ObjectiveBreakdown(
            unassigned_count=1,
            teacher_preference_penalty=2,
            active_teacher_slot_count=1,
            availability_preference_score=3,
            changed_assignment_count=0,
        ),
        elapsed_seconds=1.25,
        warnings=("架空データによる確認",),
    )

    restored = optimization_result_from_json(optimization_result_to_json(result))

    assert restored == result


def test_snapshot_decoder_rejects_unknown_fields_and_wrong_schema() -> None:
    source = json.loads(optimization_input_to_json(_japanese_input()))
    source["data"]["unexpected"] = "do not accept"
    with pytest.raises(SnapshotDecodeError, match="fieldが不正"):
        optimization_input_from_json(json.dumps(source))

    source = json.loads(optimization_input_to_json(_japanese_input()))
    source["schema"] = "dangerous.dynamic.Class"
    with pytest.raises(SnapshotDecodeError, match="schemaが一致"):
        optimization_input_from_json(json.dumps(source))


@pytest.mark.parametrize(
    "payload, message",
    [
        ('{"schema":"x","schema":"x","schema_version":1,"data":{}}', "重複"),
        (
            '{"schema":"summer_scheduler.optimization_input",'
            '"schema_version":1,"data":{"project_id":NaN}}',
            "非有限数",
        ),
    ],
)
def test_snapshot_decoder_rejects_duplicate_keys_and_non_finite_numbers(
    payload: str,
    message: str,
) -> None:
    with pytest.raises(SnapshotDecodeError, match=message):
        optimization_input_from_json(payload)


def test_snapshot_decoder_rejects_oversized_payload_before_parsing() -> None:
    with pytest.raises(SnapshotDecodeError, match="許容サイズ"):
        optimization_input_from_json(" " * (MAX_SNAPSHOT_BYTES + 1))


def test_dto_nested_collections_are_immutable() -> None:
    source = _japanese_input()

    with pytest.raises(FrozenInstanceError):
        source.project_id = 2  # type: ignore[misc]
    assert isinstance(source.teachers[0].qualified_subject_ids, frozenset)
    assert isinstance(source.lesson_requests[0].preferred_teacher_ids, tuple)


def _japanese_input() -> OptimizationInput:
    day = date(2026, 8, 3)
    return OptimizationInput(
        project_id=2026,
        open_dates=(day,),
        time_slots=(
            TimeSlotData(
                id=11,
                code="Y",
                display_name="Yコマ",
                start_time=time(14, 10),
                end_time=time(15, 30),
                sort_order=1,
            ),
        ),
        students=(
            StudentData(
                id=1,
                display_name="架空生徒・青空",
                default_max_consecutive_slots=3,
            ),
        ),
        teachers=(
            TeacherData(
                id=2,
                display_name="架空講師・若葉",
                qualified_subject_ids=frozenset({100}),
            ),
        ),
        subjects=(
            SubjectData(
                id=100,
                code="JH_MATH",
                display_name="中学校・数学",
            ),
        ),
        lesson_requests=(
            LessonRequestData(
                id=10,
                student_id=1,
                subject_id=100,
                required_sessions=2,
                regular_teacher_id=2,
                regular_teacher_priority=5,
                preferred_teacher_ids=(None, 2, None),
                one_to_one_required=True,
                max_consecutive_slots_override=3,
            ),
        ),
        availabilities=(
            AvailabilityData(
                owner_type="student",
                owner_id=1,
                day=day,
                time_slot_id=11,
                level=2,
            ),
            AvailabilityData(
                owner_type="teacher",
                owner_id=2,
                day=day,
                time_slot_id=11,
                level=1,
            ),
        ),
        group_blocks=(
            GroupBlockData(
                id=90,
                day=date(2026, 8, 4),
                start_time=time(13, 0),
                end_time=time(14, 0),
                student_ids=frozenset({1}),
            ),
        ),
        existing_assignments=(
            ExistingAssignmentData(
                id=80,
                lesson_request_id=10,
                session_index=1,
                day=day,
                time_slot_id=11,
                teacher_id=2,
                is_locked=True,
                is_manual=True,
            ),
        ),
        settings=_settings(),
    )


def _request(
    *,
    request_id: int = 10,
    required_sessions: int = 1,
) -> LessonRequestData:
    return LessonRequestData(
        id=request_id,
        student_id=1,
        subject_id=100,
        required_sessions=required_sessions,
    )


def _settings() -> OptimizationSettings:
    return OptimizationSettings(
        time_limit_seconds=30,
        random_seed=42,
        num_search_workers=1,
        regular_teacher_priority_weights=(1, 2, 3, 4),
        preferred_teacher_rank_weights=(3, 2, 1),
        student_preferred_time_weight=2,
        teacher_preferred_time_weight=1,
        preserve_existing_assignment_weight=3,
    )
