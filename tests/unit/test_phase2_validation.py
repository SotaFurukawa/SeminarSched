"""Phase 2の既定値とDomain検証の単体テスト。"""

from __future__ import annotations

from datetime import date, time

from summer_scheduler.domain.defaults import DEFAULT_SUBJECTS, DEFAULT_TIME_SLOTS
from summer_scheduler.domain.validation import (
    TimeSlotInput,
    validate_lesson_request,
    validate_project,
    validate_time_slots,
)


def test_default_time_slots_match_master_specification() -> None:
    actual = [
        (
            item.code,
            item.start_time.isoformat(timespec="minutes"),
            item.end_time.isoformat(timespec="minutes"),
            item.sort_order,
        )
        for item in DEFAULT_TIME_SLOTS
    ]

    assert actual == [
        ("Y", "14:10", "15:30", 1),
        ("Z", "15:40", "17:00", 2),
        ("A", "17:10", "18:30", 3),
        ("B", "18:40", "20:00", 4),
        ("C", "20:10", "21:30", 5),
    ]


def test_default_subjects_have_23_stable_unique_codes() -> None:
    codes = {subject.code for subject in DEFAULT_SUBJECTS}
    displays = {subject.display_name for subject in DEFAULT_SUBJECTS}

    assert len(DEFAULT_SUBJECTS) == 23
    assert len(codes) == 23
    assert "高校・数学一般" in displays
    assert "高校・数学III" in displays
    assert "HS_MATH_GENERAL" in codes
    assert "HS_MATH_III" in codes


def test_time_slot_overlap_and_duplicate_order_are_errors() -> None:
    slots = (
        TimeSlotInput("Y", "Y", time(14, 10), time(15, 30), 1),
        TimeSlotInput("Z", "Z", time(15, 0), time(16, 0), 1),
    )

    issues = validate_time_slots(slots)

    assert {issue.code for issue in issues} == {"invalid", "time_overlap"}
    assert any("順序" in issue.message for issue in issues)
    assert any("時刻が重複" in issue.message for issue in issues)


def test_priority_five_requires_regular_teacher() -> None:
    issues = validate_lesson_request(
        required_sessions=2,
        regular_teacher_priority=5,
        regular_teacher_id=None,
        preferred_teacher_ids=(None, None, None),
        max_consecutive_slots_override=None,
        regular_teacher_can_teach=None,
    )

    assert any(issue.code == "priority_five_teacher" for issue in issues)
    assert all(issue.severity == "error" for issue in issues)


def test_project_end_date_cannot_precede_start_date() -> None:
    issues = validate_project(
        title="2026年度 夏期講習",
        campus_name="架空校",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 1),
    )

    assert len(issues) == 1
    assert issues[0].field == "end_date"
