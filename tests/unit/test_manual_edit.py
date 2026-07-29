"""Phase 5の純粋な手動編集preview境界を検証する。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, time

import pytest

from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    DiagnosticCode,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    OptimizationInput,
    OptimizationSettings,
    ScheduledAssignment,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
    UnassignedLesson,
)
from summer_scheduler.optimization.manual_edit import (
    EditDecision,
    EditOperation,
    EditOperationKind,
    EditPreview,
    EditPreviewCode,
    EditSchedule,
    EditTarget,
    MetricDirection,
    SoftMetricCode,
    SoftMetricDelta,
    preview_assign_unassigned,
    preview_edit,
    preview_move,
    preview_unassign,
)

DAY_1 = date(2026, 8, 3)
DAY_2 = date(2026, 8, 4)
CLOSED_DAY = date(2026, 8, 5)
Y = TimeSlotData(100, "Y", "Yコマ", time(14, 10), time(15, 30), 1)
Z = TimeSlotData(101, "Z", "Zコマ", time(15, 40), time(17, 0), 2)
A = TimeSlotData(102, "A", "Aコマ", time(17, 10), time(18, 30), 3)
SETTINGS = OptimizationSettings(
    time_limit_seconds=30,
    random_seed=7,
    num_search_workers=1,
    regular_teacher_priority_weights=(1, 3, 6, 10),
    preferred_teacher_rank_weights=(9, 6, 3),
    student_preferred_time_weight=2,
    teacher_preferred_time_weight=1,
    preserve_existing_assignment_weight=4,
)


def test_valid_move_is_green_and_does_not_mutate_current_schedule() -> None:
    request = _request(1, 1)
    data = _input((request,))
    generation = generate_candidates(data)
    current = _schedule(data, {(1, 1): _target(DAY_1, Y, 10)})

    preview = preview_move(
        data,
        generation,
        current,
        lesson_request_id=1,
        session_index=1,
        target=_target(DAY_1, Y, 20),
    )

    assert preview.allowed
    assert preview.decision is EditDecision.GREEN
    assert preview.code is EditPreviewCode.ALLOWED
    assert preview.current_schedule.assignments[0].teacher_id == 10
    assert preview.proposed_schedule.assignments[0].teacher_id == 20
    assert all(not delta.worsened for delta in preview.soft_deltas)


@pytest.mark.parametrize(
    ("mutate", "target"),
    [
        (
            lambda data: replace(
                data,
                availabilities=tuple(
                    replace(item, level=0)
                    if (
                        item.owner_type == "student"
                        and item.owner_id == 1
                        and item.day == DAY_1
                        and item.time_slot_id == Z.id
                    )
                    else item
                    for item in data.availabilities
                ),
            ),
            EditTarget(DAY_1, Z.id, 10),
        ),
        (
            lambda data: replace(
                data,
                availabilities=tuple(
                    replace(item, level=0)
                    if (
                        item.owner_type == "teacher"
                        and item.owner_id == 20
                        and item.day == DAY_1
                        and item.time_slot_id == Y.id
                    )
                    else item
                    for item in data.availabilities
                ),
            ),
            EditTarget(DAY_1, Y.id, 20),
        ),
        (
            lambda data: replace(
                data,
                teachers=tuple(
                    replace(item, qualified_subject_ids=frozenset()) if item.id == 20 else item
                    for item in data.teachers
                ),
            ),
            EditTarget(DAY_1, Y.id, 20),
        ),
        (
            lambda data: data,
            EditTarget(day=CLOSED_DAY, time_slot_id=Y.id, teacher_id=10),
        ),
    ],
)
def test_candidate_boundary_rejects_unavailable_unqualified_or_closed_target(
    mutate: Callable[[OptimizationInput], OptimizationInput],
    target: EditTarget,
) -> None:
    request = _request(1, 1)
    base = _input((request,))
    data = mutate(base)
    generation = generate_candidates(data)
    current = _schedule(data, {(1, 1): _target(DAY_1, Y, 10)})

    preview = preview_move(
        data,
        generation,
        current,
        lesson_request_id=1,
        session_index=1,
        target=target,
    )

    assert preview.decision is EditDecision.RED
    assert DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE in _hard_codes(preview)


def test_priority_five_teacher_change_is_rejected_at_candidate_boundary() -> None:
    request = _request(
        1,
        1,
        regular_teacher_id=10,
        regular_teacher_priority=5,
    )
    data = _input((request,))
    current = _schedule(data, {(1, 1): _target(DAY_1, Y, 10)})

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=1,
        session_index=1,
        target=_target(DAY_1, Y, 20),
    )

    assert not preview.allowed
    assert DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE in _hard_codes(preview)


def test_group_lesson_conflict_is_rejected_at_candidate_boundary() -> None:
    request = _request(1, 1)
    group = GroupBlockData(
        id=1,
        day=DAY_1,
        start_time=Z.start_time,
        end_time=Z.end_time,
        student_ids=frozenset({1}),
    )
    data = _input((request,), groups=(group,))
    current = _schedule(data, {(1, 1): _target(DAY_1, Y, 10)})

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=1,
        session_index=1,
        target=_target(DAY_1, Z, 10),
    )

    assert preview.decision is EditDecision.RED
    assert DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE in _hard_codes(preview)


def test_group_lesson_teacher_conflict_is_rejected_at_candidate_boundary() -> None:
    request = _request(1, 1)
    group = GroupBlockData(
        id=1,
        day=DAY_1,
        start_time=Z.start_time,
        end_time=Z.end_time,
        teacher_id=20,
    )
    data = _input((request,), groups=(group,))
    current = _schedule(data, {(1, 1): _target(DAY_1, Y, 10)})

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=1,
        session_index=1,
        target=_target(DAY_1, Z, 20),
    )

    assert preview.decision is EditDecision.RED
    assert DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE in _hard_codes(preview)


def test_disabled_time_slot_is_rejected_at_candidate_boundary() -> None:
    request = _request(1, 1)
    data = _input((request,))
    disabled_a = replace(A, enabled=False)
    data = replace(
        data,
        time_slots=(Y, Z, disabled_a),
    )
    current = _schedule(data, {(1, 1): _target(DAY_1, Y, 10)})

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=1,
        session_index=1,
        target=_target(DAY_1, disabled_a, 10),
    )

    assert preview.decision is EditDecision.RED
    assert DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE in _hard_codes(preview)


def test_student_simultaneous_assignment_is_rejected() -> None:
    requests = (_request(1, 1), _request(2, 1))
    data = _input(requests)
    current = _schedule(
        data,
        {
            (1, 1): _target(DAY_1, Y, 10),
            (2, 1): _target(DAY_1, Z, 20),
        },
    )

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=2,
        session_index=1,
        target=_target(DAY_1, Y, 20),
    )

    assert DiagnosticCode.STUDENT_TIME_CONFLICT in _hard_codes(preview)


def test_teacher_capacity_three_is_rejected() -> None:
    requests = tuple(_request(index, index) for index in (1, 2, 3))
    data = _input(requests)
    current = _schedule(
        data,
        {
            (1, 1): _target(DAY_1, Y, 10),
            (2, 1): _target(DAY_1, Y, 10),
            (3, 1): _target(DAY_1, Y, 20),
        },
    )

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=3,
        session_index=1,
        target=_target(DAY_1, Y, 10),
    )

    assert DiagnosticCode.TEACHER_CAPACITY_EXCEEDED in _hard_codes(preview)


def test_adding_to_one_to_one_slot_is_rejected() -> None:
    requests = (_request(1, 1, one_to_one=True), _request(2, 2))
    data = _input(requests)
    current = _schedule(
        data,
        {
            (1, 1): _target(DAY_1, Y, 10),
            (2, 1): _target(DAY_1, Y, 20),
        },
    )

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=2,
        session_index=1,
        target=_target(DAY_1, Y, 10),
    )

    assert DiagnosticCode.ONE_TO_ONE_CAPACITY in _hard_codes(preview)


def test_student_gap_is_rejected_after_move() -> None:
    requests = (_request(1, 1), _request(2, 1))
    teachers = (
        TeacherData(10, "架空講師10", frozenset({500}), allow_gap=True),
        TeacherData(20, "架空講師20", frozenset({500}), allow_gap=True),
    )
    data = _input(requests, teachers=teachers)
    current = _schedule(
        data,
        {
            (1, 1): _target(DAY_1, Y, 10),
            (2, 1): _target(DAY_1, Z, 20),
        },
    )

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=2,
        session_index=1,
        target=_target(DAY_1, A, 20),
    )

    assert DiagnosticCode.STUDENT_GAP_NOT_ALLOWED in _hard_codes(preview)


def test_teacher_gap_is_rejected_after_move() -> None:
    requests = (_request(1, 1), _request(2, 2))
    data = _input(requests)
    current = _schedule(
        data,
        {
            (1, 1): _target(DAY_1, Y, 10),
            (2, 1): _target(DAY_1, Z, 10),
        },
    )

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=2,
        session_index=1,
        target=_target(DAY_1, A, 10),
    )

    assert DiagnosticCode.TEACHER_GAP_NOT_ALLOWED in _hard_codes(preview)


def test_student_consecutive_limit_is_rejected_after_move() -> None:
    requests = tuple(_request(index, 1) for index in (1, 2, 3))
    teachers = tuple(
        TeacherData(index, f"架空講師{index}", frozenset({500}), allow_gap=True)
        for index in (10, 20, 30)
    )
    data = _input(requests, teachers=teachers)
    current = _schedule(
        data,
        {
            (1, 1): _target(DAY_1, Y, 10),
            (2, 1): _target(DAY_1, Z, 20),
            (3, 1): _target(DAY_2, Y, 30),
        },
    )

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=3,
        session_index=1,
        target=_target(DAY_1, A, 30),
    )

    assert DiagnosticCode.STUDENT_CONSECUTIVE_LIMIT in _hard_codes(preview)


@pytest.mark.parametrize("operation_kind", [EditOperationKind.MOVE, EditOperationKind.UNASSIGN])
def test_locked_source_cannot_be_moved_or_unassigned(
    operation_kind: EditOperationKind,
) -> None:
    request = _request(1, 1)
    data = _input((request,))
    current = _schedule(
        data,
        {(1, 1): _target(DAY_1, Y, 10)},
        locked=frozenset({(1, 1)}),
    )
    operation = EditOperation(
        kind=operation_kind,
        lesson_request_id=1,
        session_index=1,
        target=(_target(DAY_1, Z, 10) if operation_kind is EditOperationKind.MOVE else None),
    )

    preview = preview_edit(data, generate_candidates(data), current, operation)

    assert preview.code is EditPreviewCode.HARD_REJECTED
    assert DiagnosticCode.LOCKED_ASSIGNMENT_NOT_PRESERVED in _hard_codes(preview)


def test_locked_target_capacity_is_not_bypassed() -> None:
    requests = tuple(_request(index, index) for index in (1, 2, 3))
    existing = (
        _existing(1, requests[0], Y, 10, locked=True),
        _existing(2, requests[1], Y, 10, locked=True),
    )
    data = _input(requests, existing=existing)
    current = _schedule(
        data,
        {
            (1, 1): _target(DAY_1, Y, 10),
            (2, 1): _target(DAY_1, Y, 10),
            (3, 1): _target(DAY_1, Y, 20),
        },
        locked=frozenset({(1, 1), (2, 1)}),
    )

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=3,
        session_index=1,
        target=_target(DAY_1, Y, 10),
    )

    assert preview.decision is EditDecision.RED
    assert DiagnosticCode.ASSIGNMENT_NOT_CANDIDATE in _hard_codes(preview)
    assert DiagnosticCode.TEACHER_CAPACITY_EXCEEDED in _hard_codes(preview)


def test_unassigned_can_be_added_and_assignment_can_be_removed_without_partition_loss() -> None:
    request = _request(1, 1)
    data = _input((request,))
    generation = generate_candidates(data)
    unassigned = _schedule(data, {(1, 1): None})

    added = preview_assign_unassigned(
        data,
        generation,
        unassigned,
        lesson_request_id=1,
        session_index=1,
        target=_target(DAY_1, Y, 10),
    )

    assert added.allowed
    assert len(added.proposed_schedule.assignments) == 1
    assert added.proposed_schedule.unassigned_lessons == ()

    removed = preview_unassign(
        data,
        generation,
        added.proposed_schedule,
        lesson_request_id=1,
        session_index=1,
    )
    assert removed.allowed
    assert removed.decision is EditDecision.YELLOW
    assert removed.proposed_schedule.assignments == ()
    assert len(removed.proposed_schedule.unassigned_lessons) == 1
    assert _delta_by_code(removed, SoftMetricCode.UNASSIGNED_COUNT).worsened


def test_soft_warning_reports_all_required_before_after_deltas() -> None:
    request_1 = _request(1, 1)
    request_2 = _request(
        2,
        2,
        regular_teacher_id=10,
        regular_teacher_priority=4,
        preferred_teacher_ids=(10, None, None),
    )
    existing = (_existing(1, request_2, Y, 10),)
    data = _input(
        (request_1, request_2),
        existing=existing,
        preferred_availability=frozenset(
            {
                ("student", 2, DAY_1, Y.id),
                ("teacher", 10, DAY_1, Y.id),
            }
        ),
    )
    current = _schedule(
        data,
        {
            (1, 1): _target(DAY_1, Y, 10),
            (2, 1): _target(DAY_1, Y, 10),
        },
    )

    preview = preview_move(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=2,
        session_index=1,
        target=_target(DAY_1, Z, 20),
    )

    assert preview.decision is EditDecision.YELLOW
    required_worsened = {
        SoftMetricCode.REGULAR_TEACHER_PENALTY,
        SoftMetricCode.PREFERRED_TEACHER_PENALTY,
        SoftMetricCode.PREFERRED_TIME_SCORE,
        SoftMetricCode.PAIRED_SLOT_COUNT,
        SoftMetricCode.ACTIVE_TEACHER_SLOT_COUNT,
        SoftMetricCode.CHANGED_EXISTING_ASSIGNMENT_COUNT,
    }
    assert required_worsened <= {item.code for item in preview.worsened_soft_deltas}
    assert all("→" in item.message for item in preview.soft_deltas)


def test_metric_direction_controls_worsening_for_minimize_and_maximize() -> None:
    lower = SoftMetricDelta(
        SoftMetricCode.ACTIVE_TEACHER_SLOT_COUNT,
        "稼働講師枠数",
        MetricDirection.LOWER_IS_BETTER,
        1,
        2,
    )
    higher = SoftMetricDelta(
        SoftMetricCode.PREFERRED_TIME_SCORE,
        "希望日時",
        MetricDirection.HIGHER_IS_BETTER,
        3,
        2,
    )
    improved_lower = replace(lower, after_value=0)
    improved_higher = replace(higher, after_value=4)

    assert lower.worsened
    assert higher.worsened
    assert not improved_lower.worsened
    assert not improved_higher.worsened


def test_invalid_current_partition_is_rejected_before_operation() -> None:
    request = _request(1, 1)
    data = _input((request,))
    current = EditSchedule(assignments=(), unassigned_lessons=())

    preview = preview_assign_unassigned(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=1,
        session_index=1,
        target=_target(DAY_1, Y, 10),
    )

    assert preview.code is EditPreviewCode.INVALID_CURRENT_SCHEDULE
    assert DiagnosticCode.SESSION_MISSING in _hard_codes(preview)


def test_wrong_partition_side_is_an_invalid_operation_with_japanese_message() -> None:
    request = _request(1, 1)
    data = _input((request,))
    current = _schedule(data, {(1, 1): _target(DAY_1, Y, 10)})

    preview = preview_assign_unassigned(
        data,
        generate_candidates(data),
        current,
        lesson_request_id=1,
        session_index=1,
        target=_target(DAY_1, Z, 10),
    )

    assert preview.code is EditPreviewCode.INVALID_OPERATION
    assert preview.hard_issues[0].message == "指定した授業は未配置一覧にありません"


def _input(
    requests: tuple[LessonRequestData, ...],
    *,
    teachers: tuple[TeacherData, ...] | None = None,
    existing: tuple[ExistingAssignmentData, ...] = (),
    groups: tuple[GroupBlockData, ...] = (),
    preferred_availability: frozenset[tuple[str, int, date, int]] = frozenset(),
) -> OptimizationInput:
    student_ids = sorted({request.student_id for request in requests})
    students = tuple(StudentData(item, f"架空生徒{item}") for item in student_ids)
    actual_teachers = teachers or (
        TeacherData(10, "架空講師10", frozenset({500})),
        TeacherData(20, "架空講師20", frozenset({500})),
    )
    availability: list[AvailabilityData] = []
    for student in students:
        for day in (DAY_1, DAY_2):
            for slot in (Y, Z, A):
                key = ("student", student.id, day, slot.id)
                availability.append(
                    AvailabilityData(
                        "student",
                        student.id,
                        day,
                        slot.id,
                        2 if key in preferred_availability else 1,
                    )
                )
    for teacher in actual_teachers:
        for day in (DAY_1, DAY_2):
            for slot in (Y, Z, A):
                key = ("teacher", teacher.id, day, slot.id)
                availability.append(
                    AvailabilityData(
                        "teacher",
                        teacher.id,
                        day,
                        slot.id,
                        2 if key in preferred_availability else 1,
                    )
                )
    return OptimizationInput(
        project_id=1,
        open_dates=(DAY_1, DAY_2),
        time_slots=(Y, Z, A),
        students=students,
        teachers=actual_teachers,
        subjects=(SubjectData(500, "JH_MATH", "中学校・数学"),),
        lesson_requests=requests,
        availabilities=tuple(availability),
        group_blocks=groups,
        existing_assignments=existing,
        settings=SETTINGS,
    )


def _request(
    request_id: int,
    student_id: int,
    *,
    one_to_one: bool = False,
    regular_teacher_id: int | None = None,
    regular_teacher_priority: int = 1,
    preferred_teacher_ids: tuple[int | None, int | None, int | None] = (
        None,
        None,
        None,
    ),
) -> LessonRequestData:
    return LessonRequestData(
        id=request_id,
        student_id=student_id,
        subject_id=500,
        required_sessions=1,
        regular_teacher_id=regular_teacher_id,
        regular_teacher_priority=regular_teacher_priority,
        preferred_teacher_ids=preferred_teacher_ids,
        one_to_one_required=one_to_one,
    )


def _target(day: date, slot: TimeSlotData, teacher_id: int) -> EditTarget:
    return EditTarget(day=day, time_slot_id=slot.id, teacher_id=teacher_id)


def _schedule(
    data: OptimizationInput,
    placements: dict[tuple[int, int], EditTarget | None],
    *,
    locked: frozenset[tuple[int, int]] = frozenset(),
) -> EditSchedule:
    requests = {item.id: item for item in data.lesson_requests}
    assignments: list[ScheduledAssignment] = []
    unassigned: list[UnassignedLesson] = []
    for key, target in placements.items():
        request = requests[key[0]]
        if target is None:
            unassigned.append(
                UnassignedLesson(
                    lesson_request_id=key[0],
                    session_index=key[1],
                    student_id=request.student_id,
                    subject_id=request.subject_id,
                    reasons=(),
                )
            )
        else:
            assignments.append(
                ScheduledAssignment(
                    lesson_request_id=key[0],
                    session_index=key[1],
                    student_id=request.student_id,
                    subject_id=request.subject_id,
                    teacher_id=target.teacher_id,
                    day=target.day,
                    time_slot_id=target.time_slot_id,
                    is_locked=key in locked,
                )
            )
    return EditSchedule(tuple(assignments), tuple(unassigned))


def _existing(
    assignment_id: int,
    request: LessonRequestData,
    slot: TimeSlotData,
    teacher_id: int,
    *,
    locked: bool = False,
) -> ExistingAssignmentData:
    return ExistingAssignmentData(
        id=assignment_id,
        lesson_request_id=request.id,
        session_index=1,
        day=DAY_1,
        time_slot_id=slot.id,
        teacher_id=teacher_id,
        is_locked=locked,
    )


def _hard_codes(
    preview: EditPreview,
) -> set[DiagnosticCode | object]:
    return {item.code for item in preview.hard_issues}


def _delta_by_code(
    preview: EditPreview,
    code: SoftMetricCode,
) -> SoftMetricDelta:
    return next(item for item in preview.soft_deltas if item.code is code)
