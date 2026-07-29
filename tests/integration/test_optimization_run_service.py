"""OptimizationRunServiceのprepare/finalize安全境界テスト。"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from summer_scheduler.application.optimization_run_service import (
    OptimizationFinalizationError,
    OptimizationInputChangedError,
    OptimizationPreparationError,
    OptimizationRunService,
)
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    LessonRequest,
    OptimizationRun,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TeacherQualification,
    TimeSlot,
)
from summer_scheduler.optimization.dto import (
    ObjectiveBreakdown,
    OptimizationResult,
    ScheduledAssignment,
)
from summer_scheduler.optimization.serialization import optimization_input_to_json
from summer_scheduler.optimization.solver import solve_optimization
from summer_scheduler.shared.settings import OptimizationAppSettings


@dataclass(frozen=True, slots=True)
class _Graph:
    project_id: int
    student_id: int
    teacher_id: int
    subject_id: int
    request_id: int
    target_slot_id: int
    previous_slot_id: int
    previous_assignment_id: int
    day: date


@pytest.fixture
def project_service(tmp_path: Path) -> Iterator[ProjectService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    service = ProjectService(registry, tmp_path / "バックアップ")
    service.create_project(
        tmp_path / "最適化実行.jukuschedule",
        title="架空校 夏期講習",
        campus_name="架空みらい校",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
    )
    yield service
    service.close_project()
    registry.dispose()


def _app_settings() -> OptimizationAppSettings:
    return OptimizationAppSettings(
        default_preset="standard",
        fast_time_limit_seconds=30.1,
        standard_time_limit_seconds=120.0,
        high_quality_time_limit_seconds=600.0,
        random_seed=42,
        num_search_workers=1,
        regular_teacher_priority_weights=(1, 2, 3, 4),
        preferred_teacher_rank_weights=(30, 20, 10),
        student_preferred_time_weight=3,
        teacher_preferred_time_weight=2,
        preserve_existing_assignment_weight=5,
        optional_balance_weight=0,
    )


def _seed_valid_graph(projects: ProjectService) -> _Graph:
    database = projects.require_database()
    project_id = projects.require_project().project_id
    day = date(2026, 8, 1)
    with database.session_factory.begin() as session:
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        target_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "Y"))
        previous_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "Z"))
        assert subject is not None
        assert target_slot is not None
        assert previous_slot is not None
        student = Student(
            external_id="S-RUN-001",
            name="架空 同姓名",
            grade="中2",
            default_max_consecutive_slots=2,
            allow_gap=False,
            active=True,
        )
        same_name_student = Student(
            external_id="S-RUN-002",
            name="架空 同姓名",
            grade="中3",
            default_max_consecutive_slots=2,
            allow_gap=False,
            active=True,
        )
        teacher = Teacher(
            external_id="T-RUN-001",
            name="架空 実行講師",
            allow_gap=False,
            active=True,
        )
        session.add_all([student, same_name_student, teacher])
        session.flush()
        session.add(
            TeacherQualification(
                teacher_id=teacher.id,
                subject_id=subject.id,
                can_teach=True,
            )
        )
        request = LessonRequest(
            project_id=project_id,
            student_id=student.id,
            subject_id=subject.id,
            required_sessions=1,
            regular_teacher_id_optional=teacher.id,
            regular_teacher_priority=5,
            one_to_one_required=False,
        )
        session.add(request)
        session.flush()
        session.add_all(
            [
                StudentAvailability(
                    project_id=project_id,
                    student_id=student.id,
                    date=day,
                    time_slot_id=target_slot.id,
                    availability_level=2,
                ),
                TeacherAvailability(
                    project_id=project_id,
                    teacher_id=teacher.id,
                    date=day,
                    time_slot_id=target_slot.id,
                    availability_level=1,
                ),
            ]
        )
        previous = Assignment(
            project_id=project_id,
            lesson_request_id=request.id,
            session_index=1,
            date=day,
            time_slot_id=previous_slot.id,
            teacher_id=teacher.id,
            is_locked=False,
            is_manual=True,
            created_by="manual",
        )
        session.add(previous)
        session.flush()
        return _Graph(
            project_id=project_id,
            student_id=student.id,
            teacher_id=teacher.id,
            subject_id=subject.id,
            request_id=request.id,
            target_slot_id=target_slot.id,
            previous_slot_id=previous_slot.id,
            previous_assignment_id=previous.id,
            day=day,
        )


def _feasible_result(
    graph: _Graph,
    *,
    teacher_id: int | None = None,
    cancelled: bool = False,
) -> OptimizationResult:
    return OptimizationResult(
        solver_status="FEASIBLE",
        assignments=(
            ScheduledAssignment(
                lesson_request_id=graph.request_id,
                session_index=1,
                student_id=graph.student_id,
                subject_id=graph.subject_id,
                teacher_id=(graph.teacher_id if teacher_id is None else teacher_id),
                day=graph.day,
                time_slot_id=graph.target_slot_id,
                is_locked=False,
            ),
        ),
        unassigned_lessons=(),
        objective_breakdown=ObjectiveBreakdown(
            unassigned_count=0,
            teacher_preference_penalty=0,
            active_teacher_slot_count=1,
            availability_preference_score=3,
            changed_assignment_count=1,
        ),
        elapsed_seconds=0.75,
        warnings=("匿名テスト警告",),
        cancelled=cancelled,
    )


def _assignments(projects: ProjectService, project_id: int) -> list[Assignment]:
    database = projects.require_database()
    with database.session_factory() as session:
        return list(
            session.scalars(
                select(Assignment)
                .where(Assignment.project_id == project_id)
                .order_by(Assignment.lesson_request_id, Assignment.session_index)
            )
        )


def _runs(projects: ProjectService, project_id: int) -> list[OptimizationRun]:
    database = projects.require_database()
    with database.session_factory() as session:
        return list(
            session.scalars(
                select(OptimizationRun)
                .where(OptimizationRun.project_id == project_id)
                .order_by(OptimizationRun.id)
            )
        )


def _log_directory(projects: ProjectService) -> Path:
    return projects.require_project().path.parent / "app-logs" / "optimization-runs"


def test_prepare_and_finalize_updates_same_run_and_replaces_assignments(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    graph = _seed_valid_graph(project_service)
    service = OptimizationRunService(project_service, _app_settings())
    log_directory = tmp_path / "最適化ログ" / "optimization-runs"

    prepared = service.prepare("fast", log_directory=log_directory)

    expected_json = optimization_input_to_json(prepared.input)
    expected_fingerprint = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
    assert prepared.project_id == graph.project_id
    assert prepared.input_fingerprint == expected_fingerprint
    assert prepared.input.settings.time_limit_seconds == pytest.approx(30.1)
    running_rows = _runs(project_service, graph.project_id)
    assert len(running_rows) == 1
    running = running_rows[0]
    assert running.id == prepared.optimization_run_id
    assert running.status == "running"
    assert running.solver_status == "UNKNOWN"
    assert running.time_limit_seconds == 31
    assert running.random_seed == 42
    assert running.input_snapshot_json == expected_json
    assert prepared.log_directory == log_directory.resolve()
    assert prepared.log_path.parent == log_directory.resolve()
    assert prepared.log_path.name.startswith("optimization-run-")
    assert prepared.log_path.suffix == ".log"
    assert running.log_path_optional == str(prepared.log_path)
    assert running.warning_count == 1
    start_log = json.loads(prepared.log_path.read_text(encoding="utf-8"))
    assert start_log["event"] == "started"
    assert start_log["run_id"] == prepared.optimization_run_id
    assert start_log["preset"] == "fast"
    assert start_log["status"] == "running"
    assert start_log["assignment_count"] == 0
    assert start_log["unassigned_count"] == 0
    assert start_log["warning_count"] == 1
    assert start_log["elapsed_seconds"] == pytest.approx(0)

    completed = service.finalize(prepared, _feasible_result(graph))

    assert completed.optimization_run_id == prepared.optimization_run_id
    assert completed.assignment_count == 1
    assert completed.unassigned_count == 0
    assert completed.warning_count == 2
    runs = _runs(project_service, graph.project_id)
    assert len(runs) == 1
    run = runs[0]
    assert run.status == "completed"
    assert run.solver_status == "FEASIBLE"
    assert run.finished_at is not None
    assert run.elapsed_seconds == pytest.approx(0.75)
    assert run.warning_count == 2
    assert json.loads(run.objective_summary_json) == {
        "active_teacher_slot_count": 1,
        "availability_preference_score": 3,
        "changed_assignment_count": 1,
        "optional_balance_score": 0,
        "teacher_preference_penalty": 0,
        "unassigned_count": 0,
    }
    snapshot = json.loads(run.result_snapshot_json)
    assert snapshot["input_fingerprint"] == prepared.input_fingerprint
    assert snapshot["optimization_result"]["schema"] == ("summer_scheduler.optimization_result")
    assert snapshot["previous_assignments"] == [
        {
            "created_by": "manual",
            "date": graph.day.isoformat(),
            "id": graph.previous_assignment_id,
            "is_locked": False,
            "is_manual": True,
            "lesson_request_id": graph.request_id,
            "optimization_run_id": None,
            "session_index": 1,
            "teacher_id": graph.teacher_id,
            "time_slot_id": graph.previous_slot_id,
        }
    ]
    assignments = _assignments(project_service, graph.project_id)
    assert len(assignments) == 1
    assert assignments[0].time_slot_id == graph.target_slot_id
    assert assignments[0].created_by == "solver"
    assert assignments[0].optimization_run_id_optional == run.id
    log_text = prepared.log_path.read_text(encoding="utf-8")
    log_lines = [json.loads(line) for line in log_text.splitlines()]
    assert [line["event"] for line in log_lines] == ["started", "completed"]
    expected_log_fields = {
        "assignment_count",
        "elapsed_seconds",
        "event",
        "preset",
        "run_id",
        "solver_status",
        "status",
        "timestamp",
        "unassigned_count",
        "warning_count",
    }
    assert all(set(line) == expected_log_fields for line in log_lines)
    assert log_lines[-1]["assignment_count"] == 1
    assert log_lines[-1]["unassigned_count"] == 0
    assert log_lines[-1]["warning_count"] == 2
    assert log_lines[-1]["elapsed_seconds"] == pytest.approx(0.75)
    assert "架空 同姓名" not in log_text
    assert "架空 実行講師" not in log_text
    assert str(project_service.require_project().path.resolve()) not in log_text
    assert "input_snapshot" not in log_text

    with pytest.raises(
        OptimizationFinalizationError,
        match="running状態",
    ):
        service.finalize(prepared, _feasible_result(graph))
    assert _runs(project_service, graph.project_id)[0].status == "completed"
    assert len(_assignments(project_service, graph.project_id)) == 1


def test_prepare_solve_finalize_end_to_end(
    project_service: ProjectService,
) -> None:
    graph = _seed_valid_graph(project_service)
    service = OptimizationRunService(project_service, _app_settings())
    assert service.default_preset == "standard"

    prepared = service.prepare(
        "fast",
        log_directory=_log_directory(project_service),
    )
    result = solve_optimization(prepared.input)
    completed = service.finalize(prepared, result)

    assert result.solver_status == "OPTIMAL"
    assert completed.assignment_count == 1
    assignments = _assignments(project_service, graph.project_id)
    assert [(row.time_slot_id, row.teacher_id) for row in assignments] == [
        (graph.target_slot_id, graph.teacher_id)
    ]
    runs = _runs(project_service, graph.project_id)
    assert [(row.status, row.solver_status) for row in runs] == [("completed", "OPTIMAL")]


def test_prepare_rejects_validation_errors_without_creating_run(
    project_service: ProjectService,
) -> None:
    database = project_service.require_database()
    project_id = project_service.require_project().project_id
    with database.session_factory.begin() as session:
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        assert subject is not None
        student = Student(
            external_id="S-INVALID-RUN",
            name="架空 不正入力",
            grade="中2",
            default_max_consecutive_slots=2,
            allow_gap=False,
            active=True,
        )
        session.add(student)
        session.flush()
        session.add(
            LessonRequest(
                project_id=project_id,
                student_id=student.id,
                subject_id=subject.id,
                required_sessions=1,
                regular_teacher_id_optional=None,
                regular_teacher_priority=5,
                one_to_one_required=False,
            )
        )

    service = OptimizationRunService(project_service, _app_settings())
    with pytest.raises(OptimizationPreparationError, match="入力検証エラー"):
        service.prepare(
            "fast",
            log_directory=_log_directory(project_service),
        )
    assert _runs(project_service, project_id) == []


def test_changed_input_marks_run_failed_and_keeps_previous_assignments(
    project_service: ProjectService,
) -> None:
    graph = _seed_valid_graph(project_service)
    service = OptimizationRunService(project_service, _app_settings())
    prepared = service.prepare(
        "fast",
        log_directory=_log_directory(project_service),
    )
    database = project_service.require_database()
    with database.session_factory.begin() as session:
        availability = session.get(
            StudentAvailability,
            (
                graph.project_id,
                graph.student_id,
                graph.day,
                graph.target_slot_id,
            ),
        )
        assert availability is not None
        availability.availability_level = 1

    with pytest.raises(
        OptimizationInputChangedError,
        match="入力が変更",
    ):
        service.finalize(prepared, _feasible_result(graph))

    run = _runs(project_service, graph.project_id)[0]
    assert run.status == "failed"
    assert run.result_snapshot_json == "{}"
    assignments = _assignments(project_service, graph.project_id)
    assert len(assignments) == 1
    assert assignments[0].time_slot_id == graph.previous_slot_id
    assert assignments[0].created_by == "manual"


def test_invalid_result_marks_run_failed_without_assignment_mutation(
    project_service: ProjectService,
) -> None:
    graph = _seed_valid_graph(project_service)
    service = OptimizationRunService(project_service, _app_settings())
    prepared = service.prepare(
        "fast",
        log_directory=_log_directory(project_service),
    )

    with pytest.raises(
        OptimizationFinalizationError,
        match="ハード制約違反",
    ):
        service.finalize(
            prepared,
            _feasible_result(graph, teacher_id=graph.teacher_id + 9999),
        )

    run = _runs(project_service, graph.project_id)[0]
    assert run.status == "failed"
    assignments = _assignments(project_service, graph.project_id)
    assert len(assignments) == 1
    assert assignments[0].time_slot_id == graph.previous_slot_id


@pytest.mark.parametrize(
    ("result", "expected_status"),
    [
        ("cancelled", "cancelled"),
        ("infeasible", "failed"),
    ],
)
def test_cancelled_or_non_feasible_result_never_replaces_assignments(
    project_service: ProjectService,
    result: str,
    expected_status: str,
) -> None:
    graph = _seed_valid_graph(project_service)
    service = OptimizationRunService(project_service, _app_settings())
    prepared = service.prepare(
        "fast",
        log_directory=_log_directory(project_service),
    )
    feasible = _feasible_result(graph)
    rejected = (
        replace(feasible, cancelled=True)
        if result == "cancelled"
        else replace(
            feasible,
            solver_status="INFEASIBLE",
            assignments=(),
        )
    )

    with pytest.raises(OptimizationFinalizationError):
        service.finalize(prepared, rejected)

    run = _runs(project_service, graph.project_id)[0]
    assert run.status == expected_status
    terminal_log = [
        json.loads(line) for line in prepared.log_path.read_text(encoding="utf-8").splitlines()
    ][-1]
    assert terminal_log["event"] == expected_status
    assert terminal_log["status"] == expected_status
    assignments = _assignments(project_service, graph.project_id)
    assert len(assignments) == 1
    assert assignments[0].time_slot_id == graph.previous_slot_id


def test_finalize_exception_rolls_back_and_marks_run_failed(
    project_service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _seed_valid_graph(project_service)
    service = OptimizationRunService(project_service, _app_settings())
    prepared = service.prepare(
        "fast",
        log_directory=_log_directory(project_service),
    )

    def fail_replacement(*_args: object, **_kwargs: object) -> list[Assignment]:
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(
        "summer_scheduler.application.optimization_run_service."
        "Phase4Repository.replace_assignments",
        fail_replacement,
    )
    with pytest.raises(
        OptimizationFinalizationError,
        match="安全に保存",
    ):
        service.finalize(prepared, _feasible_result(graph))

    run = _runs(project_service, graph.project_id)[0]
    assert run.status == "failed"
    assert run.objective_summary_json == "{}"
    assignments = _assignments(project_service, graph.project_id)
    assert len(assignments) == 1
    assert assignments[0].time_slot_id == graph.previous_slot_id


def test_prepare_fails_safely_when_run_log_cannot_be_created(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    graph = _seed_valid_graph(project_service)
    blocked_directory = tmp_path / "ファイルのため作成不能"
    blocked_directory.write_text("架空", encoding="utf-8")
    service = OptimizationRunService(project_service, _app_settings())

    with pytest.raises(
        OptimizationPreparationError,
        match="最適化専用ログを作成できないため開始できません",
    ):
        service.prepare("fast", log_directory=blocked_directory)

    assert _runs(project_service, graph.project_id) == []


def test_each_prepare_creates_a_unique_run_log(
    project_service: ProjectService,
) -> None:
    graph = _seed_valid_graph(project_service)
    service = OptimizationRunService(project_service, _app_settings())
    log_directory = _log_directory(project_service)

    first = service.prepare("fast", log_directory=log_directory)
    second = service.prepare("fast", log_directory=log_directory)

    assert first.log_path != second.log_path
    assert first.log_path.is_file()
    assert second.log_path.is_file()
    assert {row.log_path_optional for row in _runs(project_service, graph.project_id)} == {
        str(first.log_path),
        str(second.log_path),
    }


def test_log_append_failure_after_commit_does_not_rollback_result(
    project_service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = _seed_valid_graph(project_service)
    service = OptimizationRunService(project_service, _app_settings())
    prepared = service.prepare(
        "fast",
        log_directory=_log_directory(project_service),
    )
    sensitive = "架空生徒・秘密のログエラー"

    def fail_append(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(sensitive)

    monkeypatch.setattr(
        "summer_scheduler.application.optimization_run_service.append_optimization_run_log",
        fail_append,
    )
    with caplog.at_level(logging.ERROR):
        finalized = service.finalize(prepared, _feasible_result(graph))

    assert finalized.assignment_count == 1
    run = _runs(project_service, graph.project_id)[0]
    assert run.status == "completed"
    assignments = _assignments(project_service, graph.project_id)
    assert len(assignments) == 1
    assert assignments[0].time_slot_id == graph.target_slot_id
    assert "RuntimeError" in caplog.text
    assert sensitive not in caplog.text
    assert len(prepared.log_path.read_text(encoding="utf-8").splitlines()) == 1
