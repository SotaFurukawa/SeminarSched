"""Phase 5の手動編集・監査をtransaction内で扱うRepository。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db.models import Assignment, AuditLog

_ASSIGNMENT_UPDATE_FIELDS = frozenset(
    {
        "date",
        "time_slot_id",
        "teacher_id",
        "optimization_run_id_optional",
        "is_locked",
        "is_manual",
        "created_by",
        "note",
    }
)


@dataclass(frozen=True, slots=True)
class AssignmentSnapshot:
    """採番IDに依存しない、Undo/Redo用のAssignment論理状態。"""

    project_id: int
    lesson_request_id: int
    session_index: int
    day: date
    time_slot_id: int
    teacher_id: int
    optimization_run_id_optional: int | None
    is_locked: bool
    is_manual: bool
    created_by: str
    note: str | None

    @property
    def key(self) -> tuple[int, int]:
        return self.lesson_request_id, self.session_index


class Phase5Repository:
    """commit/rollbackを呼出側へ残す手動編集Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get_assignment(
        self,
        *,
        project_id: int,
        lesson_request_id: int,
        session_index: int,
    ) -> Assignment | None:
        return self._session.scalar(
            select(Assignment).where(
                Assignment.project_id == project_id,
                Assignment.lesson_request_id == lesson_request_id,
                Assignment.session_index == session_index,
            )
        )

    def list_assignments(self, *, project_id: int) -> list[Assignment]:
        return list(
            self._session.scalars(
                select(Assignment)
                .where(Assignment.project_id == project_id)
                .order_by(
                    Assignment.lesson_request_id,
                    Assignment.session_index,
                    Assignment.id,
                )
            )
        )

    def create_assignment(self, snapshot: AssignmentSnapshot) -> Assignment:
        if self.get_assignment(
            project_id=snapshot.project_id,
            lesson_request_id=snapshot.lesson_request_id,
            session_index=snapshot.session_index,
        ):
            raise ValueError("同じ授業回は既に配置されています")
        row = Assignment(
            project_id=snapshot.project_id,
            lesson_request_id=snapshot.lesson_request_id,
            session_index=snapshot.session_index,
            date=snapshot.day,
            time_slot_id=snapshot.time_slot_id,
            teacher_id=snapshot.teacher_id,
            optimization_run_id_optional=snapshot.optimization_run_id_optional,
            is_locked=snapshot.is_locked,
            is_manual=snapshot.is_manual,
            created_by=snapshot.created_by,
            note=snapshot.note,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def update_assignment(
        self,
        assignment: Assignment,
        **changes: object,
    ) -> Assignment:
        unknown = set(changes) - _ASSIGNMENT_UPDATE_FIELDS
        if unknown:
            names = "、".join(sorted(unknown))
            raise ValueError(f"更新できないAssignment項目です: {names}")
        for name, value in changes.items():
            setattr(assignment, name, value)
        self._session.flush()
        return assignment

    def delete_assignment(
        self,
        *,
        project_id: int,
        lesson_request_id: int,
        session_index: int,
    ) -> bool:
        row = self.get_assignment(
            project_id=project_id,
            lesson_request_id=lesson_request_id,
            session_index=session_index,
        )
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def restore_snapshot(
        self,
        *,
        project_id: int,
        lesson_request_id: int,
        session_index: int,
        snapshot: AssignmentSnapshot | None,
    ) -> Assignment | None:
        """現在行をsnapshotへ原子的に合わせる。Noneは未配置を表す。"""
        current = self.get_assignment(
            project_id=project_id,
            lesson_request_id=lesson_request_id,
            session_index=session_index,
        )
        if snapshot is None:
            if current is not None:
                self._session.delete(current)
                self._session.flush()
            return None
        if snapshot.project_id != project_id or snapshot.key != (
            lesson_request_id,
            session_index,
        ):
            raise ValueError("別プロジェクトまたは別授業回のsnapshotは復元できません")
        if current is None:
            return self.create_assignment(snapshot)
        self.update_assignment(
            current,
            date=snapshot.day,
            time_slot_id=snapshot.time_slot_id,
            teacher_id=snapshot.teacher_id,
            optimization_run_id_optional=snapshot.optimization_run_id_optional,
            is_locked=snapshot.is_locked,
            is_manual=snapshot.is_manual,
            created_by=snapshot.created_by,
            note=snapshot.note,
        )
        return current

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        self._session.add(audit_log)
        self._session.flush()
        return audit_log

    def list_audit_logs(
        self,
        *,
        project_id: int,
        limit: int = 100,
    ) -> list[AuditLog]:
        if limit < 1:
            raise ValueError("監査ログの取得件数は1以上で指定してください")
        return list(
            self._session.scalars(
                select(AuditLog)
                .where(AuditLog.project_id == project_id)
                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                .limit(limit)
            )
        )

    @staticmethod
    def snapshot(assignment: Assignment | None) -> AssignmentSnapshot | None:
        if assignment is None:
            return None
        return AssignmentSnapshot(
            project_id=assignment.project_id,
            lesson_request_id=assignment.lesson_request_id,
            session_index=assignment.session_index,
            day=assignment.date,
            time_slot_id=assignment.time_slot_id,
            teacher_id=assignment.teacher_id,
            optimization_run_id_optional=assignment.optimization_run_id_optional,
            is_locked=assignment.is_locked,
            is_manual=assignment.is_manual,
            created_by=assignment.created_by,
            note=assignment.note,
        )

    @staticmethod
    def apply_snapshot_changes(
        snapshot: AssignmentSnapshot,
        changes: Mapping[str, object],
    ) -> AssignmentSnapshot:
        """限定フィールドだけを変更した新snapshotを返す。"""
        aliases = {"date": "day"}
        normalized = {aliases.get(key, key): value for key, value in changes.items()}
        allowed = set(AssignmentSnapshot.__dataclass_fields__)
        unknown = set(normalized) - allowed
        if unknown:
            names = "、".join(sorted(unknown))
            raise ValueError(f"snapshotに存在しない項目です: {names}")
        values: dict[str, object] = {
            field: getattr(snapshot, field) for field in AssignmentSnapshot.__dataclass_fields__
        }
        values.update(normalized)
        return AssignmentSnapshot(**values)  # type: ignore[arg-type]


__all__ = ["AssignmentSnapshot", "Phase5Repository"]
