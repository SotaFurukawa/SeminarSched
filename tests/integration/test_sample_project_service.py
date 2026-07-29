"""匿名サンプルプロジェクトの再現性と安全性。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, select

from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.application.project_validation_service import ProjectValidationService
from summer_scheduler.application.sample_project_service import SampleProjectService
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    GroupLesson,
    LessonRequest,
    Student,
    Teacher,
)


@pytest.fixture
def project_service(tmp_path: Path) -> Iterator[ProjectService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    service = ProjectService(registry, tmp_path / "バックアップ")
    yield service
    service.close_project()
    registry.dispose()


def test_create_anonymous_sample_contains_phase3_scenarios(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    summary = SampleProjectService(project_service).create_anonymous_sample(
        tmp_path / "日本語 匿名サンプル"
    )

    assert summary.path.name == "日本語 匿名サンプル.jukuschedule"
    database = project_service.require_database()
    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Student)) == 10
        assert session.scalar(select(func.count()).select_from(Teacher)) == 5
        assert session.scalar(select(func.count()).select_from(GroupLesson)) == 1
        requests = list(session.scalars(select(LessonRequest)))
        assert any(row.regular_teacher_priority == 5 for row in requests)
        assert any(row.one_to_one_required for row in requests)
        assert any(row.max_consecutive_slots_override_optional == 3 for row in requests)
        assert all("架空" in row.name for row in session.scalars(select(Student)))
        assert all("架空" in row.name for row in session.scalars(select(Teacher)))

    issues = ProjectValidationService(project_service).list_issues()
    assert issues
    assert all(issue.severity == "warning" for issue in issues)
    assert {issue.issue_type for issue in issues} == {"preferred_teacher_unqualified"}
