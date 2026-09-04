"""Googleフォーム生徒・講師回答の一括取込みテスト。"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from summer_scheduler.application.course_survey_service import (
    CourseSurveyService,
    _canonical_questionnaire_subject,
)
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    ImportSourceSnapshot,
    LessonRequest,
    RegularLessonProfile,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TimeSlot,
)

_DAY = date(2026, 8, 1)


@pytest.fixture
def survey_service(tmp_path: Path) -> Iterator[CourseSurveyService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    projects = ProjectService(registry, tmp_path / "backups")
    project = projects.create_project(
        tmp_path / "summer.jukuschedule",
        title="夏期講習",
        campus_name="テスト校",
        start_date=_DAY,
        end_date=_DAY,
    )
    database = projects.require_database()
    with database.session_factory.begin() as session:
        student = Student(external_id="S001", name="山田 花子", grade="中2")
        teacher = Teacher(external_id="T001", name="田中 太郎")
        session.add_all((student, teacher))
        session.flush()
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        assert subject is not None
        session.add(
            RegularLessonProfile(
                project_id=project.project_id,
                student_id=student.id,
                subject_id=subject.id,
                regular_teacher_id_optional=teacher.id,
                regular_teacher_priority=4,
                one_to_one_required=False,
            )
        )
    yield CourseSurveyService(projects)
    projects.close_project()
    registry.dispose()


def test_generated_google_forms_answers_are_combined_and_stored(
    survey_service: CourseSurveyService,
    tmp_path: Path,
) -> None:
    student_csv = tmp_path / "生徒回答.csv"
    teacher_csv = tmp_path / "講師回答.csv"
    _write_csv(
        student_csv,
        (
            "タイムスタンプ",
            "姓（苗字）（必須）",
            "名（必須）",
            "学年（必須）",
            "在籍区分（必須）",
            "受講教科（中学校・1教科目）（必須）",
            "受講回数（中学校・1教科目）（必須）",
            "受講不可日時（チェックしたコマは受講不可） [2026-08-01（土）]",
            "特記事項",
        ),
        (
            (
                "2026/06/01",
                "山田",
                "花子",
                "中2",
                "在籍生",
                "数学",
                "3",
                "Z, A, B, C",
                "連続希望",
            ),
        ),
    )
    _write_csv(
        teacher_csv,
        (
            "タイムスタンプ",
            "姓（苗字）（必須）",
            "名（必須）",
            "出勤不可日時（チェックしたコマは出勤不可） [2026-08-01（土）]",
            "勤務に関する特記事項",
        ),
        (("2026/06/01", "田中", "太郎", "C 20:10～21:30", ""),),
    )

    preview = survey_service.prepare(student_csv, teacher_csv)
    assert not preview.has_errors
    result = survey_service.apply(preview)
    assert result.lesson_requests == 1

    database = survey_service._projects.require_database()  # noqa: SLF001
    with database.session_factory() as session:
        request = session.scalar(select(LessonRequest))
        student = session.scalar(select(Student).where(Student.external_id == "S001"))
        teacher = session.scalar(select(Teacher).where(Teacher.external_id == "T001"))
        unavailable_slots = {
            code: session.scalar(select(TimeSlot).where(TimeSlot.code == code))
            for code in ("Z", "A", "B", "C")
        }
        c_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "C"))
        snapshots = list(session.scalars(select(ImportSourceSnapshot)))
        assert student is not None and teacher is not None
        assert all(slot is not None for slot in unavailable_slots.values())
        assert c_slot is not None
        student_unavailable = {
            code: session.get(StudentAvailability, (1, student.id, _DAY, slot.id))
            for code, slot in unavailable_slots.items()
            if slot is not None
        }
        teacher_c = session.get(TeacherAvailability, (1, teacher.id, _DAY, c_slot.id))
    assert request is not None
    assert request.required_sessions == 3
    assert request.regular_teacher_priority == 4
    assert set(student_unavailable) == {"Z", "A", "B", "C"}
    assert all(
        row is not None and row.availability_level == 0 for row in student_unavailable.values()
    )
    assert teacher_c is not None and teacher_c.availability_level == 0
    assert {row.import_type for row in snapshots} == {
        "student_availability",
        "teacher_availability",
        "combined_course_survey",
    }
    combined_path = survey_service.export_latest_combined(tmp_path / "統合結果.xlsx")
    workbook = load_workbook(combined_path, data_only=True)
    try:
        assert workbook["受講希望（正規化）"]["C2"].value == "J2"
        assert workbook["生徒回答原本"]["D2"].value == "中2"
    finally:
        workbook.close()


@pytest.mark.parametrize(
    ("value", "header", "expected"),
    (
        ("日本史", "受講教科（高校・1教科目）（必須）", "高校・日本史"),
        ("化学(高)", "受講教科（他学年・1教科目）（必須）", "高校・化学"),
        ("理科（中）", "受講教科（他学年・1教科目）（必須）", "中学校・理科"),
        (
            "算数（中学受験以外）",
            "受講教科（小学校・1教科目）（必須）",
            "小学校・算数（中学受験以外なら可能）",
        ),
    ),
)
def test_short_questionnaire_subjects_restore_canonical_names(
    value: str,
    header: str,
    expected: str,
) -> None:
    assert _canonical_questionnaire_subject(value, header) == expected


def test_missing_trial_student_is_warning_and_project_local(
    survey_service: CourseSurveyService,
    tmp_path: Path,
) -> None:
    student_csv = tmp_path / "体験生回答.csv"
    teacher_csv = tmp_path / "講師回答.csv"
    _write_csv(
        student_csv,
        (
            "姓（苗字）（必須）",
            "名（必須）",
            "学年（必須）",
            "在籍区分（必須）",
            "受講教科（中学校・1教科目）（必須）",
            "受講回数（中学校・1教科目）（必須）",
            "受講不可日時 [2026-08-01（土）]",
        ),
        (("鈴木", "体験", "中1", "体験生", "中学校・数学", "1", ""),),
    )
    _write_csv(
        teacher_csv,
        (
            "姓（苗字）（必須）",
            "名（必須）",
            "出勤不可日時 [2026-08-01（土）]",
        ),
        (("田中", "太郎", ""),),
    )

    preview = survey_service.prepare(student_csv, teacher_csv)
    assert not preview.has_errors
    assert any(issue.severity == "warning" for issue in preview.issues)
    result = survey_service.apply(preview)
    assert result.trial_students == 1


def test_unregistered_student_can_be_resolved_as_project_local_trial(
    survey_service: CourseSurveyService,
    tmp_path: Path,
) -> None:
    student_csv = tmp_path / "未登録生徒回答.csv"
    teacher_csv = tmp_path / "講師回答.csv"
    _write_csv(
        student_csv,
        (
            "姓（苗字）（必須）",
            "名（必須）",
            "学年（必須）",
            "在籍区分（必須）",
            "受講教科（中学校・1教科目）（必須）",
            "受講回数（中学校・1教科目）（必須）",
            "受講不可日時 [2026-08-01（土）]",
        ),
        (("鈴木", "体験", "中1", "在籍生", "中学校・数学", "1", ""),),
    )
    _write_csv(
        teacher_csv,
        (
            "姓（苗字）（必須）",
            "名（必須）",
            "出勤不可日時 [2026-08-01（土）]",
        ),
        (("田中", "太郎", ""),),
    )

    unresolved = survey_service.prepare(student_csv, teacher_csv)
    assert unresolved.has_errors

    resolved = survey_service.prepare(
        student_csv,
        teacher_csv,
        trial_student_rows=frozenset({2}),
    )
    assert not resolved.has_errors
    assert resolved.students[0].enrollment_type == "体験生"
    result = survey_service.apply(resolved)
    assert result.trial_students == 1


def _write_csv(path: Path, headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)
