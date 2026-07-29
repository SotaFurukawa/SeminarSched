from __future__ import annotations

from dataclasses import replace
from datetime import date, time

from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    CandidateGenerationResult,
    DiagnosticCode,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    OptimizationInput,
    OptimizationSettings,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
)

DAY = date(2026, 8, 3)
CLOSED_DAY = date(2026, 8, 4)


def test_priority_five_creates_candidates_only_for_regular_teacher() -> None:
    source = _base_input(
        request=replace(
            _request(),
            regular_teacher_id=10,
            regular_teacher_priority=5,
        )
    )

    result = generate_candidates(source)

    candidates = result.candidates_for(1000, 1)
    assert {candidate.teacher_id for candidate in candidates} == {10}
    assert DiagnosticCode.PRIORITY_5_TEACHER_REQUIRED in _codes(result, 1000, 1)


def test_priority_five_unavailable_teacher_is_not_replaced_and_is_diagnosed() -> None:
    source = _base_input(
        request=replace(
            _request(),
            regular_teacher_id=10,
            regular_teacher_priority=5,
        )
    )
    source = replace(
        source,
        availabilities=tuple(
            item
            for item in source.availabilities
            if not (item.owner_type == "teacher" and item.owner_id == 10)
        ),
    )

    result = generate_candidates(source)

    assert result.candidates_for(1000, 1) == ()
    codes = _codes(result, 1000, 1)
    assert DiagnosticCode.TEACHER_UNAVAILABLE in codes
    assert DiagnosticCode.PRIORITY_5_COMMON_SLOT_UNAVAILABLE in codes
    assert DiagnosticCode.NO_CANDIDATE in codes


def test_arbitrary_group_time_overlap_uses_half_open_intervals() -> None:
    overlapping = replace(
        _base_input(),
        group_blocks=(
            GroupBlockData(
                id=1,
                day=DAY,
                start_time=time(15, 0),
                end_time=time(15, 45),
                student_ids=frozenset({1}),
            ),
        ),
    )

    blocked = generate_candidates(overlapping)

    assert blocked.candidates_for(1000, 1) == ()
    assert DiagnosticCode.GROUP_LESSON_CONFLICT in _codes(blocked, 1000, 1)

    touching_only = replace(
        overlapping,
        group_blocks=(
            GroupBlockData(
                id=2,
                day=DAY,
                start_time=time(15, 30),
                end_time=time(16, 0),
                student_ids=frozenset({1}),
            ),
        ),
    )
    assert generate_candidates(touching_only).candidates_for(1000, 1)


def test_locked_assignment_restricts_own_session_to_exact_target() -> None:
    second_slot = TimeSlotData(
        id=101,
        code="Z",
        display_name="Zコマ",
        start_time=time(15, 40),
        end_time=time(17, 0),
        sort_order=2,
    )
    source = _base_input()
    extra_availability = tuple(replace(item, time_slot_id=101) for item in source.availabilities)
    source = replace(
        source,
        time_slots=source.time_slots + (second_slot,),
        availabilities=source.availabilities + extra_availability,
        existing_assignments=(
            ExistingAssignmentData(
                id=1,
                lesson_request_id=1000,
                session_index=1,
                day=DAY,
                time_slot_id=100,
                teacher_id=10,
                is_locked=True,
            ),
        ),
    )

    candidates = generate_candidates(source).candidates_for(1000, 1)

    assert [
        (candidate.day, candidate.time_slot_id, candidate.teacher_id) for candidate in candidates
    ] == [(DAY, 100, 10)]


def test_locked_assignment_blocks_same_student_at_same_time() -> None:
    second_request = replace(_request(), id=2000)
    source = _base_input()
    source = replace(
        source,
        lesson_requests=(source.lesson_requests[0], second_request),
        existing_assignments=(
            ExistingAssignmentData(
                id=1,
                lesson_request_id=2000,
                session_index=1,
                day=DAY,
                time_slot_id=100,
                teacher_id=10,
                is_locked=True,
            ),
        ),
    )

    result = generate_candidates(source)

    assert result.candidates_for(1000, 1) == ()
    assert DiagnosticCode.LOCKED_ASSIGNMENT_CONFLICT in _codes(result, 1000, 1)


def test_closed_disabled_zero_unqualified_and_inactive_options_are_filtered() -> None:
    enabled_but_unavailable = TimeSlotData(
        id=102,
        code="A",
        display_name="Aコマ",
        start_time=time(17, 10),
        end_time=time(18, 30),
        sort_order=3,
    )
    disabled = TimeSlotData(
        id=101,
        code="Z",
        display_name="Zコマ",
        start_time=time(15, 40),
        end_time=time(17, 0),
        sort_order=2,
        enabled=False,
    )
    source = _base_input()
    source = replace(
        source,
        time_slots=(source.time_slots[0], disabled, enabled_but_unavailable),
        teachers=source.teachers
        + (
            TeacherData(
                id=30,
                display_name="架空講師・無資格",
                qualified_subject_ids=frozenset(),
            ),
            TeacherData(
                id=40,
                display_name="架空講師・休職",
                qualified_subject_ids=frozenset({500}),
                active=False,
            ),
        ),
        availabilities=source.availabilities
        + (
            AvailabilityData("student", 1, DAY, 101, 2),
            AvailabilityData("student", 1, DAY, 102, 0),
            AvailabilityData("student", 1, CLOSED_DAY, 100, 2),
            AvailabilityData("teacher", 10, DAY, 101, 2),
            AvailabilityData("teacher", 10, DAY, 102, 2),
            AvailabilityData("teacher", 10, CLOSED_DAY, 100, 2),
            AvailabilityData("teacher", 20, DAY, 101, 2),
            AvailabilityData("teacher", 20, DAY, 102, 2),
            AvailabilityData("teacher", 20, CLOSED_DAY, 100, 2),
            AvailabilityData("teacher", 30, DAY, 100, 2),
            AvailabilityData("teacher", 40, DAY, 100, 2),
        ),
    )

    result = generate_candidates(source)

    assert {
        (candidate.day, candidate.time_slot_id, candidate.teacher_id)
        for candidate in result.candidates_for(1000, 1)
    } == {(DAY, 100, 10), (DAY, 100, 20)}
    codes = _codes(result, 1000, 1)
    assert {
        DiagnosticCode.CLOSED_DATE,
        DiagnosticCode.DISABLED_TIME_SLOT,
        DiagnosticCode.STUDENT_UNAVAILABLE,
        DiagnosticCode.TEACHER_UNQUALIFIED,
        DiagnosticCode.INACTIVE_TEACHER,
    }.issubset(codes)


def test_inactive_master_produces_structured_zero_candidate_diagnostic() -> None:
    source = _base_input()
    source = replace(
        source,
        subjects=(replace(source.subjects[0], active=False),),
    )

    result = generate_candidates(source)

    assert result.candidates_for(1000, 1) == ()
    assert _codes(result, 1000, 1) == {
        DiagnosticCode.INACTIVE_SUBJECT,
        DiagnosticCode.NO_CANDIDATE,
    }


def test_ambiguous_duplicate_availability_fails_closed() -> None:
    source = _base_input()
    source = replace(
        source,
        availabilities=source.availabilities + (source.availabilities[0],),
    )

    result = generate_candidates(source)

    assert not result.candidates
    assert result.input_diagnostics
    assert result.input_diagnostics[0].code is DiagnosticCode.INVALID_INPUT


def test_existing_assignment_session_outside_required_range_fails_closed() -> None:
    source = _base_input()
    source = replace(
        source,
        existing_assignments=(
            ExistingAssignmentData(
                id=1,
                lesson_request_id=1000,
                session_index=2,
                day=DAY,
                time_slot_id=100,
                teacher_id=10,
                is_locked=False,
            ),
        ),
    )

    result = generate_candidates(source)

    assert not result.candidates
    assert any(reason.code is DiagnosticCode.INVALID_INPUT for reason in result.input_diagnostics)


def _base_input(
    *,
    request: LessonRequestData | None = None,
) -> OptimizationInput:
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY,),
        time_slots=(
            TimeSlotData(
                id=100,
                code="Y",
                display_name="Yコマ",
                start_time=time(14, 10),
                end_time=time(15, 30),
                sort_order=1,
            ),
        ),
        students=(StudentData(id=1, display_name="架空生徒・青空"),),
        teachers=(
            TeacherData(
                id=10,
                display_name="架空講師・若葉",
                qualified_subject_ids=frozenset({500}),
            ),
            TeacherData(
                id=20,
                display_name="架空講師・夕凪",
                qualified_subject_ids=frozenset({500}),
            ),
        ),
        subjects=(
            SubjectData(
                id=500,
                code="JH_MATH",
                display_name="中学校・数学",
            ),
        ),
        lesson_requests=(request or _request(),),
        availabilities=(
            AvailabilityData("student", 1, DAY, 100, 2),
            AvailabilityData("teacher", 10, DAY, 100, 2),
            AvailabilityData("teacher", 20, DAY, 100, 1),
        ),
        group_blocks=(),
        existing_assignments=(),
        settings=OptimizationSettings(
            time_limit_seconds=30,
            random_seed=7,
            num_search_workers=1,
            regular_teacher_priority_weights=(1, 2, 3, 4),
            preferred_teacher_rank_weights=(3, 2, 1),
            student_preferred_time_weight=2,
            teacher_preferred_time_weight=1,
            preserve_existing_assignment_weight=3,
        ),
    )


def _request() -> LessonRequestData:
    return LessonRequestData(
        id=1000,
        student_id=1,
        subject_id=500,
        required_sessions=1,
    )


def _codes(
    result: CandidateGenerationResult,
    request_id: int,
    session_index: int,
) -> set[DiagnosticCode]:
    diagnostic = result.diagnostics_for(request_id, session_index)
    assert diagnostic is not None
    return {reason.code for reason in diagnostic.reasons}
