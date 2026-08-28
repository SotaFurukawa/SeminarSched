"""Phase 5手動編集Serviceのtransaction・検証・Undo/Redo結合テスト。"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import summer_scheduler.application.schedule_edit_service as service_module
from summer_scheduler.application.optimization_input_builder import (
    build_optimization_input as original_build_optimization_input,
)
from summer_scheduler.application.optimization_run_service import (
    OptimizationRunService,
)
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.application.schedule_edit_service import (
    HardConstraintViolationError,
    ScheduleEditConflictError,
    ScheduleEditService,
    ScheduleSaveError,
    SoftWarningConfirmationRequired,
)
from summer_scheduler.infrastructure.db import create_database, upgrade_database
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    AuditLog,
    LessonRequest,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TeacherQualification,
    TimeSlot,
)
from summer_scheduler.infrastructure.repositories import Phase5Repository
from summer_scheduler.optimization.candidates import (
    generate_candidates as original_generate_candidates,
)
from summer_scheduler.optimization.dto import (
    CandidateGenerationResult,
    OptimizationInput,
    OptimizationSettings,
)
from summer_scheduler.optimization.solver import solve_optimization
from summer_scheduler.shared.settings import OptimizationAppSettings


@dataclass(frozen=True, slots=True)
class _Graph:
    project_id: int
    day: date
    request_1_id: int
    request_2_id: int
    teacher_1_id: int
    teacher_2_id: int
    y_slot_id: int
    z_slot_id: int


@pytest.fixture
def project_service(tmp_path: Path) -> Iterator[ProjectService]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    service = ProjectService(registry, tmp_path / "バックアップ")
    service.create_project(
        tmp_path / "日本語フォルダー" / "Phase5編集.jukuschedule",
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
        fast_time_limit_seconds=30.0,
        standard_time_limit_seconds=120.0,
        high_quality_time_limit_seconds=600.0,
        random_seed=20260729,
        num_search_workers=1,
        regular_teacher_priority_weights=(1, 2, 3, 4),
        preferred_teacher_rank_weights=(30, 20, 10),
        student_preferred_time_weight=3,
        teacher_preferred_time_weight=2,
        preserve_existing_assignment_weight=5,
        optional_balance_weight=0,
    )


def _seed_graph(projects: ProjectService) -> _Graph:
    database = projects.require_database()
    project_id = projects.require_project().project_id
    day = date(2026, 8, 1)
    with database.session_factory.begin() as session:
        subject = session.scalar(select(Subject).where(Subject.code == "JH_MATH"))
        y_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "Y"))
        z_slot = session.scalar(select(TimeSlot).where(TimeSlot.code == "Z"))
        assert subject is not None
        assert y_slot is not None
        assert z_slot is not None
        students = [
            Student(
                external_id=f"S-P5-{index:03d}",
                name=f"架空 生徒{index}",
                grade=f"中学{index + 1}年",
                default_max_consecutive_slots=2,
                allow_gap=False,
                active=True,
            )
            for index in (1, 2)
        ]
        teachers = [
            Teacher(
                external_id=f"T-P5-{index:03d}",
                name=f"架空 講師{index}",
                allow_gap=False,
                active=True,
            )
            for index in (1, 2)
        ]
        session.add_all([*students, *teachers])
        session.flush()
        session.add_all(
            TeacherQualification(
                teacher_id=teacher.id,
                subject_id=subject.id,
                can_teach=True,
            )
            for teacher in teachers
        )
        requests = [
            LessonRequest(
                project_id=project_id,
                student_id=student.id,
                subject_id=subject.id,
                required_sessions=1,
                regular_teacher_id_optional=teachers[0].id,
                regular_teacher_priority=3,
                one_to_one_required=False,
            )
            for student in students
        ]
        session.add_all(requests)
        session.flush()
        for student, preferred_slot in zip(students, (y_slot, z_slot), strict=True):
            other_slot = z_slot if preferred_slot is y_slot else y_slot
            session.add_all(
                [
                    StudentAvailability(
                        project_id=project_id,
                        student_id=student.id,
                        date=day,
                        time_slot_id=preferred_slot.id,
                        availability_level=2,
                    ),
                    StudentAvailability(
                        project_id=project_id,
                        student_id=student.id,
                        date=day,
                        time_slot_id=other_slot.id,
                        availability_level=1,
                    ),
                ]
            )
        for teacher in teachers:
            session.add_all(
                TeacherAvailability(
                    project_id=project_id,
                    teacher_id=teacher.id,
                    date=day,
                    time_slot_id=slot.id,
                    availability_level=2 if teacher is teachers[0] else 1,
                )
                for slot in (y_slot, z_slot)
            )
        session.add_all(
            [
                Assignment(
                    project_id=project_id,
                    lesson_request_id=requests[0].id,
                    session_index=1,
                    date=day,
                    time_slot_id=y_slot.id,
                    teacher_id=teachers[0].id,
                    is_locked=False,
                    is_manual=False,
                    created_by="solver",
                ),
                Assignment(
                    project_id=project_id,
                    lesson_request_id=requests[1].id,
                    session_index=1,
                    date=day,
                    time_slot_id=z_slot.id,
                    teacher_id=teachers[0].id,
                    is_locked=False,
                    is_manual=False,
                    created_by="solver",
                ),
            ]
        )
        return _Graph(
            project_id=project_id,
            day=day,
            request_1_id=requests[0].id,
            request_2_id=requests[1].id,
            teacher_1_id=teachers[0].id,
            teacher_2_id=teachers[1].id,
            y_slot_id=y_slot.id,
            z_slot_id=z_slot.id,
        )


def _assignment(
    projects: ProjectService,
    graph: _Graph,
    request_id: int,
) -> Assignment | None:
    with projects.require_database().session_factory() as session:
        return session.scalar(
            select(Assignment).where(
                Assignment.project_id == graph.project_id,
                Assignment.lesson_request_id == request_id,
                Assignment.session_index == 1,
            )
        )


def _require_assignment(
    projects: ProjectService,
    graph: _Graph,
    request_id: int,
) -> Assignment:
    row = _assignment(projects, graph, request_id)
    assert row is not None
    return row


def test_preview_keeps_all_soft_deltas_and_apply_requires_confirmation(
    project_service: ProjectService,
) -> None:
    graph = _seed_graph(project_service)
    service = ScheduleEditService(project_service, _app_settings())
    board = service.load_board()

    assert len(board.cards) == 2
    assert board.cards[0].student_name.startswith("架空 生徒")
    assert board.cards[0].regular_teacher_name == "架空 講師1"
    assert board.cards[0].availability_text == "生徒:希望 / 講師:希望"
    preview = service.preview_move(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.z_slot_id,
        teacher_id=graph.teacher_2_id,
    )

    assert preview.allowed is True
    assert preview.decision == "yellow"
    assert len(preview.soft_deltas) == 7
    assert {item.direction for item in preview.soft_deltas} == {
        "lower_is_better",
        "higher_is_better",
    }
    assert any(
        item.before_value != item.after_value and item.worsened for item in preview.soft_deltas
    )
    with pytest.raises(SoftWarningConfirmationRequired):
        service.apply_move(
            lesson_request_id=graph.request_1_id,
            session_index=1,
            day=graph.day,
            time_slot_id=graph.z_slot_id,
            teacher_id=graph.teacher_2_id,
            reason="講師調整",
        )
    assert _require_assignment(project_service, graph, graph.request_1_id).time_slot_id == (
        graph.y_slot_id
    )

    result = service.apply_move(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.z_slot_id,
        teacher_id=graph.teacher_2_id,
        reason="  講師調整  ",
        confirm_soft_warnings=True,
    )

    assert result.action == "move"
    saved = _assignment(project_service, graph, graph.request_1_id)
    assert saved is not None
    assert (saved.time_slot_id, saved.teacher_id, saved.is_manual) == (
        graph.z_slot_id,
        graph.teacher_2_id,
        True,
    )
    with project_service.require_database().session_factory() as session:
        audit = session.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
        assert audit is not None
        assert audit.reason == "講師調整"
        assert audit.source == "manual"
        assert audit.operation_id_optional
    reloaded_service = ScheduleEditService(project_service, _app_settings())
    reloaded_board = reloaded_service.load_board()
    assert (
        next(
            card for card in reloaded_board.cards if card.lesson_request_id == graph.request_1_id
        ).teacher_id
        == graph.teacher_2_id
    )
    assert reloaded_board.audit_logs[0].reason == "講師調整"
    diff = {(item.lesson_request_id, item.session_index): item for item in reloaded_board.diff}
    changed = diff[(graph.request_1_id, 1)]
    assert changed.change_codes == ("date", "teacher")
    assert changed.change_type == "date+teacher"


def test_hard_violation_is_rejected_even_when_soft_confirmation_is_true(
    project_service: ProjectService,
) -> None:
    graph = _seed_graph(project_service)
    with project_service.require_database().session_factory.begin() as session:
        request = session.get(LessonRequest, graph.request_1_id)
        assert request is not None
        request.regular_teacher_priority = 5
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()

    preview = service.preview_move(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.z_slot_id,
        teacher_id=graph.teacher_2_id,
    )
    assert preview.allowed is False
    assert preview.decision == "red"
    assert preview.hard_issues
    with pytest.raises(HardConstraintViolationError):
        service.apply_move(
            lesson_request_id=graph.request_1_id,
            session_index=1,
            day=graph.day,
            time_slot_id=graph.z_slot_id,
            teacher_id=graph.teacher_2_id,
            reason="強制しない",
            confirm_soft_warnings=True,
        )
    assert _require_assignment(project_service, graph, graph.request_1_id).teacher_id == (
        graph.teacher_1_id
    )


def test_pairing_diff_includes_other_session_and_undo_redo_are_immediate(
    project_service: ProjectService,
) -> None:
    graph = _seed_graph(project_service)
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()

    service.apply_move(
        lesson_request_id=graph.request_2_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.y_slot_id,
        teacher_id=graph.teacher_1_id,
        reason="1対2へ集約",
        confirm_soft_warnings=True,
    )
    board = service.load_board()
    diff = {item.lesson_request_id: item for item in board.diff}
    assert diff[graph.request_1_id].change_codes == ("pairing",)
    assert diff[graph.request_1_id].before_pairing_size == 1
    assert diff[graph.request_1_id].after_pairing_size == 2
    assert diff[graph.request_2_id].change_codes == ("date", "pairing")

    undo = service.undo()
    assert undo.action == "undo"
    assert _require_assignment(project_service, graph, graph.request_2_id).time_slot_id == (
        graph.z_slot_id
    )
    redo = service.redo()
    assert redo.action == "redo"
    assert _require_assignment(project_service, graph, graph.request_2_id).time_slot_id == (
        graph.y_slot_id
    )
    history = service.list_history()
    assert [item.source for item in history[:3]] == ["redo", "undo", "manual"]


def test_unassign_assign_lock_note_and_detailed_edit_are_undoable(
    project_service: ProjectService,
) -> None:
    graph = _seed_graph(project_service)
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()

    service.unassign(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        reason="一旦未配置",
        confirm_soft_warnings=True,
    )
    assert _assignment(project_service, graph, graph.request_1_id) is None
    assert any(
        row.lesson_request_id == graph.request_1_id for row in service.load_board().unassigned
    )
    service.undo()
    assert _assignment(project_service, graph, graph.request_1_id) is not None
    service.redo()
    assert _assignment(project_service, graph, graph.request_1_id) is None
    service.apply_move(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.y_slot_id,
        teacher_id=graph.teacher_1_id,
        reason="未配置から復帰",
        confirm_soft_warnings=True,
    )
    service.undo()
    assert _assignment(project_service, graph, graph.request_1_id) is None
    service.redo()
    assert _assignment(project_service, graph, graph.request_1_id) is not None

    service.edit_assignment(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.y_slot_id,
        teacher_id=graph.teacher_1_id,
        is_locked=True,
        note="  保護者確認済み  ",
        reason="固定と備考を同時反映",
    )
    saved = _assignment(project_service, graph, graph.request_1_id)
    assert saved is not None
    assert saved.is_locked is True
    assert saved.note == "保護者確認済み"
    with pytest.raises(HardConstraintViolationError):
        service.apply_move(
            lesson_request_id=graph.request_1_id,
            session_index=1,
            day=graph.day,
            time_slot_id=graph.z_slot_id,
            teacher_id=graph.teacher_1_id,
            reason="ロック移動は禁止",
            confirm_soft_warnings=True,
        )
    service.undo()
    restored = _assignment(project_service, graph, graph.request_1_id)
    assert restored is not None
    assert restored.is_locked is False
    assert restored.note is None

    service.set_lock(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        is_locked=True,
        reason="単独ロック",
    )
    service.undo()
    assert _require_assignment(project_service, graph, graph.request_1_id).is_locked is False
    service.redo()
    assert _require_assignment(project_service, graph, graph.request_1_id).is_locked is True
    service.set_lock(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        is_locked=False,
        reason="単独ロック解除",
    )
    service.undo()
    assert _require_assignment(project_service, graph, graph.request_1_id).is_locked is True
    service.redo()
    assert _require_assignment(project_service, graph, graph.request_1_id).is_locked is False


def test_preconfirmed_assignment_is_created_locked_with_audit_and_hard_validation(
    project_service: ProjectService,
) -> None:
    graph = _seed_graph(project_service)
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()
    service.unassign(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        reason="事前確定へ移す準備",
        confirm_soft_warnings=True,
    )

    result = service.create_preconfirmed_assignment(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.z_slot_id,
        teacher_id=graph.teacher_2_id,
        note="保護者と調整済み",
    )

    saved = _require_assignment(project_service, graph, graph.request_1_id)
    assert result.action == "assign_unassigned"
    assert saved.is_locked is True
    assert saved.is_manual is True
    assert saved.created_by == "manual"
    assert saved.note == "保護者と調整済み"
    with project_service.require_database().session_factory() as session:
        audit = session.scalar(select(AuditLog).order_by(AuditLog.id.desc()))
        assert audit is not None
        assert audit.reason == "事前確定枠として登録"
        assert '"is_locked":true' in str(audit.after_json).lower()

    with pytest.raises(HardConstraintViolationError):
        service.create_preconfirmed_assignment(
            lesson_request_id=graph.request_1_id,
            session_index=1,
            day=graph.day,
            time_slot_id=graph.y_slot_id,
            teacher_id=graph.teacher_1_id,
        )


def test_unlock_invalidates_locked_candidate_cache_and_allows_preview(
    project_service: ProjectService,
) -> None:
    graph = _seed_graph(project_service)
    with project_service.require_database().session_factory.begin() as session:
        row = session.scalar(
            select(Assignment).where(Assignment.lesson_request_id == graph.request_1_id)
        )
        assert row is not None
        row.is_locked = True
        row.is_manual = True
        row.created_by = "manual"
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()
    locked_preview = service.preview_move(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.z_slot_id,
        teacher_id=graph.teacher_2_id,
    )
    assert locked_preview.allowed is False

    service.set_lock(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        is_locked=False,
        reason="固定解除",
    )
    unlocked_preview = service.preview_move(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        day=graph.day,
        time_slot_id=graph.z_slot_id,
        teacher_id=graph.teacher_2_id,
    )
    assert unlocked_preview.allowed is True
    assert "locked_assignment_not_preserved" not in unlocked_preview.hard_issue_codes


def test_external_change_rejects_undo_and_save_failure_rolls_back(
    project_service: ProjectService,
) -> None:
    graph = _seed_graph(project_service)
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()
    service.set_lock(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        is_locked=True,
        reason="固定",
    )
    with project_service.require_database().session_factory.begin() as session:
        row = session.scalar(
            select(Assignment).where(Assignment.lesson_request_id == graph.request_2_id)
        )
        assert row is not None
        row.note = "外部変更"
    with pytest.raises(ScheduleEditConflictError):
        service.undo()

    class _FailingAuditRepository(Phase5Repository):
        def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
            raise OSError("架空の保存障害")

    failing = ScheduleEditService(
        project_service,
        _app_settings(),
        repository_factory=_FailingAuditRepository,
    )
    failing.load_board()
    before = _assignment(project_service, graph, graph.request_2_id)
    assert before is not None
    with pytest.raises(ScheduleSaveError):
        failing.update_note(
            lesson_request_id=graph.request_2_id,
            session_index=1,
            note="保存されない備考",
            reason="rollback確認",
        )
    after = _assignment(project_service, graph, graph.request_2_id)
    assert after is not None
    assert after.note == "外部変更"
    assert failing.load_board().can_undo is False


def test_preview_reuses_cached_input_and_candidates(
    project_service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _seed_graph(project_service)
    build_calls = 0
    candidate_calls = 0

    def counted_build(
        *,
        session: Session,
        project_id: int,
        settings: OptimizationSettings,
    ) -> OptimizationInput:
        nonlocal build_calls
        build_calls += 1
        return original_build_optimization_input(
            session=session,
            project_id=project_id,
            settings=settings,
        )

    def counted_candidates(
        data: OptimizationInput,
        *,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> CandidateGenerationResult:
        nonlocal candidate_calls
        candidate_calls += 1
        return original_generate_candidates(data, is_cancelled=is_cancelled)

    monkeypatch.setattr(service_module, "build_optimization_input", counted_build)
    monkeypatch.setattr(service_module, "generate_candidates", counted_candidates)
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()
    assert (build_calls, candidate_calls) == (1, 1)

    for _ in range(3):
        service.preview_move(
            lesson_request_id=graph.request_1_id,
            session_index=1,
            day=graph.day,
            time_slot_id=graph.z_slot_id,
            teacher_id=graph.teacher_2_id,
        )
    assert (build_calls, candidate_calls) == (1, 1)


def test_manual_backup_creates_explicit_saved_copy_without_switching_project(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    graph = _seed_graph(project_service)
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()
    original_path = project_service.require_project().path

    saved = service.create_manual_backup(tmp_path / "手動保存" / "保存点.jukuschedule")
    automatic_1 = service.create_manual_backup()
    automatic_2 = service.create_manual_backup()

    assert saved.path.is_file()
    assert saved.path != original_path
    assert automatic_1.path.is_file()
    assert automatic_2.path.is_file()
    assert automatic_1.path != automatic_2.path
    assert project_service.require_project().path == original_path
    assert saved.lock_count == 0
    assert saved.unassigned_count == 0
    assert saved.fingerprint == service.load_board().fingerprint
    assert _require_assignment(project_service, graph, graph.request_1_id).note is None


def test_checkpoint_backup_preserves_baseline_for_external_reoptimization_diff(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    graph = _seed_graph(project_service)
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()
    checkpoint = service.create_checkpoint_backup(tmp_path / "退避" / "再最適化前.jukuschedule")
    assert checkpoint.path.is_file()
    assert checkpoint.unassigned_count == 0

    with project_service.require_database().session_factory.begin() as session:
        row = session.scalar(
            select(Assignment).where(Assignment.lesson_request_id == graph.request_1_id)
        )
        assert row is not None
        row.date = graph.day
        row.time_slot_id = graph.z_slot_id
        row.teacher_id = graph.teacher_2_id
        row.is_manual = False
        row.created_by = "solver"

    board = service.load_board()
    changed = next(item for item in board.diff if item.lesson_request_id == graph.request_1_id)
    assert changed.change_codes == ("date", "teacher")
    assert board.can_undo is False


def test_locked_assignment_survives_real_reoptimization_transaction(
    project_service: ProjectService,
    tmp_path: Path,
) -> None:
    graph = _seed_graph(project_service)
    edit_service = ScheduleEditService(project_service, _app_settings())
    edit_service.load_board()
    edit_service.set_lock(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        is_locked=True,
        reason="再最適化でも保持",
    )
    checkpoint = edit_service.create_checkpoint_backup(
        tmp_path / "再最適化前" / "固定保持.jukuschedule"
    )
    assert checkpoint.lock_count == 1

    run_service = OptimizationRunService(project_service, _app_settings())
    prepared = run_service.prepare(
        "fast",
        log_directory=tmp_path / "最適化ログ",
    )
    result = solve_optimization(prepared.input)
    assert result.solver_status in {"OPTIMAL", "FEASIBLE"}
    run_service.finalize(prepared, result)

    locked = _require_assignment(project_service, graph, graph.request_1_id)
    assert (
        locked.date,
        locked.time_slot_id,
        locked.teacher_id,
        locked.is_locked,
    ) == (
        graph.day,
        graph.y_slot_id,
        graph.teacher_1_id,
        True,
    )
    board = edit_service.load_board()
    assert board.lock_count == 1
    assert any(item.change_codes for item in board.diff)
    reopened_board = ScheduleEditService(project_service, _app_settings()).load_board()
    assert len(reopened_board.diff) == 2
    assert {code for item in reopened_board.diff for code in item.change_codes} <= {
        "new",
        "date",
        "teacher",
        "unassigned",
        "pairing",
        "unchanged",
    }


def test_abrupt_process_exit_recovers_last_commit_and_rolls_back_incomplete_edit(
    project_service: ProjectService,
) -> None:
    """即時保存後の状態だけを復旧し、未commitのAssignment/Auditを残さない。"""
    graph = _seed_graph(project_service)
    service = ScheduleEditService(project_service, _app_settings())
    service.load_board()
    service.update_note(
        lesson_request_id=graph.request_1_id,
        session_index=1,
        note="強制終了前に保存済み",
        reason="異常終了復旧の基準点",
    )

    project_path = project_service.require_project().path
    crash_script = """
import os
import sqlite3
import sys

database_path, project_id, request_id = sys.argv[1:4]
connection = sqlite3.connect(database_path)
connection.execute("PRAGMA foreign_keys=ON")
connection.execute("BEGIN IMMEDIATE")
connection.execute(
    "UPDATE assignments SET note = ? "
    "WHERE project_id = ? AND lesson_request_id = ? AND session_index = 1",
    ("未commitの変更", int(project_id), int(request_id)),
)
connection.execute(
    "INSERT INTO audit_logs "
    "(project_id, action, entity_type, entity_id, reason, source) "
    "VALUES (?, 'note', 'AssignmentSession', ?, ?, 'manual')",
    (int(project_id), f"{request_id}:1", "未commitの監査"),
)
os._exit(23)
"""
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            crash_script,
            str(project_path),
            str(graph.project_id),
            str(graph.request_1_id),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert crashed.returncode == 23

    recovered = ScheduleEditService(project_service, _app_settings()).load_board()
    recovered_card = next(
        card for card in recovered.cards if card.lesson_request_id == graph.request_1_id
    )
    assert recovered_card.note == "強制終了前に保存済み"
    reasons = [row.reason for row in recovered.audit_logs]
    assert "異常終了復旧の基準点" in reasons
    assert "未commitの監査" not in reasons

    with project_service.require_database().session_factory() as session:
        assert (
            session.execute(
                select(AuditLog.reason).where(AuditLog.reason == "未commitの監査")
            ).scalar_one_or_none()
            is None
        )
