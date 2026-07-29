"""Phase 5の手動編集・自動保存・Undo/Redoを束ねるApplication Service。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from summer_scheduler.application.optimization_input_builder import (
    build_optimization_input,
)
from summer_scheduler.application.phase5_dto import (
    AuditLogDto,
    CheckpointBackupDto,
    EditAction,
    EditPreviewDto,
    EditResultDto,
    ReoptimizationSummaryDto,
    ScheduleBoardDto,
    ScheduleDiffDto,
    SoftMetricDeltaDto,
)
from summer_scheduler.application.project_service import ProjectService, ProjectSummary
from summer_scheduler.application.schedule_board_query import (
    audit_log_to_dto,
    build_schedule_board,
)
from summer_scheduler.infrastructure.db.models import AuditLog, OptimizationRun
from summer_scheduler.infrastructure.repositories import (
    AssignmentSnapshot,
    Phase5Repository,
)
from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.dto import (
    CandidateGenerationResult,
    OptimizationInput,
    OptimizationSettings,
    ScheduledAssignment,
    UnassignedLesson,
)
from summer_scheduler.optimization.manual_edit import (
    EditOperation,
    EditOperationKind,
    EditPreview,
    EditSchedule,
    EditTarget,
    preview_edit,
)
from summer_scheduler.optimization.schedule_diff import diff_schedules
from summer_scheduler.optimization.serialization import (
    optimization_input_to_json,
    optimization_result_from_json,
)
from summer_scheduler.shared.settings import OptimizationAppSettings

RepositoryFactory = Callable[[Session], Phase5Repository]
UndoDirection = Literal["undo", "redo"]


class ScheduleEditError(RuntimeError):
    """時間割編集を安全に完了できない場合の基底例外。"""


class ScheduleEditValidationError(ScheduleEditError):
    """編集指定自体が成立しない場合。"""


class HardConstraintViolationError(ScheduleEditValidationError):
    """ハード制約違反を強制適用せず拒否した場合。"""

    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("ハード制約違反のため変更できません: " + " / ".join(issues))


class SoftWarningConfirmationRequired(ScheduleEditValidationError):
    """ソフト条件悪化を利用者が未確認の場合。"""

    def __init__(self, warnings: tuple[str, ...]) -> None:
        self.warnings = warnings
        super().__init__("ソフト条件の悪化を確認してください: " + " / ".join(warnings))


class ScheduleEditConflictError(ScheduleEditError):
    """読み込み後に外部変更を検出した場合。"""


class ScheduleSaveError(ScheduleEditError):
    """transactionがrollbackされ、保存できなかった場合。"""


class UndoRedoUnavailableError(ScheduleEditError):
    """Undo/Redo対象がない、または安全に適用できない場合。"""


@dataclass(frozen=True, slots=True)
class _PreparedContext:
    data: OptimizationInput
    generation: CandidateGenerationResult
    schedule: EditSchedule
    snapshots: tuple[AssignmentSnapshot, ...]
    base_fingerprint: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _EditCommand:
    operation_id: str
    action: str
    lesson_request_id: int
    session_index: int
    before: AssignmentSnapshot | None
    after: AssignmentSnapshot | None
    before_fingerprint: str
    after_fingerprint: str
    reason: str
    diff: tuple[ScheduleDiffDto, ...]


class ScheduleEditService:
    """手動編集を全検証し、AssignmentとAuditLogを1 transactionで自動保存する。"""

    def __init__(
        self,
        projects: ProjectService,
        app_settings: OptimizationAppSettings,
        *,
        repository_factory: RepositoryFactory = Phase5Repository,
    ) -> None:
        self._projects = projects
        self._settings = _optimization_settings(app_settings)
        self._repository_factory = repository_factory
        self._candidate_cache_key: str | None = None
        self._candidate_cache: CandidateGenerationResult | None = None
        self._context_cache: _PreparedContext | None = None
        self._cache_scope: tuple[int, str] | None = None
        self._known_fingerprint: str | None = None
        self._undo_stack: list[_EditCommand] = []
        self._redo_stack: list[_EditCommand] = []
        self._last_diff: tuple[ScheduleDiffDto, ...] = ()
        self._checkpoint_baseline: EditSchedule | None = None

    def load_board(self) -> ScheduleBoardDto:
        """最新のボードを一括取得する。外部変更時は古いUndo履歴を破棄する。"""
        project = self._require_project()
        database = self._projects.require_database()
        with database.session_factory() as session:
            context = self._build_context(session, project.project_id)
            display_diff = self._last_diff
            checkpoint_diff_applied = False
            if self._checkpoint_baseline is not None:
                checkpoint_diff = _schedule_diff(
                    self._checkpoint_baseline,
                    context.schedule,
                )
                if any(item.change_type != "unchanged" for item in checkpoint_diff):
                    display_diff = checkpoint_diff
                    checkpoint_diff_applied = True
                    self._checkpoint_baseline = None
            if (
                self._known_fingerprint is not None
                and self._known_fingerprint != context.fingerprint
            ):
                self._clear_command_history(clear_diff=False)
                if not checkpoint_diff_applied:
                    display_diff = _persisted_diff(session, context)
            elif not display_diff:
                display_diff = _persisted_diff(session, context)
            self._last_diff = display_diff
            self._known_fingerprint = context.fingerprint
            self._context_cache = context
            repository = self._repository_factory(session)
            audit_logs = repository.list_audit_logs(project_id=project.project_id)
            return build_schedule_board(
                session=session,
                project_id=project.project_id,
                generation=context.generation,
                fingerprint=context.fingerprint,
                audit_logs=audit_logs,
                diff=display_diff,
                can_undo=bool(self._undo_stack),
                can_redo=bool(self._redo_stack),
            )

    def reload(self) -> ScheduleBoardDto:
        """利用者の明示操作としてDBを再読込みし、process内Undo履歴を破棄する。"""
        self._known_fingerprint = None
        self._context_cache = None
        self._candidate_cache_key = None
        self._candidate_cache = None
        self._clear_command_history()
        return self.load_board()

    def preview_move(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        day: date,
        time_slot_id: int,
        teacher_id: int,
    ) -> EditPreviewDto:
        """配置済み移動と未配置からの配置に同じ検証境界を使う。"""
        target = EditTarget(day=day, time_slot_id=time_slot_id, teacher_id=teacher_id)
        project = self._require_project()
        context = self._cached_context(project)
        self._require_known(context.fingerprint)
        kind = (
            EditOperationKind.MOVE
            if _find_snapshot(context.snapshots, lesson_request_id, session_index)
            else EditOperationKind.ASSIGN_UNASSIGNED
        )
        preview = preview_edit(
            context.data,
            context.generation,
            context.schedule,
            EditOperation(
                kind=kind,
                lesson_request_id=lesson_request_id,
                session_index=session_index,
                target=target,
            ),
        )
        return _preview_dto(preview, context)

    def preview_unassign(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
    ) -> EditPreviewDto:
        project = self._require_project()
        context = self._cached_context(project)
        self._require_known(context.fingerprint)
        preview = preview_edit(
            context.data,
            context.generation,
            context.schedule,
            EditOperation(
                kind=EditOperationKind.UNASSIGN,
                lesson_request_id=lesson_request_id,
                session_index=session_index,
            ),
        )
        return _preview_dto(preview, context)

    def apply_move(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        day: date,
        time_slot_id: int,
        teacher_id: int,
        reason: str,
        confirm_soft_warnings: bool = False,
    ) -> EditResultDto:
        """previewと同一の検証をtransaction内で再実行して配置を保存する。"""
        return self._apply_edit(
            lesson_request_id=lesson_request_id,
            session_index=session_index,
            day=day,
            time_slot_id=time_slot_id,
            teacher_id=teacher_id,
            is_locked=None,
            note=None,
            change_note=False,
            reason=reason,
            confirm_soft_warnings=confirm_soft_warnings,
        )

    def edit_assignment(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        day: date,
        time_slot_id: int,
        teacher_id: int,
        is_locked: bool,
        note: str,
        reason: str,
        confirm_soft_warnings: bool = False,
    ) -> EditResultDto:
        """詳細編集の日付・コマ・講師・lock・備考を1 transactionで反映する。"""
        return self._apply_edit(
            lesson_request_id=lesson_request_id,
            session_index=session_index,
            day=day,
            time_slot_id=time_slot_id,
            teacher_id=teacher_id,
            is_locked=is_locked,
            note=note,
            change_note=True,
            reason=reason,
            confirm_soft_warnings=confirm_soft_warnings,
            require_assigned=True,
        )

    def unassign(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        reason: str,
        confirm_soft_warnings: bool = False,
    ) -> EditResultDto:
        """配置済み授業を未配置へ戻す。ロック済みはcore検証で拒否する。"""
        normalized_reason = _required_reason(reason)
        project = self._require_project()
        database = self._projects.require_database()
        try:
            with database.session_factory.begin() as session:
                repository = self._repository_factory(session)
                context = self._build_context(session, project.project_id)
                self._require_known(context.fingerprint)
                preview = preview_edit(
                    context.data,
                    context.generation,
                    context.schedule,
                    EditOperation(
                        kind=EditOperationKind.UNASSIGN,
                        lesson_request_id=lesson_request_id,
                        session_index=session_index,
                    ),
                )
                _require_preview_allowed(preview, confirm_soft_warnings)
                before = _find_snapshot(
                    context.snapshots,
                    lesson_request_id,
                    session_index,
                )
                if before is None:
                    raise ScheduleEditValidationError("指定した授業は配置されていません")
                saved = self._persist_change(
                    repository=repository,
                    before_context=context,
                    before=before,
                    after=None,
                    action="unassign",
                    reason=normalized_reason,
                )
        except ScheduleEditError:
            raise
        except Exception as exc:
            raise ScheduleSaveError("未配置化を保存できず、変更をrollbackしました") from exc
        return self._record_command(saved)

    def set_lock(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        is_locked: bool,
        reason: str,
    ) -> EditResultDto:
        """授業単位lock/unlockを即時保存する。"""
        return self._apply_metadata_change(
            lesson_request_id=lesson_request_id,
            session_index=session_index,
            is_locked=is_locked,
            note=None,
            change_note=False,
            reason=reason,
        )

    def update_note(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        note: str,
        reason: str,
    ) -> EditResultDto:
        """Assignment備考だけを即時保存する。"""
        return self._apply_metadata_change(
            lesson_request_id=lesson_request_id,
            session_index=session_index,
            is_locked=None,
            note=note,
            change_note=True,
            reason=reason,
        )

    def undo(self) -> EditResultDto:
        if not self._undo_stack:
            raise UndoRedoUnavailableError("元に戻せる操作がありません")
        command = self._undo_stack[-1]
        result = self._replay(command, direction="undo")
        self._undo_stack.pop()
        self._redo_stack.append(command)
        return result

    def redo(self) -> EditResultDto:
        if not self._redo_stack:
            raise UndoRedoUnavailableError("やり直せる操作がありません")
        command = self._redo_stack[-1]
        result = self._replay(command, direction="redo")
        self._redo_stack.pop()
        self._undo_stack.append(command)
        return result

    def list_history(self, *, limit: int = 100) -> tuple[AuditLogDto, ...]:
        project = self._require_project()
        database = self._projects.require_database()
        with database.session_factory() as session:
            rows = self._repository_factory(session).list_audit_logs(
                project_id=project.project_id,
                limit=limit,
            )
            return tuple(audit_log_to_dto(row) for row in rows)

    def reoptimization_summary(self) -> ReoptimizationSummaryDto:
        """ロック以外再最適化の確認画面に必要な件数だけを返す。"""
        project = self._require_project()
        context = self._cached_context(project)
        self._require_known(context.fingerprint)
        return ReoptimizationSummaryDto(
            project_id=project.project_id,
            assignment_count=len(context.snapshots),
            lock_count=sum(item.is_locked for item in context.snapshots),
            manual_count=sum(item.is_manual for item in context.snapshots),
            unassigned_count=len(context.schedule.unassigned_lessons),
            fingerprint=context.fingerprint,
        )

    def create_checkpoint_backup(
        self,
        path: Path | None = None,
    ) -> CheckpointBackupDto:
        """再最適化前の明示checkpointをProjectServiceのSQLite backupで作る。"""
        summary = self.reoptimization_summary()
        project = self._require_project()
        baseline = self._cached_context(project).schedule
        backup_path = self._projects.backup(path)
        self._checkpoint_baseline = baseline
        return CheckpointBackupDto(
            path=backup_path,
            lock_count=summary.lock_count,
            unassigned_count=summary.unassigned_count,
            fingerprint=summary.fingerprint,
        )

    def create_manual_backup(
        self,
        path: Path | None = None,
    ) -> CheckpointBackupDto:
        """即時保存済みDBの手動保存点をSQLite backup APIで作る。

        再最適化の差分baselineにはせず、通常の明示保存と再最適化前checkpointを
        別の操作として扱う。
        """
        summary = self.reoptimization_summary()
        backup_path = self._projects.backup(path)
        return CheckpointBackupDto(
            path=backup_path,
            lock_count=summary.lock_count,
            unassigned_count=summary.unassigned_count,
            fingerprint=summary.fingerprint,
        )

    def _apply_edit(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        day: date,
        time_slot_id: int,
        teacher_id: int,
        is_locked: bool | None,
        note: str | None,
        change_note: bool,
        reason: str,
        confirm_soft_warnings: bool,
        require_assigned: bool = False,
    ) -> EditResultDto:
        normalized_reason = _required_reason(reason)
        project = self._require_project()
        database = self._projects.require_database()
        try:
            with database.session_factory.begin() as session:
                repository = self._repository_factory(session)
                context = self._build_context(session, project.project_id)
                self._require_known(context.fingerprint)
                before = _find_snapshot(
                    context.snapshots,
                    lesson_request_id,
                    session_index,
                )
                if require_assigned and before is None:
                    raise ScheduleEditValidationError("指定した授業は配置されていません")
                kind = (
                    EditOperationKind.MOVE
                    if before is not None
                    else EditOperationKind.ASSIGN_UNASSIGNED
                )
                target = EditTarget(
                    day=day,
                    time_slot_id=time_slot_id,
                    teacher_id=teacher_id,
                )
                placement_changed = before is None or (
                    before.day != day
                    or before.time_slot_id != time_slot_id
                    or before.teacher_id != teacher_id
                )
                if placement_changed:
                    preview = preview_edit(
                        context.data,
                        context.generation,
                        context.schedule,
                        EditOperation(
                            kind=kind,
                            lesson_request_id=lesson_request_id,
                            session_index=session_index,
                            target=target,
                        ),
                    )
                    _require_preview_allowed(preview, confirm_soft_warnings)
                if before is None:
                    after = AssignmentSnapshot(
                        project_id=project.project_id,
                        lesson_request_id=lesson_request_id,
                        session_index=session_index,
                        day=day,
                        time_slot_id=time_slot_id,
                        teacher_id=teacher_id,
                        optimization_run_id_optional=None,
                        is_locked=is_locked or False,
                        is_manual=True,
                        created_by="manual",
                        note=_normalized_note(note) if change_note else None,
                    )
                else:
                    after = AssignmentSnapshot(
                        project_id=before.project_id,
                        lesson_request_id=before.lesson_request_id,
                        session_index=before.session_index,
                        day=day,
                        time_slot_id=time_slot_id,
                        teacher_id=teacher_id,
                        optimization_run_id_optional=before.optimization_run_id_optional,
                        is_locked=is_locked if is_locked is not None else before.is_locked,
                        is_manual=True,
                        created_by="manual",
                        note=_normalized_note(note) if change_note else before.note,
                    )
                action = _action_for(before, after, placement_changed, change_note)
                saved = self._persist_change(
                    repository=repository,
                    before_context=context,
                    before=before,
                    after=after,
                    action=action,
                    reason=normalized_reason,
                )
        except ScheduleEditError:
            raise
        except Exception as exc:
            raise ScheduleSaveError("時間割変更を保存できず、変更をrollbackしました") from exc
        return self._record_command(saved)

    def _apply_metadata_change(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        is_locked: bool | None,
        note: str | None,
        change_note: bool,
        reason: str,
    ) -> EditResultDto:
        normalized_reason = _required_reason(reason)
        project = self._require_project()
        database = self._projects.require_database()
        try:
            with database.session_factory.begin() as session:
                repository = self._repository_factory(session)
                context = self._build_context(session, project.project_id)
                self._require_known(context.fingerprint)
                before = _find_snapshot(
                    context.snapshots,
                    lesson_request_id,
                    session_index,
                )
                if before is None:
                    raise ScheduleEditValidationError("指定した授業は配置されていません")
                after = AssignmentSnapshot(
                    project_id=before.project_id,
                    lesson_request_id=before.lesson_request_id,
                    session_index=before.session_index,
                    day=before.day,
                    time_slot_id=before.time_slot_id,
                    teacher_id=before.teacher_id,
                    optimization_run_id_optional=before.optimization_run_id_optional,
                    is_locked=is_locked if is_locked is not None else before.is_locked,
                    is_manual=True,
                    created_by="manual",
                    note=_normalized_note(note) if change_note else before.note,
                )
                action = _action_for(before, after, False, change_note)
                saved = self._persist_change(
                    repository=repository,
                    before_context=context,
                    before=before,
                    after=after,
                    action=action,
                    reason=normalized_reason,
                )
        except ScheduleEditError:
            raise
        except Exception as exc:
            raise ScheduleSaveError("編集内容を保存できず、変更をrollbackしました") from exc
        return self._record_command(saved)

    def _persist_change(
        self,
        *,
        repository: Phase5Repository,
        before_context: _PreparedContext,
        before: AssignmentSnapshot | None,
        after: AssignmentSnapshot | None,
        action: str,
        reason: str,
    ) -> tuple[_EditCommand, int, _PreparedContext]:
        if before == after:
            raise ScheduleEditValidationError("変更内容がありません")
        reference = before or after
        if reference is None:  # pragma: no cover - 呼出側の型絞込み
            raise AssertionError("beforeまたはafterが必要です")
        repository.restore_snapshot(
            project_id=reference.project_id,
            lesson_request_id=reference.lesson_request_id,
            session_index=reference.session_index,
            snapshot=after,
        )
        after_context = self._build_context(repository.session, reference.project_id)
        operation_id = str(uuid4())
        audit = repository.create_audit_log(
            AuditLog(
                project_id=reference.project_id,
                action=action,
                entity_type="AssignmentSession",
                entity_id=f"{reference.lesson_request_id}:{reference.session_index}",
                before_json=_snapshot_json(before),
                after_json=_snapshot_json(after),
                reason=reason,
                source="manual",
                operation_id_optional=operation_id,
            )
        )
        command = _EditCommand(
            operation_id=operation_id,
            action=action,
            lesson_request_id=reference.lesson_request_id,
            session_index=reference.session_index,
            before=before,
            after=after,
            before_fingerprint=before_context.fingerprint,
            after_fingerprint=after_context.fingerprint,
            reason=reason,
            diff=_schedule_diff(before_context.schedule, after_context.schedule),
        )
        return command, audit.id, after_context

    def _record_command(
        self,
        saved: tuple[_EditCommand, int, _PreparedContext],
    ) -> EditResultDto:
        command, audit_log_id, after_context = saved
        self._undo_stack.append(command)
        self._redo_stack.clear()
        self._known_fingerprint = command.after_fingerprint
        self._context_cache = after_context
        self._last_diff = command.diff
        return EditResultDto(
            action=command.action,
            lesson_request_id=command.lesson_request_id,
            session_index=command.session_index,
            fingerprint=command.after_fingerprint,
            audit_log_id=audit_log_id,
            can_undo=True,
            can_redo=False,
        )

    def _replay(
        self,
        command: _EditCommand,
        *,
        direction: UndoDirection,
    ) -> EditResultDto:
        project = self._require_project()
        database = self._projects.require_database()
        expected = command.after_fingerprint if direction == "undo" else command.before_fingerprint
        target = command.before if direction == "undo" else command.after
        expected_after = (
            command.before_fingerprint if direction == "undo" else command.after_fingerprint
        )
        before_snapshot = command.after if direction == "undo" else command.before
        source = direction
        try:
            with database.session_factory.begin() as session:
                repository = self._repository_factory(session)
                context = self._build_context(session, project.project_id)
                if context.fingerprint != expected:
                    raise ScheduleEditConflictError(
                        "DBが編集履歴と一致しません。再読込みしてから操作してください"
                    )
                current = _find_snapshot(
                    context.snapshots,
                    command.lesson_request_id,
                    command.session_index,
                )
                if current != before_snapshot:
                    raise ScheduleEditConflictError("対象授業が編集履歴と一致しません")
                repository.restore_snapshot(
                    project_id=project.project_id,
                    lesson_request_id=command.lesson_request_id,
                    session_index=command.session_index,
                    snapshot=target,
                )
                after_context = self._build_context(session, project.project_id)
                if after_context.fingerprint != expected_after:
                    raise ScheduleEditConflictError(
                        "逆操作後の整合性を確認できないためrollbackしました"
                    )
                audit = repository.create_audit_log(
                    AuditLog(
                        project_id=project.project_id,
                        action=f"{direction}:{command.action}",
                        entity_type="AssignmentSession",
                        entity_id=(f"{command.lesson_request_id}:{command.session_index}"),
                        before_json=_snapshot_json(current),
                        after_json=_snapshot_json(target),
                        reason=(
                            f"{'元に戻す' if direction == 'undo' else 'やり直す'}: {command.reason}"
                        ),
                        source=source,
                        operation_id_optional=command.operation_id,
                    )
                )
        except ScheduleEditError:
            raise
        except Exception as exc:
            raise ScheduleSaveError(
                f"{'Undo' if direction == 'undo' else 'Redo'}を保存できずrollbackしました"
            ) from exc
        self._known_fingerprint = expected_after
        self._context_cache = after_context
        replayed = _EditCommand(
            operation_id=command.operation_id,
            action=f"{direction}:{command.action}",
            lesson_request_id=command.lesson_request_id,
            session_index=command.session_index,
            before=current,
            after=target,
            before_fingerprint=expected,
            after_fingerprint=expected_after,
            reason=command.reason,
            diff=_schedule_diff(context.schedule, after_context.schedule),
        )
        self._last_diff = replayed.diff
        return EditResultDto(
            action=direction,
            lesson_request_id=command.lesson_request_id,
            session_index=command.session_index,
            fingerprint=expected_after,
            audit_log_id=audit.id,
            can_undo=(len(self._undo_stack) > 1 if direction == "undo" else True),
            can_redo=(True if direction == "undo" else len(self._redo_stack) > 1),
        )

    def _build_context(self, session: Session, project_id: int) -> _PreparedContext:
        data = build_optimization_input(
            session=session,
            project_id=project_id,
            settings=self._settings,
        )
        base_fingerprint = _base_fingerprint(data)
        if self._candidate_cache_key == base_fingerprint and self._candidate_cache is not None:
            generation = self._candidate_cache
        else:
            generation = generate_candidates(data)
            self._candidate_cache_key = base_fingerprint
            self._candidate_cache = generation
        repository = self._repository_factory(session)
        snapshots = tuple(
            snapshot
            for row in repository.list_assignments(project_id=project_id)
            if (snapshot := repository.snapshot(row)) is not None
        )
        return _PreparedContext(
            data=data,
            generation=generation,
            schedule=_edit_schedule(data, generation),
            snapshots=snapshots,
            base_fingerprint=base_fingerprint,
            fingerprint=_edit_fingerprint(base_fingerprint, snapshots),
        )

    def _require_known(self, fingerprint: str) -> None:
        if self._known_fingerprint is None:
            self._known_fingerprint = fingerprint
            return
        if self._known_fingerprint != fingerprint:
            raise ScheduleEditConflictError(
                "読み込み後にプロジェクトが変更されました。再読込みしてください"
            )

    def _require_project(self) -> ProjectSummary:
        project = self._projects.require_project()
        scope = (project.project_id, str(project.path.resolve(strict=False)))
        if self._cache_scope != scope:
            self._cache_scope = scope
            self._candidate_cache_key = None
            self._candidate_cache = None
            self._context_cache = None
            self._known_fingerprint = None
            self._checkpoint_baseline = None
            self._clear_command_history()
        return project

    def _cached_context(self, project: ProjectSummary) -> _PreparedContext:
        if self._context_cache is not None:
            return self._context_cache
        database = self._projects.require_database()
        with database.session_factory() as session:
            context = self._build_context(session, project.project_id)
        self._context_cache = context
        return context

    def _clear_command_history(self, *, clear_diff: bool = True) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        if clear_diff:
            self._last_diff = ()


def _optimization_settings(source: OptimizationAppSettings) -> OptimizationSettings:
    return OptimizationSettings(
        time_limit_seconds=source.time_limit_for(source.default_preset),
        random_seed=source.random_seed,
        num_search_workers=source.num_search_workers,
        regular_teacher_priority_weights=source.regular_teacher_priority_weights,
        preferred_teacher_rank_weights=source.preferred_teacher_rank_weights,
        student_preferred_time_weight=source.student_preferred_time_weight,
        teacher_preferred_time_weight=source.teacher_preferred_time_weight,
        preserve_existing_assignment_weight=source.preserve_existing_assignment_weight,
        optional_balance_weight=source.optional_balance_weight,
    )


def _edit_schedule(
    data: OptimizationInput,
    generation: CandidateGenerationResult,
) -> EditSchedule:
    requests = {item.id: item for item in data.lesson_requests}
    assignments = tuple(
        ScheduledAssignment(
            lesson_request_id=row.lesson_request_id,
            session_index=row.session_index,
            student_id=requests[row.lesson_request_id].student_id,
            subject_id=requests[row.lesson_request_id].subject_id,
            teacher_id=row.teacher_id,
            day=row.day,
            time_slot_id=row.time_slot_id,
            is_locked=row.is_locked,
        )
        for row in data.existing_assignments
    )
    assigned_keys = {
        (row.lesson_request_id, row.session_index) for row in data.existing_assignments
    }
    unassigned: list[UnassignedLesson] = []
    for row in generation.sessions:
        if row.key in assigned_keys:
            continue
        diagnostic = generation.diagnostics_for(row.lesson_request_id, row.session_index)
        unassigned.append(
            UnassignedLesson(
                lesson_request_id=row.lesson_request_id,
                session_index=row.session_index,
                student_id=row.student_id,
                subject_id=row.subject_id,
                reasons=diagnostic.reasons if diagnostic is not None else (),
            )
        )
    return EditSchedule(
        assignments=assignments,
        unassigned_lessons=tuple(unassigned),
    )


def _base_fingerprint(data: OptimizationInput) -> str:
    document = json.loads(optimization_input_to_json(data))
    payload = document["data"]
    if not isinstance(payload, dict):  # pragma: no cover - 自前codecの保証
        raise ScheduleEditValidationError("最適化入力snapshotの形式が不正です")
    raw_assignments = payload.get("existing_assignments")
    if not isinstance(raw_assignments, list):  # pragma: no cover - 自前codecの保証
        raise ScheduleEditValidationError("最適化入力のAssignment形式が不正です")
    locked_assignments: list[object] = []
    for raw in raw_assignments:
        if not isinstance(raw, dict):  # pragma: no cover - 自前codecの保証
            raise ScheduleEditValidationError("最適化入力のAssignment形式が不正です")
        if raw.get("is_locked") is True:
            normalized = dict(raw)
            # 採番IDの変化は候補集合へ影響しないためcache keyから除外する。
            normalized["id"] = 0
            locked_assignments.append(normalized)
    payload["existing_assignments"] = locked_assignments
    return _sha256(_canonical_json(document))


def _edit_fingerprint(
    base_fingerprint: str,
    snapshots: tuple[AssignmentSnapshot, ...],
) -> str:
    logical = [
        _snapshot_object(item)
        for item in sorted(
            snapshots,
            key=lambda row: (row.lesson_request_id, row.session_index),
        )
    ]
    return _sha256(
        _canonical_json(
            {
                "base_fingerprint": base_fingerprint,
                "assignments": logical,
            }
        )
    )


def _preview_dto(preview: EditPreview, context: _PreparedContext) -> EditPreviewDto:
    current = _find_snapshot(
        context.snapshots,
        preview.operation.lesson_request_id,
        preview.operation.session_index,
    )
    action = _action_from_kind(preview.operation.kind)
    after_summary = (
        "未配置"
        if preview.operation.kind is EditOperationKind.UNASSIGN
        else _target_summary(preview.operation.target)
    )
    return EditPreviewDto(
        action=action,
        lesson_request_id=preview.operation.lesson_request_id,
        session_index=preview.operation.session_index,
        allowed=preview.allowed,
        decision=preview.decision.value,
        preview_code=preview.code.value,
        hard_issue_codes=tuple(item.code.value for item in preview.hard_issues),
        hard_issues=tuple(item.message for item in preview.hard_issues),
        soft_warnings=tuple(item.message for item in preview.worsened_soft_deltas),
        soft_deltas=tuple(
            SoftMetricDeltaDto(
                code=item.code.value,
                label=item.label,
                direction=item.direction.value,
                before_value=item.before_value,
                after_value=item.after_value,
                worsened=item.worsened,
                message=item.message,
            )
            for item in preview.soft_deltas
        ),
        before_summary=_snapshot_summary(current),
        after_summary=after_summary,
        expected_fingerprint=context.fingerprint,
    )


def _require_preview_allowed(preview: EditPreview, confirm_soft_warnings: bool) -> None:
    if not preview.allowed:
        issues = tuple(item.message for item in preview.hard_issues) or (preview.message,)
        raise HardConstraintViolationError(issues)
    warnings = tuple(item.message for item in preview.worsened_soft_deltas)
    if warnings and not confirm_soft_warnings:
        raise SoftWarningConfirmationRequired(warnings)


def _find_snapshot(
    snapshots: tuple[AssignmentSnapshot, ...],
    lesson_request_id: int,
    session_index: int,
) -> AssignmentSnapshot | None:
    return next(
        (
            item
            for item in snapshots
            if item.lesson_request_id == lesson_request_id and item.session_index == session_index
        ),
        None,
    )


def _action_for(
    before: AssignmentSnapshot | None,
    after: AssignmentSnapshot,
    placement_changed: bool,
    change_note: bool,
) -> str:
    if before is None:
        return "assign_unassigned"
    if placement_changed:
        return "move"
    if before.is_locked != after.is_locked:
        return "lock" if after.is_locked else "unlock"
    if change_note and before.note != after.note:
        return "note"
    raise ScheduleEditValidationError("変更内容がありません")


def _action_from_kind(kind: EditOperationKind) -> EditAction:
    if kind is EditOperationKind.MOVE:
        return "move"
    if kind is EditOperationKind.ASSIGN_UNASSIGNED:
        return "assign_unassigned"
    return "unassign"


def _required_reason(reason: str) -> str:
    value = reason.strip()
    if not value:
        raise ScheduleEditValidationError("手動変更の理由を入力してください")
    return value


def _normalized_note(note: str | None) -> str | None:
    if note is None:
        return None
    value = note.strip()
    return value or None


def _snapshot_object(snapshot: AssignmentSnapshot) -> dict[str, object]:
    value = asdict(snapshot)
    value["day"] = snapshot.day.isoformat()
    return value


def _snapshot_json(snapshot: AssignmentSnapshot | None) -> str | None:
    return None if snapshot is None else _canonical_json(_snapshot_object(snapshot))


def _snapshot_summary(snapshot: AssignmentSnapshot | None) -> str:
    if snapshot is None:
        return "未配置"
    return (
        f"{snapshot.day.isoformat()} / コマID {snapshot.time_slot_id} / "
        f"講師ID {snapshot.teacher_id}"
    )


def _target_summary(target: EditTarget | None) -> str:
    if target is None:
        return "未配置"
    return f"{target.day.isoformat()} / コマID {target.time_slot_id} / 講師ID {target.teacher_id}"


def _schedule_diff(
    before: EditSchedule,
    after: EditSchedule,
) -> tuple[ScheduleDiffDto, ...]:
    return tuple(
        ScheduleDiffDto(
            lesson_request_id=entry.lesson_request_id,
            session_index=entry.session_index,
            change_type="+".join(kind.value for kind in entry.change_kinds),
            change_codes=tuple(kind.value for kind in entry.change_kinds),
            before_summary=_scheduled_summary(entry.before),
            after_summary=_scheduled_summary(entry.after),
            before_pairing_size=entry.before_pairing_size,
            after_pairing_size=entry.after_pairing_size,
        )
        for entry in diff_schedules(before, after)
    )


def _scheduled_summary(assignment: ScheduledAssignment | None) -> str:
    if assignment is None:
        return "未配置"
    return (
        f"{assignment.day.isoformat()} / コマID {assignment.time_slot_id} / "
        f"講師ID {assignment.teacher_id}"
    )


def _persisted_diff(
    session: Session,
    context: _PreparedContext,
) -> tuple[ScheduleDiffDto, ...]:
    """再起動後も最新の手動操作または最適化runのbefore/afterを復元する。"""
    audit = session.scalar(
        select(AuditLog)
        .where(
            AuditLog.project_id == context.data.project_id,
            AuditLog.entity_type == "AssignmentSession",
            AuditLog.source.in_(("manual", "undo", "redo")),
        )
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(1)
    )
    run = session.scalar(
        select(OptimizationRun)
        .where(
            OptimizationRun.project_id == context.data.project_id,
            OptimizationRun.status == "completed",
        )
        .order_by(OptimizationRun.finished_at.desc(), OptimizationRun.id.desc())
        .limit(1)
    )
    if audit is not None and (
        run is None
        or run.finished_at is None
        or _timestamp_key(audit.timestamp) >= _timestamp_key(run.finished_at)
    ):
        before_snapshot = _snapshot_from_json(audit.before_json)
        after_snapshot = _snapshot_from_json(audit.after_json)
        key_source = before_snapshot or after_snapshot
        if key_source is not None and _schedule_has_snapshot(
            context.schedule,
            after_snapshot,
            key_source.key,
        ):
            before_schedule = _schedule_replacing(
                context,
                key_source.key,
                before_snapshot,
            )
            return _schedule_diff(before_schedule, context.schedule)
    if run is None or run.result_snapshot_json == "{}":
        return ()
    return _optimization_run_diff(run.result_snapshot_json, context)


def _optimization_run_diff(
    result_snapshot_json: str,
    context: _PreparedContext,
) -> tuple[ScheduleDiffDto, ...]:
    try:
        document = json.loads(result_snapshot_json)
    except json.JSONDecodeError as exc:
        raise ScheduleEditValidationError("最適化runの差分snapshotが不正です") from exc
    if not isinstance(document, dict) or document.get("schema") != (
        "summer_scheduler.optimization_run_result"
    ):
        return ()
    if document.get("schema_version") != 1:
        raise ScheduleEditValidationError("未対応の最適化run差分snapshotです")
    previous_raw = document.get("previous_assignments")
    result_raw = document.get("optimization_result")
    if not isinstance(previous_raw, list) or not isinstance(result_raw, dict):
        raise ScheduleEditValidationError("最適化runの差分snapshotに必要な項目がありません")
    previous = tuple(
        _snapshot_from_mapping(row, project_id=context.data.project_id) for row in previous_raw
    )
    before = _schedule_from_snapshots(context, previous)
    result = optimization_result_from_json(_canonical_json(result_raw))
    after = EditSchedule(
        assignments=result.assignments,
        unassigned_lessons=result.unassigned_lessons,
    )
    return _schedule_diff(before, after)


def _schedule_from_snapshots(
    context: _PreparedContext,
    snapshots: tuple[AssignmentSnapshot, ...],
) -> EditSchedule:
    request_by_id = {item.id: item for item in context.data.lesson_requests}
    assignments = tuple(
        ScheduledAssignment(
            lesson_request_id=item.lesson_request_id,
            session_index=item.session_index,
            student_id=request_by_id[item.lesson_request_id].student_id,
            subject_id=request_by_id[item.lesson_request_id].subject_id,
            teacher_id=item.teacher_id,
            day=item.day,
            time_slot_id=item.time_slot_id,
            is_locked=item.is_locked,
        )
        for item in snapshots
    )
    assigned_keys = {(item.lesson_request_id, item.session_index) for item in snapshots}
    unassigned = tuple(
        UnassignedLesson(
            lesson_request_id=item.lesson_request_id,
            session_index=item.session_index,
            student_id=item.student_id,
            subject_id=item.subject_id,
            reasons=(),
        )
        for item in context.generation.sessions
        if item.key not in assigned_keys
    )
    return EditSchedule(assignments=assignments, unassigned_lessons=unassigned)


def _schedule_replacing(
    context: _PreparedContext,
    key: tuple[int, int],
    snapshot: AssignmentSnapshot | None,
) -> EditSchedule:
    snapshots = tuple(item for item in context.snapshots if item.key != key) + (
        (snapshot,) if snapshot is not None else ()
    )
    return _schedule_from_snapshots(context, snapshots)


def _schedule_has_snapshot(
    schedule: EditSchedule,
    snapshot: AssignmentSnapshot | None,
    key: tuple[int, int],
) -> bool:
    current = next(
        (
            item
            for item in schedule.assignments
            if (item.lesson_request_id, item.session_index) == key
        ),
        None,
    )
    if snapshot is None:
        return current is None
    return current is not None and (
        current.day,
        current.time_slot_id,
        current.teacher_id,
        current.is_locked,
    ) == (
        snapshot.day,
        snapshot.time_slot_id,
        snapshot.teacher_id,
        snapshot.is_locked,
    )


def _snapshot_from_json(payload: str | None) -> AssignmentSnapshot | None:
    if payload is None:
        return None
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ScheduleEditValidationError("監査ログのAssignment snapshotが不正です") from exc
    return _snapshot_from_mapping(raw)


def _snapshot_from_mapping(
    raw: object,
    *,
    project_id: int | None = None,
) -> AssignmentSnapshot:
    if not isinstance(raw, dict):
        raise ScheduleEditValidationError("Assignment snapshotはobjectである必要があります")
    try:
        return AssignmentSnapshot(
            project_id=_strict_int(raw.get("project_id", project_id)),
            lesson_request_id=_strict_int(raw["lesson_request_id"]),
            session_index=_strict_int(raw["session_index"]),
            day=date.fromisoformat(str(raw["day"] if "day" in raw else raw["date"])),
            time_slot_id=_strict_int(raw["time_slot_id"]),
            teacher_id=_strict_int(raw["teacher_id"]),
            optimization_run_id_optional=_optional_int(
                raw.get("optimization_run_id_optional", raw.get("optimization_run_id"))
            ),
            is_locked=_strict_bool(raw["is_locked"]),
            is_manual=_strict_bool(raw["is_manual"]),
            created_by=str(raw["created_by"]),
            note=_optional_str(raw.get("note")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ScheduleEditValidationError("Assignment snapshotの項目が不正です") from exc


def _strict_bool(value: object) -> bool:
    if type(value) is not bool:
        raise TypeError("boolean required")
    return value


def _strict_int(value: object) -> int:
    if type(value) is not int:
        raise TypeError("integer required")
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _strict_int(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _timestamp_key(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "HardConstraintViolationError",
    "ScheduleEditConflictError",
    "ScheduleEditError",
    "ScheduleEditService",
    "ScheduleEditValidationError",
    "ScheduleSaveError",
    "SoftWarningConfirmationRequired",
    "UndoRedoUnavailableError",
]
