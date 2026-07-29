"""Phase 4の現在時間割と最適化履歴を扱うRepository。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db.models import Assignment, OptimizationRun

_ASSIGNMENT_UPDATE_FIELDS = frozenset(
    {
        "date",
        "time_slot_id",
        "teacher_id",
        "is_locked",
        "is_manual",
        "created_by",
        "optimization_run_id_optional",
    }
)
_RUN_UPDATE_FIELDS = frozenset(
    {
        "finished_at",
        "status",
        "solver_status",
        "objective_summary_json",
        "unassigned_count",
        "warning_count",
        "log_path_optional",
        "input_snapshot_json",
        "result_snapshot_json",
        "elapsed_seconds",
    }
)


class Phase4Repository:
    """SQLAlchemy Sessionのtransaction境界を越えずにPhase 4データを操作する。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """呼出側がcommit/rollbackを管理する同一Sessionを返す。"""
        return self._session

    def create_assignment(self, assignment: Assignment) -> Assignment:
        """Assignmentを追加し、採番済みの行を返す。"""
        self._session.add(assignment)
        self._session.flush()
        return assignment

    def get_assignment(self, assignment_id: int) -> Assignment | None:
        return self._session.get(Assignment, assignment_id)

    def list_assignments(
        self,
        *,
        project_id: int,
        lesson_request_id: int | None = None,
        teacher_id: int | None = None,
        date_value: date | None = None,
        is_locked: bool | None = None,
    ) -> list[Assignment]:
        statement = select(Assignment).where(Assignment.project_id == project_id)
        if lesson_request_id is not None:
            statement = statement.where(Assignment.lesson_request_id == lesson_request_id)
        if teacher_id is not None:
            statement = statement.where(Assignment.teacher_id == teacher_id)
        if date_value is not None:
            statement = statement.where(Assignment.date == date_value)
        if is_locked is not None:
            statement = statement.where(Assignment.is_locked.is_(is_locked))
        return list(
            self._session.scalars(
                statement.order_by(
                    Assignment.date,
                    Assignment.time_slot_id,
                    Assignment.teacher_id,
                    Assignment.lesson_request_id,
                    Assignment.session_index,
                )
            )
        )

    def update_assignment(
        self,
        assignment: Assignment,
        **changes: object,
    ) -> Assignment:
        self._apply_changes(
            assignment,
            changes,
            allowed=_ASSIGNMENT_UPDATE_FIELDS,
        )
        self._session.flush()
        return assignment

    def delete_assignment(self, assignment_id: int) -> bool:
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            return False
        self._session.delete(assignment)
        self._session.flush()
        return True

    def create_optimization_run(
        self,
        optimization_run: OptimizationRun,
    ) -> OptimizationRun:
        """実行履歴を追加する。スナップショットはローカルDBだけに保存する。"""
        self._session.add(optimization_run)
        self._session.flush()
        return optimization_run

    def get_optimization_run(
        self,
        optimization_run_id: int,
    ) -> OptimizationRun | None:
        return self._session.get(OptimizationRun, optimization_run_id)

    def list_optimization_runs(
        self,
        *,
        project_id: int,
        status: str | None = None,
    ) -> list[OptimizationRun]:
        statement = select(OptimizationRun).where(OptimizationRun.project_id == project_id)
        if status is not None:
            statement = statement.where(OptimizationRun.status == status)
        return list(
            self._session.scalars(
                statement.order_by(
                    OptimizationRun.started_at.desc(),
                    OptimizationRun.id.desc(),
                )
            )
        )

    def update_optimization_run(
        self,
        optimization_run: OptimizationRun,
        **changes: object,
    ) -> OptimizationRun:
        self._apply_changes(
            optimization_run,
            changes,
            allowed=_RUN_UPDATE_FIELDS,
        )
        self._session.flush()
        return optimization_run

    def replace_assignments(
        self,
        *,
        project_id: int,
        assignments: Iterable[Assignment],
        preserve_locked: bool = True,
    ) -> list[Assignment]:
        """現在時間割を置換し、必要ならロック済み行を必ず保持する。

        呼出側は置換前の内容をOptimizationRun.result_snapshot_json等へ保存してから
        このメソッドを呼ぶ。検証・削除・追加は同じSession内で行い、commitしない。
        """
        incoming = list(assignments)
        self._validate_replacement(project_id, incoming)
        locked = (
            self.list_assignments(project_id=project_id, is_locked=True) if preserve_locked else []
        )
        locked_by_key = {_session_key(row): row for row in locked}
        additions: list[Assignment] = []
        for row in incoming:
            current_locked = locked_by_key.get(_session_key(row))
            if current_locked is None:
                additions.append(row)
                continue
            if not _same_placement(current_locked, row):
                raise ValueError("ロック済みAssignmentと異なる配置で置換することはできません")

        delete_statement = delete(Assignment).where(Assignment.project_id == project_id)
        if preserve_locked:
            delete_statement = delete_statement.where(Assignment.is_locked.is_(False))
        self._session.execute(delete_statement)
        self._session.flush()
        self._session.add_all(additions)
        self._session.flush()
        return sorted(
            [*locked, *additions],
            key=lambda row: (
                row.date,
                row.time_slot_id,
                row.teacher_id,
                row.lesson_request_id,
                row.session_index,
            ),
        )

    def save_run_and_replace_assignments(
        self,
        *,
        optimization_run: OptimizationRun,
        assignments: Iterable[Assignment],
        preserve_locked: bool = True,
    ) -> list[Assignment]:
        """履歴追加と現在時間割置換を呼出側の1 transaction内で行う。"""
        incoming = list(assignments)
        self._validate_replacement(optimization_run.project_id, incoming)
        self.create_optimization_run(optimization_run)
        for assignment in incoming:
            if assignment.optimization_run_id_optional is None:
                assignment.optimization_run_id_optional = optimization_run.id
        return self.replace_assignments(
            project_id=optimization_run.project_id,
            assignments=incoming,
            preserve_locked=preserve_locked,
        )

    @staticmethod
    def _apply_changes(
        entity: Assignment | OptimizationRun,
        changes: Mapping[str, object],
        *,
        allowed: frozenset[str],
    ) -> None:
        unknown = set(changes) - allowed
        if unknown:
            names = "、".join(sorted(unknown))
            raise ValueError(f"更新できないフィールドです: {names}")
        for field, value in changes.items():
            setattr(entity, field, value)

    @staticmethod
    def _validate_replacement(
        project_id: int,
        assignments: list[Assignment],
    ) -> None:
        if any(row.project_id != project_id for row in assignments):
            raise ValueError("別プロジェクトのAssignmentは置換できません")
        if any(row.id is not None for row in assignments):
            raise ValueError("置換には未永続化のAssignmentを指定してください")
        keys = [_session_key(row) for row in assignments]
        if len(keys) != len(set(keys)):
            raise ValueError("同じ受講希望・セッション番号が重複しています")


def _session_key(assignment: Assignment) -> tuple[int, int]:
    return assignment.lesson_request_id, assignment.session_index


def _same_placement(left: Assignment, right: Assignment) -> bool:
    return (
        left.date == right.date
        and left.time_slot_id == right.time_slot_id
        and left.teacher_id == right.teacher_id
    )


__all__ = ["Phase4Repository"]
