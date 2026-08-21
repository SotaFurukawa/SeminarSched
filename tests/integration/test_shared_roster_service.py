"""講習から独立した共通名簿の統合テスト。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.application.shared_roster_service import SharedRosterService
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    RegularLessonProfile,
    Student,
    Subject,
    Teacher,
    TeacherQualification,
)
from summer_scheduler.infrastructure.excel.shared_roster import (
    SharedQualification,
    SharedRegularLesson,
    SharedRosterData,
    SharedStudent,
    SharedSubject,
    SharedTeacher,
    write_shared_roster,
)


@pytest.fixture
def roster_service(tmp_path: Path) -> Iterator[SharedRosterService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    projects = ProjectService(
        registry,
        tmp_path / "backups",
        workspace_directory=tmp_path / "workspace",
    )
    projects.create_project(
        tmp_path / "summer.jukuschedule",
        title="夏期講習",
        campus_name="テスト校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
    )
    service = SharedRosterService(projects)
    yield service
    projects.close_project()
    registry.dispose()


def test_shared_roster_syncs_people_qualifications_and_regular_lessons(
    roster_service: SharedRosterService,
) -> None:
    write_shared_roster(
        roster_service.path,
        SharedRosterData(
            students=(
                SharedStudent("S001", "山田", "花子", "中2"),
                SharedStudent("S002", "佐藤", "次郎", "中3", active=False),
            ),
            teachers=(SharedTeacher("T001", "田中", "太郎"),),
            subjects=(SharedSubject("JH_MATH", "中学校・数学", "junior_high", 1),),
            qualifications=(SharedQualification("T001", "JH_MATH"),),
            regular_lessons=(SharedRegularLesson("S001", "JH_MATH", "T001", 4, False),),
        ),
    )

    result = roster_service.sync_to_current_project()

    assert result.students == 2
    database = roster_service._projects.require_database()  # noqa: SLF001
    with database.session_factory() as session:
        students = list(session.scalars(select(Student).order_by(Student.external_id)))
        teacher = session.scalar(select(Teacher).where(Teacher.external_id == "T001"))
        qualification = session.scalar(select(TeacherQualification))
        profile = session.scalar(select(RegularLessonProfile))
        subjects = list(session.scalars(select(Subject).order_by(Subject.sort_order)))
    assert [(row.name, row.active) for row in students] == [
        ("山田 花子", True),
        ("佐藤 次郎", False),
    ]
    assert teacher is not None
    assert qualification is not None and qualification.can_teach is True
    assert profile is not None
    assert profile.regular_teacher_id_optional == teacher.id
    assert profile.regular_teacher_priority == 4
    assert len(subjects) == 26
    assert {row.display_name for row in subjects} >= {
        "小学校・算数（中学受験）",
        "小学校・算数（中学受験以外なら可能）",
        "小学校・国語（中学受験）",
        "小学校・国語（中学受験以外なら可能）",
        "高校・数学IA",
        "高校・数学IIBC",
        "高校・数学III",
    }

    workbook = load_workbook(roster_service.path, data_only=False)
    try:
        assert workbook["生徒"]["E2"].value == "J2"
        assert workbook["生徒"]["E3"].value == "J3"
        assert workbook["生徒"]["H3"].value == "☐ 退籍"
        assert len(workbook["生徒"].conditional_formatting) > 0
        assert workbook["通常授業"]["J2"].value == 4
        assert workbook["科目"].max_row == 27
    finally:
        workbook.close()


def test_blank_ids_are_generated_and_persisted(roster_service: SharedRosterService) -> None:
    write_shared_roster(
        roster_service.path,
        SharedRosterData(
            students=(SharedStudent("", "山田", "花子", "小2"),),
            teachers=(SharedTeacher("", "田中", "太郎"),),
            subjects=(SharedSubject("ES_MATH", "小学校・算数", "elementary", 1),),
        ),
    )

    roster_service.sync_to_current_project()

    workbook = load_workbook(roster_service.path, data_only=False)
    try:
        assert workbook["生徒"]["A2"].value == "S-0001"
        assert workbook["生徒"]["E2"].value == "S2"
        assert workbook["講師"]["A2"].value == "T-0001"
    finally:
        workbook.close()


def test_blank_ids_do_not_collide_with_ids_on_later_rows(
    roster_service: SharedRosterService,
) -> None:
    write_shared_roster(
        roster_service.path,
        SharedRosterData(
            students=(
                SharedStudent("", "青木", "花子", "小2"),
                SharedStudent("S-0001", "山田", "太郎", "中1"),
            ),
            teachers=(
                SharedTeacher("", "伊藤", "一郎"),
                SharedTeacher("T0001", "田中", "二郎"),
            ),
            subjects=(SharedSubject("ES_MATH", "小学校・算数", "elementary", 1),),
        ),
    )

    roster_service.sync_to_current_project()

    workbook = load_workbook(roster_service.path, data_only=False)
    try:
        student_ids = {workbook["生徒"][f"A{row}"].value for row in (2, 3)}
        teacher_ids = {workbook["講師"][f"A{row}"].value for row in (2, 3)}
        assert student_ids == {"S-0001", "S-0002"}
        assert teacher_ids == {"T0001", "T-0002"}
    finally:
        workbook.close()


def test_blank_ids_do_not_reuse_an_id_only_present_in_the_project(
    roster_service: SharedRosterService,
) -> None:
    database = roster_service._projects.require_database()  # noqa: SLF001
    with database.session_factory.begin() as session:
        session.add(Student(external_id="S-0001", name="過去 生徒", grade="中3", active=False))
        session.add(Teacher(external_id="T-0001", name="過去 講師", active=False))
    write_shared_roster(
        roster_service.path,
        SharedRosterData(
            students=(SharedStudent("", "新規", "生徒", "小2"),),
            teachers=(SharedTeacher("", "新規", "講師"),),
            subjects=(SharedSubject("ES_MATH", "小学校・算数", "elementary", 1),),
        ),
    )

    roster_service.sync_to_current_project()

    workbook = load_workbook(roster_service.path, data_only=False)
    try:
        assert workbook["生徒"]["A2"].value == "S-0002"
        assert workbook["講師"]["A2"].value == "T-0002"
    finally:
        workbook.close()
