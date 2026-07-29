"""Phase 4 Repositoryの置換・履歴・transaction境界テスト。"""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    Campus,
    CourseProject,
    LessonRequest,
    OptimizationRun,
    Student,
    Subject,
    Teacher,
    TimeSlot,
)
from summer_scheduler.infrastructure.repositories import Phase4Repository


def _graph(
    repository: Phase4Repository,
) -> tuple[CourseProject, LessonRequest, Teacher, TimeSlot]:
    session = repository.session
    campus = Campus(name="架空つばさ校")
    student = Student(
        external_id="S-REPO-P4",
        name="架空 生徒",
        grade="中2",
        default_max_consecutive_slots=2,
        allow_gap=False,
        active=True,
    )
    teacher = Teacher(
        external_id="T-REPO-P4",
        name="架空 講師",
        allow_gap=False,
        active=True,
    )
    subject = Subject(
        code="REPO_P4_MATH",
        display_name="中学校・数学",
        school_level="中学校",
        sort_order=1,
        active=True,
    )
    session.add_all([campus, student, teacher, subject])
    session.flush()
    project = CourseProject(
        campus_id=campus.id,
        title="Repository Phase 4",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        status="editing",
        file_version=1,
    )
    session.add(project)
    session.flush()
    slot = TimeSlot(
        project_id=project.id,
        code="A",
        display_name="A",
        start_time=time(17, 10),
        end_time=time(18, 30),
        sort_order=1,
        enabled=True,
    )
    request = LessonRequest(
        project_id=project.id,
        student_id=student.id,
        subject_id=subject.id,
        required_sessions=3,
        regular_teacher_id_optional=teacher.id,
        regular_teacher_priority=3,
        one_to_one_required=False,
    )
    session.add_all([slot, request])
    session.flush()
    return project, request, teacher, slot


def _assignment(
    project: CourseProject,
    request: LessonRequest,
    teacher: Teacher,
    slot: TimeSlot,
    *,
    session_index: int,
    day: date,
    locked: bool = False,
) -> Assignment:
    return Assignment(
        project_id=project.id,
        lesson_request_id=request.id,
        session_index=session_index,
        date=day,
        time_slot_id=slot.id,
        teacher_id=teacher.id,
        is_locked=locked,
        is_manual=locked,
        created_by="manual" if locked else "solver",
    )


def _optimization_run(
    project_id: int,
    *,
    previous_assignment_id: int,
) -> OptimizationRun:
    return OptimizationRun(
        project_id=project_id,
        status="completed",
        solver_status="FEASIBLE",
        time_limit_seconds=30,
        objective_summary_json='{"unassigned_count":0}',
        unassigned_count=0,
        warning_count=1,
        input_snapshot_json='{"project_id":"1"}',
        result_snapshot_json=json.dumps(
            {"previous_assignments": [{"assignment_id": previous_assignment_id}]},
            ensure_ascii=False,
        ),
        random_seed=42,
        elapsed_seconds=1.5,
    )


def test_save_run_replaces_only_unlocked_and_rollback_restores_previous(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "Repository_日本語.jukuschedule")
    upgrade_database(database.engine)
    try:
        with database.session_factory() as session:
            repository = Phase4Repository(session)
            project, request, teacher, slot = _graph(repository)
            locked = repository.create_assignment(
                _assignment(
                    project,
                    request,
                    teacher,
                    slot,
                    session_index=1,
                    day=date(2026, 8, 4),
                    locked=True,
                )
            )
            previous = repository.create_assignment(
                _assignment(
                    project,
                    request,
                    teacher,
                    slot,
                    session_index=2,
                    day=date(2026, 8, 5),
                )
            )
            session.commit()
            ids = (
                project.id,
                request.id,
                teacher.id,
                slot.id,
                locked.id,
                previous.id,
            )

            matching_locked = _assignment(
                project,
                request,
                teacher,
                slot,
                session_index=1,
                day=date(2026, 8, 4),
                locked=True,
            )
            replacement = _assignment(
                project,
                request,
                teacher,
                slot,
                session_index=2,
                day=date(2026, 8, 6),
            )
            run = _optimization_run(
                project.id,
                previous_assignment_id=previous.id,
            )
            current = repository.save_run_and_replace_assignments(
                optimization_run=run,
                assignments=[matching_locked, replacement],
            )
            assert [row.id for row in current if row.is_locked] == [locked.id]
            assert replacement.optimization_run_id_optional == run.id
            replaced_row = repository.get_assignment(previous.id)
            assert replaced_row is replacement
            assert replaced_row.date == date(2026, 8, 6)
            snapshot = json.loads(run.result_snapshot_json)
            assert snapshot["previous_assignments"] == [{"assignment_id": previous.id}]
            assert session.in_transaction()

            session.rollback()
            session.expunge_all()
            project_id, _request_id, _teacher_id, _slot_id, locked_id, previous_id = ids
            restored = repository.list_assignments(project_id=project_id)
            assert [row.id for row in restored] == [locked_id, previous_id]
            assert repository.list_optimization_runs(project_id=project_id) == []
    finally:
        database.dispose()


def test_failed_save_rolls_back_run_and_assignment_replacement(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "Repository_rollback.jukuschedule")
    upgrade_database(database.engine)
    try:
        with database.session_factory() as session:
            repository = Phase4Repository(session)
            project, request, teacher, slot = _graph(repository)
            previous = repository.create_assignment(
                _assignment(
                    project,
                    request,
                    teacher,
                    slot,
                    session_index=1,
                    day=date(2026, 8, 5),
                )
            )
            session.commit()
            project_id = project.id
            previous_id = previous.id

            invalid = _assignment(
                project,
                request,
                teacher,
                slot,
                session_index=2,
                day=date(2026, 8, 6),
            )
            invalid.teacher_id = teacher.id + 9999
            run = _optimization_run(
                project.id,
                previous_assignment_id=previous.id,
            )
            with pytest.raises(IntegrityError):
                repository.save_run_and_replace_assignments(
                    optimization_run=run,
                    assignments=[invalid],
                )
            session.rollback()
            session.expunge_all()

            assert repository.get_assignment(previous_id) is not None
            assert repository.list_optimization_runs(project_id=project_id) == []
            assert session.scalar(select(Assignment).where(Assignment.id != previous_id)) is None
    finally:
        database.dispose()


def test_replace_rejects_locked_change_and_cross_project_before_delete(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "Repository_locked.jukuschedule")
    upgrade_database(database.engine)
    try:
        with database.session_factory() as session:
            repository = Phase4Repository(session)
            project, request, teacher, slot = _graph(repository)
            locked = repository.create_assignment(
                _assignment(
                    project,
                    request,
                    teacher,
                    slot,
                    session_index=1,
                    day=date(2026, 8, 4),
                    locked=True,
                )
            )
            session.commit()

            moved_locked = _assignment(
                project,
                request,
                teacher,
                slot,
                session_index=1,
                day=date(2026, 8, 5),
                locked=True,
            )
            with pytest.raises(ValueError, match="ロック済み"):
                repository.replace_assignments(
                    project_id=project.id,
                    assignments=[moved_locked],
                )
            assert repository.get_assignment(locked.id) is locked

            foreign = _assignment(
                project,
                request,
                teacher,
                slot,
                session_index=2,
                day=date(2026, 8, 5),
            )
            foreign.project_id = project.id + 1
            with pytest.raises(ValueError, match="別プロジェクト"):
                repository.replace_assignments(
                    project_id=project.id,
                    assignments=[foreign],
                )
            assert repository.get_assignment(locked.id) is locked
    finally:
        database.dispose()
