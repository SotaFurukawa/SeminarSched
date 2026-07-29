"""Phase 6出力スナップショットと設定Repositoryの結合テスト。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db import Database, create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    Campus,
    CourseProject,
    GroupLesson,
    GroupLessonStudent,
    LessonRequest,
    OpenDate,
    OutputSetting,
    Student,
    Subject,
    Teacher,
    TimeSlot,
    ValidationIssue,
)
from summer_scheduler.infrastructure.repositories import (
    OutputRepository,
    OutputRepositoryError,
)
from summer_scheduler.reporting.settings import DEFAULT_STYLE_RULES, OutputSettings
from summer_scheduler.shared.settings import load_settings

DAY_ONE = date(2026, 8, 1)
DAY_TWO = date(2026, 8, 2)
DAY_THREE = date(2026, 8, 3)


@pytest.fixture
def seeded_database(tmp_path: Path) -> Iterator[tuple[Database, dict[str, int]]]:
    database = create_database(tmp_path / "日本語 出力データ" / "出力Repository.jukuschedule")
    upgrade_database(database.engine)
    with database.session_factory.begin() as session:
        ids = _seed_graph(session)
    yield database, ids
    database.dispose()


def _seed_graph(session: Session) -> dict[str, int]:
    campus = Campus(
        name="架空みらい校",
        address_optional="架空県架空市1-2-3",
        logo_path_optional=r"C:\校舎素材\架空ロゴ.png",
    )
    students = (
        Student(
            external_id="S-OUT-001",
            name="架空 とても長い氏名の生徒一郎",
            grade="中学2年",
            default_max_consecutive_slots=2,
            allow_gap=False,
            note="生徒備考",
            active=True,
        ),
        Student(
            external_id="S-OUT-002",
            name="架空 生徒二郎",
            grade="中学3年",
            default_max_consecutive_slots=2,
            allow_gap=False,
            active=True,
        ),
    )
    teachers = (
        Teacher(
            external_id="T-OUT-001",
            name="架空 講師一郎",
            allow_gap=False,
            note="講師備考",
            active=True,
        ),
        Teacher(
            external_id="T-OUT-002",
            name="架空 講師二郎",
            allow_gap=False,
            active=True,
        ),
    )
    subject = Subject(
        code="OUT_MATH",
        display_name="架空数学",
        school_level="中学校",
        sort_order=901,
        active=True,
    )
    session.add_all([campus, *students, *teachers, subject])
    session.flush()
    project = CourseProject(
        campus_id=campus.id,
        title="架空校 2026夏期講習",
        start_date=DAY_ONE,
        end_date=DAY_THREE,
        status="editing",
        file_version=1,
    )
    session.add(project)
    session.flush()
    slots = (
        TimeSlot(
            project_id=project.id,
            code="Y",
            display_name="Yコマ",
            start_time=time(14, 10),
            end_time=time(15, 30),
            sort_order=1,
            enabled=True,
        ),
        TimeSlot(
            project_id=project.id,
            code="Z",
            display_name="Zコマ",
            start_time=time(15, 40),
            end_time=time(17, 0),
            sort_order=2,
            enabled=True,
        ),
    )
    session.add_all(
        [
            *slots,
            OpenDate(
                project_id=project.id,
                date=DAY_ONE,
                is_open=True,
                note="",
            ),
            OpenDate(
                project_id=project.id,
                date=DAY_TWO,
                is_open=False,
                note="全館休校",
            ),
        ]
    )
    session.flush()
    requests = (
        LessonRequest(
            project_id=project.id,
            student_id=students[0].id,
            subject_id=subject.id,
            required_sessions=2,
            regular_teacher_id_optional=teachers[0].id,
            regular_teacher_priority=5,
            one_to_one_required=True,
            note="受講希望備考1",
        ),
        LessonRequest(
            project_id=project.id,
            student_id=students[1].id,
            subject_id=subject.id,
            required_sessions=1,
            regular_teacher_id_optional=teachers[0].id,
            regular_teacher_priority=3,
            preferred_teacher_1_id_optional=teachers[1].id,
            one_to_one_required=False,
            note="受講希望備考2",
        ),
    )
    session.add_all(requests)
    session.flush()
    assignment = Assignment(
        project_id=project.id,
        lesson_request_id=requests[0].id,
        session_index=1,
        date=DAY_ONE,
        time_slot_id=slots[0].id,
        teacher_id=teachers[0].id,
        is_locked=True,
        is_manual=True,
        created_by="manual",
        note="割当備考",
    )
    group = GroupLesson(
        project_id=project.id,
        group_code="GROUP-OUT-001",
        grade="中学3年",
        subject_id=subject.id,
        course_name="架空 集団数学",
        date=DAY_TWO,
        start_time=time(15, 30),
        end_time=time(17, 10),
        teacher_id_optional=teachers[1].id,
        room_optional="架空教室A",
        note="集団授業備考",
    )
    session.add_all([assignment, group])
    session.flush()
    session.add(
        GroupLessonStudent(
            group_lesson_id=group.id,
            student_id=students[1].id,
        )
    )
    session.add_all(
        [
            ValidationIssue(
                project_id=project.id,
                severity="error",
                issue_type="one_to_one_assignment_conflict",
                entity_type="assignment",
                entity_id_optional=str(assignment.id),
                message="1対1必須枠を確認してください",
                details_json="{}",
                resolved=False,
            ),
            ValidationIssue(
                project_id=project.id,
                severity="warning",
                issue_type="preferred_teacher_unqualified",
                entity_type="lesson_request",
                entity_id_optional=str(requests[1].id),
                message="第1希望講師はこの科目の資格がありません",
                details_json=json.dumps(
                    {
                        "student_id": students[1].id,
                        "subject_id": subject.id,
                    },
                    ensure_ascii=False,
                ),
                resolved=False,
            ),
            ValidationIssue(
                project_id=project.id,
                severity="info",
                issue_type="group_reviewed",
                entity_type="group_lesson",
                entity_id_optional=str(group.id),
                message="集団授業を確認しました",
                details_json="{}",
                resolved=True,
            ),
        ]
    )
    session.flush()
    return {
        "project": project.id,
        "campus": campus.id,
        "student_1": students[0].id,
        "student_2": students[1].id,
        "teacher_1": teachers[0].id,
        "teacher_2": teachers[1].id,
        "subject": subject.id,
        "request_1": requests[0].id,
        "request_2": requests[1].id,
        "slot_y": slots[0].id,
        "group": group.id,
    }


def test_build_base_snapshot_copies_all_output_facts_and_resolves_warnings(
    seeded_database: tuple[Database, dict[str, int]],
) -> None:
    database, ids = seeded_database
    generated_at = datetime(2026, 7, 29, 4, 30, tzinfo=UTC)

    with database.session_factory() as session:
        snapshot = OutputRepository(session).build_base_snapshot(
            ids["project"],
            generated_at=generated_at,
        )

    assert snapshot.project.title == "架空校 2026夏期講習"
    assert snapshot.project.campus_name == "架空みらい校"
    assert snapshot.project.generated_at == generated_at
    assert snapshot.project.logo_path_optional == r"C:\校舎素材\架空ロゴ.png"
    assert [(row.day, row.is_open, row.configured, row.note) for row in snapshot.dates] == [
        (DAY_ONE, True, True, ""),
        (DAY_TWO, False, True, "全館休校"),
        (DAY_THREE, False, False, ""),
    ]
    assert [row.code for row in snapshot.slots] == ["Y", "Z"]
    assert snapshot.students[0].name == "架空 とても長い氏名の生徒一郎"
    assert snapshot.teachers[0].external_id == "T-OUT-001"
    assert snapshot.subjects[0].code == "OUT_MATH"
    assert snapshot.lesson_requests[0].required_sessions == 2
    assert snapshot.lesson_requests[0].one_to_one_required is True
    assert snapshot.assignments[0].is_locked is True
    assert snapshot.assignments[0].is_manual is True
    assert snapshot.assignments[0].note == "割当備考"
    assert snapshot.group_lessons[0].student_ids == (ids["student_2"],)
    assert snapshot.group_lessons[0].room == "架空教室A"
    assert snapshot.unassigned == ()

    assert len(snapshot.warnings) == 2
    assignment_warning = snapshot.warnings[0]
    assert assignment_warning.severity == "error"
    assert assignment_warning.day_optional == DAY_ONE
    assert assignment_warning.slot_code == "Y"
    assert assignment_warning.student_name == "架空 とても長い氏名の生徒一郎"
    assert assignment_warning.teacher_name == "架空 講師一郎"
    assert assignment_warning.student_ids == (ids["student_1"],)
    assert assignment_warning.teacher_id_optional == ids["teacher_1"]
    assert assignment_warning.status == "未対応"
    preferred_warning = snapshot.warnings[1]
    assert preferred_warning.student_name == "架空 生徒二郎"
    assert preferred_warning.teacher_name == "架空 講師二郎"


def test_snapshot_can_include_resolved_warning_with_group_context(
    seeded_database: tuple[Database, dict[str, int]],
) -> None:
    database, ids = seeded_database

    with database.session_factory() as session:
        snapshot = OutputRepository(session).build_base_snapshot(
            ids["project"],
            include_resolved_warnings=True,
        )

    assert len(snapshot.warnings) == 3
    resolved = snapshot.warnings[-1]
    assert resolved.issue_type == "group_reviewed"
    assert resolved.day_optional == DAY_TWO
    assert resolved.student_name == "架空 生徒二郎"
    assert resolved.teacher_name == "架空 講師二郎"
    assert resolved.status == "対応済み"


def test_settings_round_trip_preserves_every_field_and_uses_campus_logo(
    seeded_database: tuple[Database, dict[str, int]],
) -> None:
    database, ids = seeded_database
    custom_styles = (
        replace(
            DEFAULT_STYLE_RULES[0],
            marker="[個別1対1]",
            fill_color="#AABBCC",
        ),
        *DEFAULT_STYLE_RULES[1:],
    )
    expected = OutputSettings(
        project_id=ids["project"],
        paper_size="A4",
        orientation="portrait",
        logo_path_optional=r"D:\日本語素材\新しいロゴ.png",
        visible_fields=("note", "grade", "manual"),
        days_per_page=5,
        teacher_columns_per_page=13,
        font_size=10.5,
        margin_mm=12.25,
        file_name_pattern="{project}_{report}_{date}",
        default_output_directory_optional=r"D:\夏期講習 出力",
        student_page_mode="combined",
        csv_with_bom=False,
        style_rules=custom_styles,
    )

    with database.session_factory.begin() as session:
        saved = OutputRepository(session).upsert_settings(expected)
        assert saved == expected

    with database.session_factory() as session:
        repository = OutputRepository(session)
        unrelated_defaults = replace(
            load_settings().output,
            paper_size="A3",
            days_per_page=7,
        )
        assert (
            repository.get_settings(
                ids["project"],
                defaults=unrelated_defaults,
            )
            == expected
        )
        row = session.get(OutputSetting, ids["project"])
        campus = session.get(Campus, ids["campus"])
        assert row is not None
        assert campus is not None
        assert json.loads(row.visible_fields_json) == ["note", "grade", "manual"]
        assert json.loads(row.style_rules_json)[0]["marker"] == "[個別1対1]"
        assert campus.logo_path_optional == expected.logo_path_optional
        assert session.scalar(select(func.count()).select_from(OutputSetting)) == 1

    with database.session_factory.begin() as session:
        campus = session.get(Campus, ids["campus"])
        assert campus is not None
        campus.logo_path_optional = r"E:\校舎正本\差替ロゴ.png"
    with database.session_factory() as session:
        loaded = OutputRepository(session).get_settings(ids["project"])
        assert loaded.logo_path_optional == r"E:\校舎正本\差替ロゴ.png"
        assert loaded.paper_size == "A4"


def test_default_settings_and_invalid_project_are_explicit(
    seeded_database: tuple[Database, dict[str, int]],
) -> None:
    database, ids = seeded_database
    with database.session_factory() as session:
        repository = OutputRepository(session)
        defaults = repository.get_settings(ids["project"])
        assert defaults == OutputSettings(
            project_id=ids["project"],
            logo_path_optional=r"C:\校舎素材\架空ロゴ.png",
        )
        configured_defaults = replace(
            load_settings().output,
            paper_size="A4",
            orientation="portrait",
            days_per_page=4,
            teacher_columns_per_page=5,
            font_size=11.0,
            margin_mm=6.5,
            csv_with_bom=False,
            file_name_pattern="{project}_{report}",
            default_output_directory_optional=r"C:\型付き既定出力",
        )
        assert repository.get_settings(
            ids["project"],
            defaults=configured_defaults,
        ) == configured_defaults.for_project(
            ids["project"],
            logo_path_optional=r"C:\校舎素材\架空ロゴ.png",
        )
        with pytest.raises(OutputRepositoryError, match="見つかりません"):
            repository.build_base_snapshot(ids["project"] + 999)
