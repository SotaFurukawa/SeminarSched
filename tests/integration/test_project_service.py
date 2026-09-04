"""`.jukuschedule`プロジェクト管理の統合テスト。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from summer_scheduler.application.project_service import (
    ProjectFileError,
    ProjectService,
)
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    OpenDate,
    Student,
    Subject,
    Teacher,
    TeacherQualification,
    TimeSlot,
)


@pytest.fixture
def project_service(tmp_path: Path) -> Iterator[ProjectService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    service = ProjectService(registry, tmp_path / "バックアップ")
    yield service
    service.close_project()
    registry.dispose()


def test_create_save_reopen_and_recent_project(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_path = tmp_path / "日本語プロジェクト"

    created = project_service.create_project(
        project_path,
        title="2026年度 夏期講習",
        campus_name="架空校",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
    )

    assert created.path.name == "日本語プロジェクト.jukuschedule"
    assert created.path.is_file()
    database = project_service.require_database()
    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TimeSlot)) == 5
        assert session.scalar(select(func.count()).select_from(Subject)) == 26
        assert session.scalar(select(func.count()).select_from(OpenDate)) == 3

    project_service.close_project()
    reopened = project_service.open_project(created.path)

    assert reopened.title == "2026年度 夏期講習"
    assert reopened.campus_name == "架空校"
    assert project_service.recent_projects()[0].path == created.path

    assert project_service.mark_workflow_step_complete(2) == 2
    assert project_service.mark_workflow_step_complete(1) == 2
    project_service.close_project()
    project_service.open_project(created.path)
    assert project_service.workflow_completed_step() == 2


def test_recent_project_can_be_hidden_without_deleting_file(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    created = project_service.create_project(
        tmp_path / "非表示確認.jukuschedule",
        title="非表示確認",
        campus_name="架空校",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 21),
    )
    project_service.close_project()

    project_service.hide_recent_project(created.path)

    assert created.path.is_file()
    assert all(row.path != created.path for row in project_service.recent_projects())


def test_workspace_directories_and_automatic_project_path(
    project_service: ProjectService,
) -> None:
    assert project_service.student_directory.is_dir()
    assert project_service.teacher_directory.is_dir()
    assert project_service.projects_directory.is_dir()

    first = project_service.create_project_in_workspace(
        title="2026年度 夏期講習:本番/確認",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
    )
    assert first.path.parent == project_service.projects_directory
    assert first.path.name == "2026年度 夏期講習_本番_確認.jukuschedule"
    assert first.campus_name == "既定校舎"

    second = project_service.create_project_in_workspace(
        title="2026年度 夏期講習:本番/確認",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
    )
    assert second.path.name == "2026年度 夏期講習_本番_確認-2.jukuschedule"


def test_new_workspace_project_inherits_people_and_qualifications(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    project_service.create_project(
        tmp_path / "previous.jukuschedule",
        title="前回講習",
        campus_name="既定校舎",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 2),
    )
    database = project_service.require_database()
    with database.session_factory.begin() as session:
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        assert subject is not None
        student = Student(external_id="S001", name="架空 生徒", grade="中2", active=False)
        teacher = Teacher(external_id="T001", name="架空 講師", active=True)
        session.add_all([student, teacher])
        session.flush()
        session.add(
            TeacherQualification(
                teacher_id=teacher.id,
                subject_id=subject.id,
                can_teach=True,
            )
        )

    project_service.create_project_in_workspace(
        title="次回講習",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )
    inherited = project_service.require_database()
    with inherited.session_factory() as session:
        copied_student = session.scalar(select(Student).where(Student.external_id == "S001"))
        copied_teacher = session.scalar(select(Teacher).where(Teacher.external_id == "T001"))
        qualification = session.scalar(select(TeacherQualification))
    assert copied_student is not None and copied_student.active is False
    assert copied_teacher is not None and copied_teacher.active is True
    assert qualification is not None and qualification.can_teach is True


def test_save_as_duplicate_and_backup_keep_valid_sqlite_files(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    original = project_service.create_project(
        tmp_path / "元データ.jukuschedule",
        title="講習",
        campus_name="架空校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
    )

    duplicate = project_service.duplicate(tmp_path / "複製")
    backup = project_service.backup()
    saved_as = project_service.save_as(tmp_path / "別名保存")

    assert original.path.is_file()
    assert duplicate.is_file()
    assert backup.is_file()
    assert saved_as.path.name == "別名保存.jukuschedule"
    project_service.close_project()
    assert project_service.open_project(duplicate).title == "講習"


def test_open_rejects_non_project_sqlite(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "不正.jukuschedule"
    invalid.write_bytes(b"not a sqlite database")

    with pytest.raises(ProjectFileError, match="SQLite形式"):
        project_service.open_project(invalid)
