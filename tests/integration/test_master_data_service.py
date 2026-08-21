"""Phase 2マスター管理Application Serviceの統合テスト。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time
from pathlib import Path

import pytest

from summer_scheduler.application.master_data_service import MasterDataService
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.domain.validation import DomainValidationError
from summer_scheduler.infrastructure.db import create_database, upgrade_database


@pytest.fixture
def master_service(tmp_path: Path) -> Iterator[MasterDataService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    projects = ProjectService(registry, tmp_path / "backups")
    projects.create_project(
        tmp_path / "講習.jukuschedule",
        title="夏期講習",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
    )
    yield MasterDataService(projects)
    projects.close_project()
    registry.dispose()


def test_duplicate_student_and_teacher_ids_are_rejected(
    master_service: MasterDataService,
) -> None:
    master_service.save_student(
        record_id=None,
        external_id="S001",
        name="架空 花子",
        grade="中1",
        default_max_consecutive_slots=2,
        allow_gap=False,
        note="",
        active=True,
    )
    with pytest.raises(DomainValidationError, match="生徒IDが重複"):
        master_service.save_student(
            record_id=None,
            external_id="S001",
            name="架空 太郎",
            grade="中2",
            default_max_consecutive_slots=2,
            allow_gap=False,
            note="",
            active=True,
        )

    master_service.save_teacher(
        record_id=None,
        external_id="T001",
        name="講師 一郎",
        allow_gap=False,
        note="",
        active=True,
    )
    with pytest.raises(DomainValidationError, match="講師IDが重複"):
        master_service.save_teacher(
            record_id=None,
            external_id="T001",
            name="講師 二郎",
            allow_gap=False,
            note="",
            active=True,
        )


def test_blank_student_and_teacher_ids_are_generated_in_sequence(
    master_service: MasterDataService,
) -> None:
    for name in ("架空 花子", "架空 太郎"):
        master_service.save_student(
            record_id=None,
            external_id="",
            name=name,
            grade="中1",
            default_max_consecutive_slots=2,
            allow_gap=False,
            note="",
            active=True,
        )
    for name in ("講師 一郎", "講師 二郎"):
        master_service.save_teacher(
            record_id=None,
            external_id="",
            name=name,
            allow_gap=False,
            note="",
            active=True,
        )

    assert [row.external_id for row in master_service.list_students()] == ["S-0001", "S-0002"]
    assert [row.external_id for row in master_service.list_teachers()] == ["T-0001", "T-0002"]


def test_student_grade_filter_accepts_common_japanese_notation(
    master_service: MasterDataService,
) -> None:
    master_service.save_student(
        record_id=None,
        external_id="S-GRADE",
        name="架空 学年",
        grade="中学2年",
        default_max_consecutive_slots=2,
        allow_gap=False,
        note="",
        active=True,
    )

    filtered = master_service.list_students(grade="中2")
    assert [student.external_id for student in filtered] == ["S-GRADE"]


def test_qualification_and_lesson_request_rules(
    master_service: MasterDataService,
) -> None:
    student_id = master_service.save_student(
        record_id=None,
        external_id="S001",
        name="架空 花子",
        grade="高1",
        default_max_consecutive_slots=2,
        allow_gap=False,
        note="",
        active=True,
    ).record_id
    teacher_id = master_service.save_teacher(
        record_id=None,
        external_id="T001",
        name="講師 一郎",
        allow_gap=False,
        note="",
        active=True,
    ).record_id
    subject = next(
        item for item in master_service.list_subjects() if item.code == "HS_MATH_GENERAL"
    )

    with pytest.raises(DomainValidationError, match="優先度5"):
        master_service.save_lesson_request(
            record_id=None,
            student_id=student_id,
            subject_id=subject.id,
            required_sessions=2,
            regular_teacher_id=None,
            regular_teacher_priority=5,
            preferred_teacher_1_id=None,
            preferred_teacher_2_id=None,
            preferred_teacher_3_id=None,
            one_to_one_required=False,
            max_consecutive_slots_override=None,
            allow_gap_override=None,
            note="",
        )

    master_service.set_qualification(
        teacher_id,
        subject.id,
        can_teach=True,
    )
    saved = master_service.save_lesson_request(
        record_id=None,
        student_id=student_id,
        subject_id=subject.id,
        required_sessions=2,
        regular_teacher_id=teacher_id,
        regular_teacher_priority=5,
        preferred_teacher_1_id=teacher_id,
        preferred_teacher_2_id=None,
        preferred_teacher_3_id=None,
        one_to_one_required=False,
        max_consecutive_slots_override=2,
        allow_gap_override=False,
        note="",
    )

    assert saved.warnings == ()
    assert len(master_service.list_lesson_requests(student_id=student_id)) == 1
    with pytest.raises(DomainValidationError, match="受講希望が重複"):
        master_service.save_lesson_request(
            record_id=None,
            student_id=student_id,
            subject_id=subject.id,
            required_sessions=1,
            regular_teacher_id=teacher_id,
            regular_teacher_priority=2,
            preferred_teacher_1_id=None,
            preferred_teacher_2_id=None,
            preferred_teacher_3_id=None,
            one_to_one_required=False,
            max_consecutive_slots_override=None,
            allow_gap_override=None,
            note="",
        )


def test_time_slot_overlap_is_rejected(master_service: MasterDataService) -> None:
    with pytest.raises(DomainValidationError, match="時刻が重複"):
        master_service.save_time_slot(
            record_id=None,
            code="X",
            display_name="追加",
            start_time=time(15, 0),
            end_time=time(16, 0),
            sort_order=6,
            enabled=True,
        )


def test_open_date_bulk_and_project_period_update(
    master_service: MasterDataService,
) -> None:
    master_service.set_weekday_closed(6)
    assert any(
        row.date.weekday() == 6 and not row.is_open for row in master_service.list_open_dates()
    )

    master_service.update_project(
        title="夏期講習 改訂",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 5),
    )

    assert len(master_service.list_open_dates()) == 5
    assert master_service.project_details().title == "夏期講習 改訂"


def test_selected_open_dates_are_updated_atomically_and_keep_notes(
    master_service: MasterDataService,
) -> None:
    first = date(2026, 8, 1)
    second = date(2026, 8, 2)
    third = date(2026, 8, 3)
    master_service.set_open_date(first, is_open=True, note="午前のみ")

    master_service.set_open_dates_state((first, third, first), is_open=False)

    rows = {row.date: row for row in master_service.list_open_dates()}
    assert rows[first].is_open is False
    assert rows[first].note == "午前のみ"
    assert rows[second].is_open is True
    assert rows[third].is_open is False

    before = {day: row.is_open for day, row in rows.items()}
    with pytest.raises(DomainValidationError, match="講習期間外"):
        master_service.set_open_dates_state(
            (second, date(2026, 8, 4)),
            is_open=False,
        )
    after = {row.date: row.is_open for row in master_service.list_open_dates()}
    assert after == before


def test_selected_open_dates_require_at_least_one_date(
    master_service: MasterDataService,
) -> None:
    with pytest.raises(DomainValidationError, match="1日以上"):
        master_service.set_open_dates_state((), is_open=False)
