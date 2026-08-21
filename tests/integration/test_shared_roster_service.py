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
    read_shared_roster,
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
        assert workbook["生徒"]["A2"].value == "☑ 在籍"
        assert workbook["生徒"]["A3"].value == "☐ 退籍"
        assert workbook["生徒"]["F2"].value == "J2"
        assert workbook["生徒"]["F3"].value == "J3"
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
        assert workbook["生徒"]["B2"].value == "S-0001"
        assert workbook["生徒"]["F2"].value == "S2"
        assert workbook["講師"]["B2"].value == "T-0001"
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
        student_ids = {workbook["生徒"][f"B{row}"].value for row in (2, 3)}
        teacher_ids = {workbook["講師"][f"B{row}"].value for row in (2, 3)}
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
        assert workbook["生徒"]["B2"].value == "S-0002"
        assert workbook["講師"]["B2"].value == "T-0002"
    finally:
        workbook.close()


def test_shared_roster_prepares_status_first_defaults_and_required_cells(
    tmp_path: Path,
) -> None:
    path = tmp_path / "roster.xlsx"
    write_shared_roster(path, SharedRosterData((), (), ()))

    workbook = load_workbook(path, data_only=False)
    try:
        students = workbook["生徒"]
        teachers = workbook["講師"]
        assert students["A1"].value == "在籍（姓入力時は自動で☑）"
        assert students["B1"].value == "生徒ID（自動・入力不要）"
        assert "デフォルトは2" in str(students["G1"].value)
        assert "デフォルトはなし" in str(students["H1"].value)
        assert students["A2"].value == '=IF(C2="","","☑ 在籍")'
        assert str(students["B2"].value).startswith('=IF(C2="","","S-"')
        assert students["G2"].value == '=IF(C2="","",2)'
        assert students["H2"].value == '=IF(C2="","","なし")'
        assert students["C2"].fill.fgColor.rgb == "00FFF2CC"
        assert students["F2"].fill.fgColor.rgb == "00FFF2CC"
        assert teachers["A2"].value == '=IF(C2="","","☑ 在籍")'
        assert str(teachers["B2"].value).startswith('=IF(C2="","","T-"')
        assert teachers["F2"].value == '=IF(C2="","","なし")'
        assert teachers["C2"].fill.fgColor.rgb == "00FFF2CC"
        assert students.auto_filter.ref == "A1:I2"
        assert teachers.auto_filter.ref == "A1:G2"
    finally:
        workbook.close()


def test_surname_only_input_gets_ids_and_defaults_when_imported(tmp_path: Path) -> None:
    path = tmp_path / "surname_only.xlsx"
    write_shared_roster(path, SharedRosterData((), (), ()))
    workbook = load_workbook(path, data_only=False)
    try:
        workbook["生徒"]["C2"] = "新規"
        workbook["生徒"]["F2"] = "H2"
        workbook["講師"]["C2"] = "担当"
        workbook.save(path)
    finally:
        workbook.close()

    data = read_shared_roster(path)

    assert data.students == (SharedStudent("S-0001", "新規", "", "高2", 2, False, True, ""),)
    assert data.teachers == (SharedTeacher("T-0001", "担当", "", False, True, ""),)


def test_shared_roster_reads_legacy_person_column_order(tmp_path: Path) -> None:
    path = tmp_path / "legacy.xlsx"
    write_shared_roster(path, SharedRosterData((), (), ()))
    workbook = load_workbook(path)
    try:
        students = workbook["生徒"]
        students.delete_rows(1, students.max_row)
        students.append(
            (
                "生徒ID（自動・入力不要）",
                "姓（必須）",
                "名",
                "氏名（確認）",
                "学年（必須）",
                "標準最大連続コマ数",
                "空きコマ許可",
                "在籍",
                "備考",
            )
        )
        students.append(("S-0007", "旧式", "生徒", "旧式 生徒", "中2", 3, "はい", "☐ 退籍", "旧"))

        teachers = workbook["講師"]
        teachers.delete_rows(1, teachers.max_row)
        teachers.append(
            (
                "講師ID（自動・入力不要）",
                "姓（必須）",
                "名",
                "氏名（確認）",
                "空きコマ許可",
                "在籍",
                "備考",
            )
        )
        teachers.append(("T-0008", "旧式", "講師", "旧式 講師", "いいえ", "☑ 在籍", "旧"))
        workbook.save(path)
    finally:
        workbook.close()

    data = read_shared_roster(path)

    assert data.students == (SharedStudent("S-0007", "旧式", "生徒", "中2", 3, True, False, "旧"),)
    assert data.teachers == (SharedTeacher("T-0008", "旧式", "講師", False, True, "旧"),)
