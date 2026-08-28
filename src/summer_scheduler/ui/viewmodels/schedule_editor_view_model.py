"""Phase 5時間割編集を仮想化QMLモデルへ公開するViewModel。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Protocol, cast

from PySide6.QtCore import (
    Property,
    QAbstractTableModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from summer_scheduler.application.phase5_dto import (
    AuditLogDto,
    CheckpointBackupDto,
    EditPreviewDto,
    GroupBlockDto,
    ReoptimizationSummaryDto,
    ScheduleBoardDto,
    ScheduleCardDto,
    ScheduleDiffDto,
    UnassignedSessionDto,
)
from summer_scheduler.application.project_service import ProjectService

logger = logging.getLogger(__name__)

_WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")
_DECISION_ICON = {"green": "✓", "yellow": "△", "red": "✕"}
_ACTION_LABELS = {
    "move": "授業移動",
    "assign_unassigned": "未配置から配置",
    "unassign": "未配置へ移動",
    "lock": "ロック",
    "unlock": "ロック解除",
    "note": "備考変更",
    "edit": "詳細編集",
    "undo": "Undo",
    "redo": "Redo",
}
_DIFF_LABELS = {
    "new": "新規配置",
    "added": "新規配置",
    "date": "日時変更",
    "date_changed": "日時変更",
    "time_changed": "日時変更",
    "moved": "日時変更",
    "teacher": "講師変更",
    "teacher_changed": "講師変更",
    "unassigned": "未配置化",
    "pairing": "1対1／1対2変化",
    "pairing_changed": "1対1／1対2変化",
    "unchanged": "変更なし",
}
_EMPTY_PREVIEW: dict[str, object] = {
    "decision": "",
    "code": "",
    "icon": "",
    "message": "",
    "targetKey": "",
    "hardIssues": [],
    "hardIssueCodes": [],
    "softDeltas": [],
    "beforeSummary": "",
    "afterSummary": "",
}
_ROOT_MODEL_INDEX = QModelIndex()


class ScheduleEditServiceProtocol(Protocol):
    """ViewModelが必要とするPhase 5 application service境界。"""

    def load_board(self) -> ScheduleBoardDto: ...

    def preview_move(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        day: date,
        time_slot_id: int,
        teacher_id: int,
    ) -> EditPreviewDto: ...

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
    ) -> object: ...

    def create_preconfirmed_assignment(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        day: date,
        time_slot_id: int,
        teacher_id: int,
        note: str = "",
    ) -> object: ...

    def preview_unassign(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
    ) -> EditPreviewDto: ...

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
    ) -> object: ...

    def unassign(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        reason: str,
        confirm_soft_warnings: bool = False,
    ) -> object: ...

    def set_lock(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        is_locked: bool,
        reason: str,
    ) -> object: ...

    def undo(self) -> object: ...

    def redo(self) -> object: ...

    def reoptimization_summary(self) -> ReoptimizationSummaryDto: ...

    def create_checkpoint_backup(self) -> CheckpointBackupDto: ...

    def create_manual_backup(self) -> CheckpointBackupDto: ...


class ScheduleGridModel(QAbstractTableModel):
    """当日分だけを保持する、講師列×コマ行の再利用可能TableView model。"""

    CellDataRole = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cells: list[list[dict[str, object]]] = []
        self._teacher_labels: list[str] = []
        self._slot_labels: list[str] = []

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = _ROOT_MODEL_INDEX,
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._cells)

    def columnCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = _ROOT_MODEL_INDEX,
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._teacher_labels)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object | None:
        if (
            not index.isValid()
            or index.row() < 0
            or index.column() < 0
            or index.row() >= len(self._cells)
            or index.column() >= len(self._teacher_labels)
        ):
            return None
        if role == self.CellDataRole:
            return self._cells[index.row()][index.column()]
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object | None:
        if role != int(Qt.ItemDataRole.DisplayRole) or section < 0:
            return None
        labels = (
            self._teacher_labels if orientation == Qt.Orientation.Horizontal else self._slot_labels
        )
        return labels[section] if section < len(labels) else None

    def roleNames(self) -> dict[int, QByteArray]:
        return {self.CellDataRole: QByteArray(b"cellData")}

    def replace(
        self,
        *,
        cells: list[list[dict[str, object]]],
        teacher_labels: list[str],
        slot_labels: list[str],
    ) -> None:
        self.beginResetModel()
        self._cells = cells
        self._teacher_labels = teacher_labels
        self._slot_labels = slot_labels
        self.endResetModel()


@dataclass(frozen=True, slots=True)
class _PendingEdit:
    kind: str
    lesson_request_id: int
    session_index: int
    day: date | None
    time_slot_id: int
    teacher_id: int
    is_locked: bool | None = None
    note: str | None = None


class ScheduleEditorViewModel(QObject):
    """ScheduleEditServiceのDTOをQMLの基本型と仮想化表へ変換する。"""

    projectStateChanged = Signal()
    boardChanged = Signal()
    selectionChanged = Signal()
    previewChanged = Signal()
    navigationChanged = Signal()
    filterChanged = Signal()
    messageChanged = Signal()
    saveStateChanged = Signal()
    scheduleSaved = Signal()

    def __init__(
        self,
        service: ScheduleEditServiceProtocol,
        projects: ProjectService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._projects = projects
        self._grid_model = ScheduleGridModel(self)
        self._board: ScheduleBoardDto | None = None
        self._current_date: date | None = None
        self._view_mode = "day"
        self._zoom_factor = 1.0
        self._search_query = ""
        self._grade_filter = ""
        self._subject_filter = ""
        self._flag_filters = {
            "oneToOne": False,
            "priority5": False,
            "warning": False,
            "locked": False,
            "unassigned": False,
        }
        self._selected_key: tuple[int, int] | None = None
        self._selected_lesson: dict[str, object] = {}
        self._drop_preview = dict(_EMPTY_PREVIEW)
        self._pending_edit: _PendingEdit | None = None
        self._reoptimization_summary: dict[str, object] = {}
        self._status_message = ""
        self._error_message = ""
        self._is_saving = False
        self._draft_editing = False
        self._save_failed = False
        self.refreshSchedule()

    # QML properties

    def _get_has_open_project(self) -> bool:
        return self._projects.current is not None

    hasOpenProject = Property(bool, _get_has_open_project, notify=projectStateChanged)

    def _get_grid_model(self) -> QObject:
        return self._grid_model

    gridModel = Property(QObject, _get_grid_model, constant=True)

    def _get_current_date(self) -> str:
        return "" if self._current_date is None else self._current_date.isoformat()

    currentDate = Property(str, _get_current_date, notify=navigationChanged)

    def _get_date_tabs(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        return [
            {
                "date": row.day.isoformat(),
                "label": _date_label(row.day),
                "selected": row.day == self._current_date,
                "isOpen": row.is_open,
                "note": row.note,
            }
            for row in board.dates
        ]

    dateTabs = Property(list, _get_date_tabs, notify=navigationChanged)

    def _get_can_go_previous_date(self) -> bool:
        return self._date_index() > 0

    canGoPreviousDate = Property(
        bool,
        _get_can_go_previous_date,
        notify=navigationChanged,
    )

    def _get_can_go_next_date(self) -> bool:
        board = self._board
        index = self._date_index()
        return board is not None and index >= 0 and index + 1 < len(board.dates)

    canGoNextDate = Property(bool, _get_can_go_next_date, notify=navigationChanged)

    def _get_view_mode(self) -> str:
        return self._view_mode

    viewMode = Property(str, _get_view_mode, notify=navigationChanged)

    def _get_zoom_factor(self) -> float:
        return self._zoom_factor

    zoomFactor = Property(float, _get_zoom_factor, notify=navigationChanged)

    def _get_teacher_headers(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        return [{"id": row.id, "label": row.name, "active": row.active} for row in board.teachers]

    teacherHeaders = Property(list, _get_teacher_headers, notify=boardChanged)

    def _get_slot_headers(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        return [
            {
                "id": row.id,
                "code": row.code,
                "label": row.display_name,
                "enabled": row.enabled,
                "time": f"{row.start_time:%H:%M}～{row.end_time:%H:%M}",
            }
            for row in board.slots
        ]

    slotHeaders = Property(list, _get_slot_headers, notify=boardChanged)

    def _get_grade_options(self) -> list[dict[str, str]]:
        board = self._board
        values: set[str] = set()
        if board is not None:
            values.update(card.grade for card in board.cards)
            values.update(row.grade for row in board.unassigned)
        return [{"label": "すべての学年", "value": ""}] + [
            {"label": value, "value": value} for value in sorted(values)
        ]

    gradeOptions = Property(list, _get_grade_options, notify=boardChanged)

    def _get_subject_options(self) -> list[dict[str, str]]:
        board = self._board
        values: dict[str, str] = {}
        if board is not None:
            values.update((card.subject_code, card.subject_name) for card in board.cards)
            values.update((row.subject_code, row.subject_name) for row in board.unassigned)
        return [{"label": "すべての科目", "value": ""}] + [
            {"label": label, "value": code}
            for code, label in sorted(values.items(), key=lambda item: item[1])
        ]

    subjectOptions = Property(list, _get_subject_options, notify=boardChanged)

    def _get_unassigned_lessons(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        return [self._unassigned_dict(row) for row in board.unassigned]

    unassignedLessons = Property(list, _get_unassigned_lessons, notify=filterChanged)

    def _get_preconfirmation_candidates(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        return [
            {
                **self._unassigned_dict(row),
                "label": (f"{row.student_name}／{row.subject_name}／第{row.session_index}回"),
            }
            for row in board.unassigned
        ]

    preconfirmationCandidates = Property(
        list,
        _get_preconfirmation_candidates,
        notify=boardChanged,
    )

    def _get_preconfirmed_assignments(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        return [self._card_dict(row) for row in board.cards if row.is_locked and row.is_manual]

    preconfirmedAssignments = Property(
        list,
        _get_preconfirmed_assignments,
        notify=boardChanged,
    )

    def _get_unassigned_count(self) -> int:
        return 0 if self._board is None else self._board.unassigned_count

    unassignedCount = Property(int, _get_unassigned_count, notify=boardChanged)

    def _get_day_summaries(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        cards_by_date: dict[date, list[ScheduleCardDto]] = {}
        for card in board.cards:
            cards_by_date.setdefault(card.day, []).append(card)
        groups_by_date: dict[date, list[GroupBlockDto]] = {}
        for group in board.group_blocks:
            groups_by_date.setdefault(group.day, []).append(group)
        return [
            self._day_summary(
                row.day,
                cards_by_date.get(row.day, []),
                groups_by_date.get(row.day, []),
            )
            for row in board.dates
        ]

    daySummaries = Property(list, _get_day_summaries, notify=boardChanged)

    def _get_selected_lesson(self) -> dict[str, object]:
        return self._selected_lesson

    selectedLesson = Property(object, _get_selected_lesson, notify=selectionChanged)

    def _get_drop_preview(self) -> dict[str, object]:
        return self._drop_preview

    dropPreview = Property(object, _get_drop_preview, notify=previewChanged)

    def _get_history_rows(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        return [_history_dict(row) for row in board.audit_logs]

    historyRows = Property(list, _get_history_rows, notify=boardChanged)

    def _get_diff_rows(self) -> list[dict[str, object]]:
        board = self._board
        if board is None:
            return []
        return [_diff_dict(row) for row in board.diff]

    diffRows = Property(list, _get_diff_rows, notify=boardChanged)

    def _get_reoptimization_summary(self) -> dict[str, object]:
        return self._reoptimization_summary

    reoptimizationSummary = Property(
        object,
        _get_reoptimization_summary,
        notify=boardChanged,
    )

    def _get_can_undo(self) -> bool:
        return self._board is not None and self._board.can_undo

    canUndo = Property(bool, _get_can_undo, notify=boardChanged)

    def _get_can_redo(self) -> bool:
        return self._board is not None and self._board.can_redo

    canRedo = Property(bool, _get_can_redo, notify=boardChanged)

    def _get_has_unsaved_changes(self) -> bool:
        return (
            self._is_saving
            or self._draft_editing
            or self._pending_edit is not None
            or self._save_failed
        )

    hasUnsavedChanges = Property(
        bool,
        _get_has_unsaved_changes,
        notify=saveStateChanged,
    )

    def _get_save_state_text(self) -> str:
        if self._is_saving:
            return "… 保存処理中"
        if self._pending_edit is not None:
            return "△ 確認待ち・未保存"
        if self._draft_editing:
            return "● 編集中・未保存"
        if self._save_failed:
            return "⚠ 保存失敗・未反映"
        return "✓ 自動保存済み"

    saveStateText = Property(str, _get_save_state_text, notify=saveStateChanged)

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=messageChanged)

    def _get_error_message(self) -> str:
        return self._error_message

    errorMessage = Property(str, _get_error_message, notify=messageChanged)

    # Navigation / filter actions

    @Slot()
    def refreshSchedule(self) -> None:
        if self._projects.current is None:
            self._board = None
            self._current_date = None
            self._selected_key = None
            self._selected_lesson = {}
            self._is_saving = False
            self._draft_editing = False
            self._save_failed = False
            self._pending_edit = None
            self._replace_grid()
            self.projectStateChanged.emit()
            self.boardChanged.emit()
            self.navigationChanged.emit()
            self.saveStateChanged.emit()
            return
        try:
            board = self._service.load_board()
        except Exception as exc:
            self._log_unexpected("時間割の読込み", exc)
            self._set_error("時間割を読み込めませんでした。ローカルログを確認してください")
            return
        self._apply_board(board, preserve_date=True)

    @Slot()
    def refreshProjectState(self) -> None:
        self.refreshSchedule()

    @Slot()
    def previousDate(self) -> None:
        self._move_date(-1)

    @Slot()
    def nextDate(self) -> None:
        self._move_date(1)

    @Slot(str, result=bool)
    def selectDate(self, value: str) -> bool:
        try:
            selected = date.fromisoformat(value)
        except ValueError:
            self._set_error("日付はyyyy-MM-dd形式で選択してください")
            return False
        board = self._board
        if board is None or selected not in {row.day for row in board.dates}:
            self._set_error("講習期間内の日付を選択してください")
            return False
        if selected == self._current_date:
            return True
        self._current_date = selected
        self._replace_grid()
        self._clear_messages()
        self.navigationChanged.emit()
        return True

    @Slot(str)
    def setViewMode(self, value: str) -> None:
        if value not in {"day", "multiple"}:
            self._set_error("表示は日表示または複数日サマリーを選択してください")
            return
        if value == self._view_mode:
            return
        self._view_mode = value
        self.navigationChanged.emit()

    @Slot(float)
    def setZoomFactor(self, value: float) -> None:
        normalized = min(1.5, max(0.75, round(value / 0.05) * 0.05))
        if abs(self._zoom_factor - normalized) < 0.001:
            return
        self._zoom_factor = normalized
        self.navigationChanged.emit()

    @Slot(str)
    def setSearchQuery(self, value: str) -> None:
        normalized = value.strip().casefold()
        if normalized == self._search_query:
            return
        self._search_query = normalized
        self._filters_changed()

    @Slot(str)
    def setGradeFilter(self, value: str) -> None:
        if value == self._grade_filter:
            return
        self._grade_filter = value
        self._filters_changed()

    @Slot(str)
    def setSubjectFilter(self, value: str) -> None:
        if value == self._subject_filter:
            return
        self._subject_filter = value
        self._filters_changed()

    @Slot(str, bool)
    def setFlagFilter(self, name: str, enabled: bool) -> None:
        if name not in self._flag_filters:
            self._set_error("時間割の絞込み条件が不正です")
            return
        if self._flag_filters[name] == enabled:
            return
        self._flag_filters[name] = enabled
        self._filters_changed()

    # Selection / edit actions

    @Slot(int, int, result=bool)
    def selectLesson(self, lesson_request_id: int, session_index: int) -> bool:
        board = self._board
        if board is None:
            return False
        key = (lesson_request_id, session_index)
        for card in board.cards:
            if (card.lesson_request_id, card.session_index) == key:
                self._selected_key = key
                self._selected_lesson = self._card_dict(card)
                self.selectionChanged.emit()
                return True
        for row in board.unassigned:
            if (row.lesson_request_id, row.session_index) == key:
                self._selected_key = key
                self._selected_lesson = self._unassigned_dict(row)
                self.selectionChanged.emit()
                return True
        self._set_error("選択した授業は現在の時間割にありません")
        return False

    @Slot(int, int, str, int, int, result=str)
    def previewMove(
        self,
        lesson_request_id: int,
        session_index: int,
        day_value: str,
        time_slot_id: int,
        teacher_id: int,
    ) -> str:
        target = self._move_target(
            "move",
            lesson_request_id,
            session_index,
            day_value,
            time_slot_id,
            teacher_id,
        )
        if target is None:
            return "red"
        preview = self._preview(target)
        return preview.decision if preview is not None else "red"

    @Slot(int, int, str, int, int, str, result=bool)
    def createPreconfirmedAssignment(
        self,
        lesson_request_id: int,
        session_index: int,
        day_value: str,
        time_slot_id: int,
        teacher_id: int,
        note: str,
    ) -> bool:
        """未配置の受講1回を、検証済みロック枠として即時保存する。"""
        target = self._move_target(
            "preconfirm",
            lesson_request_id,
            session_index,
            day_value,
            time_slot_id,
            teacher_id,
        )
        if target is None or target.day is None:
            return False
        self._begin_save()
        try:
            self._service.create_preconfirmed_assignment(
                lesson_request_id=lesson_request_id,
                session_index=session_index,
                day=target.day,
                time_slot_id=time_slot_id,
                teacher_id=teacher_id,
                note=note,
            )
        except Exception as exc:
            return self._action_failed("事前確定枠の登録", exc)
        return self._action_succeeded("事前確定枠を登録し、再最適化で動かないようロックしました")

    @Slot(int, int, str, int, int, result=str)
    def dropMove(
        self,
        lesson_request_id: int,
        session_index: int,
        day_value: str,
        time_slot_id: int,
        teacher_id: int,
    ) -> str:
        target = self._move_target(
            "move",
            lesson_request_id,
            session_index,
            day_value,
            time_slot_id,
            teacher_id,
        )
        if target is None:
            return "red"
        preview = self._preview(target)
        if preview is None or preview.decision == "red":
            return "red"
        if preview.decision == "yellow":
            self._set_pending_edit(target)
            return "yellow"
        if self._apply_pending(target, "ドラッグ＆ドロップで移動", confirm=False):
            return "green"
        return "red"

    @Slot()
    def clearDropPreview(self) -> None:
        if self._pending_edit is not None:
            return
        self._set_preview(None, target=None)

    @Slot(str, result=bool)
    def confirmPendingMove(self, reason: str) -> bool:
        pending = self._pending_edit
        if pending is None:
            self._set_error("確認対象の変更がありません")
            return False
        return self._apply_pending(
            pending,
            reason.strip() or "ソフト条件を確認して変更",
            confirm=True,
        )

    @Slot()
    def cancelPendingMove(self) -> None:
        self._set_pending_edit(None)
        self._set_preview(None, target=None)
        self._set_status("変更を取り消しました")

    @Slot(bool)
    def setDraftEditing(self, editing: bool) -> None:
        if self._draft_editing == editing:
            return
        self._draft_editing = editing
        self.saveStateChanged.emit()

    @Slot(result=bool)
    def toggleSelectedLock(self) -> bool:
        selected = self._selected_lesson
        key = self._selected_key
        if key is None or not selected or not selected.get("assignmentId"):
            self._set_error("配置済みの授業を選択してください")
            return False
        desired = not bool(selected.get("isLocked", False))
        self._begin_save()
        try:
            self._service.set_lock(
                lesson_request_id=key[0],
                session_index=key[1],
                is_locked=desired,
                reason="時間割編集画面から明示操作",
            )
        except Exception as exc:
            return self._action_failed("ロック変更", exc)
        return self._action_succeeded("授業のロックを変更しました")

    @Slot(str, result=str)
    def unassignSelected(self, reason: str) -> str:
        selected = self._selected_lesson
        key = self._selected_key
        if key is None or not selected or not selected.get("assignmentId"):
            self._set_error("配置済みの授業を選択してください")
            return "red"
        if bool(selected.get("isLocked", False)):
            self._set_error("ロック済み授業は、先に明示的にロック解除してください")
            return "red"
        pending = _PendingEdit(
            kind="unassign",
            lesson_request_id=key[0],
            session_index=key[1],
            day=None,
            time_slot_id=0,
            teacher_id=0,
        )
        try:
            preview = self._service.preview_unassign(
                lesson_request_id=key[0],
                session_index=key[1],
            )
        except Exception as exc:
            self._action_failed("未配置前検証", exc, reload_board=False)
            return "red"
        self._set_preview(preview, target=pending)
        if preview.decision == "red":
            self._set_error(self._drop_preview["message"].__str__())
            return "red"
        if preview.decision == "yellow":
            self._set_pending_edit(pending)
            return "yellow"
        if self._apply_pending(
            pending,
            reason.strip() or "時間割編集画面から未配置へ移動",
            confirm=False,
        ):
            return "green"
        return "red"

    @Slot(str, int, int, bool, str, str, result=str)
    def editSelected(
        self,
        day_value: str,
        time_slot_id: int,
        teacher_id: int,
        is_locked: bool,
        note: str,
        reason: str,
    ) -> str:
        key = self._selected_key
        selected = self._selected_lesson
        if key is None or not selected or not selected.get("assignmentId"):
            self._set_error("配置済みの授業を選択してください")
            return "red"
        target = self._move_target(
            "edit",
            key[0],
            key[1],
            day_value,
            time_slot_id,
            teacher_id,
            is_locked=is_locked,
            note=note,
        )
        if target is None:
            return "red"
        location_changed = (
            day_value != str(selected.get("date", ""))
            or time_slot_id != _dictionary_int(selected, "timeSlotId")
            or teacher_id != _dictionary_int(selected, "teacherId")
        )
        if bool(selected.get("isLocked", False)) and location_changed:
            self._set_error("ロック済み授業は、先に明示的にロック解除してください")
            return "red"
        if not location_changed:
            if self._apply_pending(
                target,
                reason.strip() or "詳細編集ダイアログから変更",
                confirm=False,
            ):
                return "green"
            return "red"
        preview = self._preview(target)
        if preview is None or preview.decision == "red":
            return "red"
        if preview.decision == "yellow":
            self._set_pending_edit(target)
            return "yellow"
        if self._apply_pending(
            target,
            reason.strip() or "詳細編集ダイアログから変更",
            confirm=False,
        ):
            return "green"
        return "red"

    @Slot(result=bool)
    def undo(self) -> bool:
        if not self._get_can_undo():
            self._set_error("元に戻せる操作はありません")
            return False
        self._begin_save()
        try:
            self._service.undo()
        except Exception as exc:
            return self._action_failed("Undo", exc)
        return self._action_succeeded("直前の操作を元に戻しました")

    @Slot(result=bool)
    def redo(self) -> bool:
        if not self._get_can_redo():
            self._set_error("やり直せる操作はありません")
            return False
        self._begin_save()
        try:
            self._service.redo()
        except Exception as exc:
            return self._action_failed("Redo", exc)
        return self._action_succeeded("取り消した操作をやり直しました")

    @Slot(result=bool)
    def manualSave(self) -> bool:
        """即時保存済みDBを再読込みし、SQLite backupの明示保存点を作る。"""
        if self._projects.current is None:
            self._set_error("先にプロジェクトを開いてください")
            return False
        self._begin_save()
        try:
            backup = self._service.create_manual_backup()
            board = self._service.load_board()
        except Exception as exc:
            return self._action_failed("手動保存", exc, reload_board=False)
        self._apply_board(board, preserve_date=True)
        self._set_status(
            f"手動保存点を作成しました: {backup.path}。"
            "バックアップには個人情報が含まれる可能性があります"
        )
        return True

    @Slot(result=bool)
    def prepareReoptimization(self) -> bool:
        try:
            summary = self._service.reoptimization_summary()
        except Exception as exc:
            return self._action_failed("再最適化の事前確認", exc, reload_board=False)
        self._reoptimization_summary = _reoptimization_dict(summary)
        self.boardChanged.emit()
        self._clear_messages()
        return True

    @Slot(result=bool)
    def createReoptimizationCheckpoint(self) -> bool:
        self._begin_save()
        try:
            backup = self._service.create_checkpoint_backup()
        except Exception as exc:
            return self._action_failed("再最適化前バックアップ", exc, reload_board=False)
        self._finish_save()
        self._set_status(
            f"再最適化前バックアップを作成しました: {backup.path}。"
            "バックアップには個人情報が含まれる可能性があります"
        )
        return True

    @Slot()
    def clearMessages(self) -> None:
        self._clear_messages()

    # Internal conversion and service helpers

    def _apply_board(self, board: ScheduleBoardDto, *, preserve_date: bool) -> None:
        previous_date = self._current_date if preserve_date else None
        self._board = board
        available_dates = [row.day for row in board.dates]
        self._current_date = (
            previous_date
            if previous_date is not None and previous_date in available_dates
            else (available_dates[0] if available_dates else None)
        )
        self._is_saving = False
        self._save_failed = False
        self._pending_edit = None
        self._set_preview(None, target=None)
        self._replace_grid()
        self._refresh_selection()
        self.projectStateChanged.emit()
        self.boardChanged.emit()
        self.navigationChanged.emit()
        self.filterChanged.emit()
        self.saveStateChanged.emit()

    def _replace_grid(self) -> None:
        board = self._board
        current_date = self._current_date
        if board is None or current_date is None:
            self._grid_model.replace(cells=[], teacher_labels=[], slot_labels=[])
            return
        teachers = list(board.teachers)
        slots = list(board.slots)
        cards = {(card.lesson_request_id, card.session_index): card for card in board.cards}
        groups = {group.id: group for group in board.group_blocks}
        cells = {(cell.day, cell.time_slot_id, cell.teacher_id): cell for cell in board.cells}
        rows: list[list[dict[str, object]]] = []
        for slot in slots:
            row: list[dict[str, object]] = []
            for teacher in teachers:
                source = cells.get((current_date, slot.id, teacher.id))
                card_rows = (
                    [
                        self._card_dict(cards[key])
                        for key in (
                            (item.lesson_request_id, item.session_index)
                            for item in source.assignment_keys
                        )
                        if key in cards
                    ]
                    if source is not None
                    else []
                )
                group_rows = (
                    [
                        _group_dict(groups[group_id])
                        for group_id in source.group_lesson_ids
                        if group_id in groups
                    ]
                    if source is not None
                    else []
                )
                row.append(
                    {
                        "cellKey": _cell_key(current_date, slot.id, teacher.id),
                        "date": current_date.isoformat(),
                        "timeSlotId": slot.id,
                        "timeSlotCode": slot.code,
                        "teacherId": teacher.id,
                        "teacherName": teacher.name,
                        "lessonCards": card_rows,
                        "groupLessons": group_rows,
                    }
                )
            rows.append(row)
        self._grid_model.replace(
            cells=rows,
            teacher_labels=[teacher.name for teacher in teachers],
            slot_labels=[slot.display_name for slot in slots],
        )

    def _card_dict(self, card: ScheduleCardDto) -> dict[str, object]:
        board = self._board
        teacher_name = ""
        slot_label = ""
        if board is not None:
            teacher_name = next(
                (row.name for row in board.teachers if row.id == card.teacher_id),
                "",
            )
            slot_label = next(
                (row.display_name for row in board.slots if row.id == card.time_slot_id),
                "",
            )
        warning_messages = list(card.warning_messages)
        history = list(card.change_history)
        detail_lines = [
            f"{card.student_name}（{card.grade}） / {card.subject_name}",
            f"第{card.session_index}回 / {card.day.isoformat()} {slot_label} / {teacher_name}",
        ]
        if warning_messages:
            detail_lines.append("警告: " + " / ".join(warning_messages))
        if history:
            detail_lines.append("変更履歴: " + " / ".join(history[:3]))
        return {
            "assignmentId": card.assignment_id,
            "lessonRequestId": card.lesson_request_id,
            "sessionIndex": card.session_index,
            "studentId": card.student_id,
            "studentName": card.student_name,
            "grade": card.grade,
            "subjectId": card.subject_id,
            "subjectCode": card.subject_code,
            "subjectShortName": card.subject_code or card.subject_name,
            "subjectName": card.subject_name,
            "date": card.day.isoformat(),
            "timeSlotId": card.time_slot_id,
            "teacherId": card.teacher_id,
            "teacherName": teacher_name,
            "oneToOneRequired": card.one_to_one_required,
            "isPriorityFive": card.priority_five,
            "isLocked": card.is_locked,
            "isManual": card.is_manual,
            "note": card.note,
            "hasWarning": card.warning_count > 0 or bool(warning_messages),
            "warningCount": max(card.warning_count, len(warning_messages)),
            "warningMessages": warning_messages,
            "regularTeacherName": card.regular_teacher_name or "―",
            "preferredTeacherText": "、".join(card.preferred_teacher_names) or "―",
            "availabilityText": card.availability_text or "―",
            "consecutiveText": card.consecutive_text or "―",
            "gapText": card.gap_text or "―",
            "changeHistory": history,
            "detailText": "\n".join(detail_lines),
            "matchesFilter": self._matches_card(card, teacher_name),
        }

    def _unassigned_dict(self, row: UnassignedSessionDto) -> dict[str, object]:
        return {
            "assignmentId": 0,
            "lessonRequestId": row.lesson_request_id,
            "sessionIndex": row.session_index,
            "studentId": row.student_id,
            "studentName": row.student_name,
            "grade": row.grade,
            "subjectId": row.subject_id,
            "subjectCode": row.subject_code,
            "subjectShortName": row.subject_code or row.subject_name,
            "subjectName": row.subject_name,
            "date": "",
            "timeSlotId": 0,
            "teacherId": 0,
            "oneToOneRequired": row.one_to_one_required,
            "isPriorityFive": row.priority_five,
            "isLocked": False,
            "isManual": False,
            "hasWarning": True,
            "remainingCount": row.remaining_count,
            "candidateCount": row.candidate_count,
            "reasonText": row.primary_reason,
            "detailText": (
                f"{row.student_name}（{row.grade}） / {row.subject_name}\n"
                f"第{row.session_index}回 / 未配置: {row.primary_reason}"
            ),
            "matchesFilter": self._matches_unassigned(row),
        }

    def _day_summary(
        self,
        day_value: date,
        cards: list[ScheduleCardDto],
        groups: list[GroupBlockDto],
    ) -> dict[str, object]:
        occupancy: dict[tuple[int, int], int] = {}
        for card in cards:
            key = (card.teacher_id, card.time_slot_id)
            occupancy[key] = occupancy.get(key, 0) + 1
        return {
            "date": day_value.isoformat(),
            "label": _date_label(day_value),
            "assignmentCount": len(cards),
            "pairedCellCount": sum(count == 2 for count in occupancy.values()),
            "groupLessonCount": len(groups),
            "warningCount": sum(
                max(card.warning_count, len(card.warning_messages)) for card in cards
            ),
            "lockCount": sum(card.is_locked for card in cards),
        }

    def _preview(self, target: _PendingEdit) -> EditPreviewDto | None:
        assert target.day is not None
        try:
            preview = self._service.preview_move(
                lesson_request_id=target.lesson_request_id,
                session_index=target.session_index,
                day=target.day,
                time_slot_id=target.time_slot_id,
                teacher_id=target.teacher_id,
            )
        except Exception as exc:
            self._action_failed("移動前検証", exc, reload_board=False)
            self._set_preview_error(target, "移動前検証を完了できませんでした")
            return None
        self._set_preview(preview, target=target)
        if preview.decision == "red":
            self._set_error(self._drop_preview["message"].__str__())
        else:
            self._clear_messages()
        return preview

    def _set_preview(
        self,
        preview: EditPreviewDto | None,
        *,
        target: _PendingEdit | None,
    ) -> None:
        if preview is None:
            self._drop_preview = dict(_EMPTY_PREVIEW)
        else:
            if preview.hard_issues:
                message = " / ".join(preview.hard_issues)
            elif preview.soft_warnings:
                message = " / ".join(preview.soft_warnings)
            else:
                message = "配置可能です"
            self._drop_preview = {
                "decision": preview.decision,
                "code": preview.preview_code,
                "icon": _DECISION_ICON[preview.decision],
                "message": message,
                "targetKey": (
                    ""
                    if target is None
                    else (
                        ""
                        if target.day is None
                        else _cell_key(target.day, target.time_slot_id, target.teacher_id)
                    )
                ),
                "hardIssues": list(preview.hard_issues),
                "hardIssueCodes": list(preview.hard_issue_codes),
                "softDeltas": [
                    {
                        "code": delta.code,
                        "label": delta.label,
                        "direction": delta.direction,
                        "before": delta.before_value,
                        "after": delta.after_value,
                        "worsened": delta.worsened,
                        "message": delta.message,
                    }
                    for delta in preview.soft_deltas
                ],
                "beforeSummary": preview.before_summary,
                "afterSummary": preview.after_summary,
            }
        self.previewChanged.emit()

    def _set_preview_error(self, target: _PendingEdit, message: str) -> None:
        self._drop_preview = {
            "decision": "red",
            "code": "ui_validation_error",
            "icon": _DECISION_ICON["red"],
            "message": message,
            "targetKey": (
                ""
                if target.day is None
                else _cell_key(target.day, target.time_slot_id, target.teacher_id)
            ),
            "hardIssues": [message],
            "hardIssueCodes": ["ui_validation_error"],
            "softDeltas": [],
            "beforeSummary": "",
            "afterSummary": "",
        }
        self.previewChanged.emit()

    def _apply_pending(
        self,
        pending: _PendingEdit,
        reason: str,
        *,
        confirm: bool,
    ) -> bool:
        self._begin_save()
        try:
            if pending.kind == "unassign":
                self._service.unassign(
                    lesson_request_id=pending.lesson_request_id,
                    session_index=pending.session_index,
                    reason=reason,
                    confirm_soft_warnings=confirm,
                )
            elif pending.kind == "edit":
                assert pending.day is not None
                assert pending.is_locked is not None
                assert pending.note is not None
                self._service.edit_assignment(
                    lesson_request_id=pending.lesson_request_id,
                    session_index=pending.session_index,
                    day=pending.day,
                    time_slot_id=pending.time_slot_id,
                    teacher_id=pending.teacher_id,
                    is_locked=pending.is_locked,
                    note=pending.note,
                    reason=reason,
                    confirm_soft_warnings=confirm,
                )
            else:
                assert pending.day is not None
                self._service.apply_move(
                    lesson_request_id=pending.lesson_request_id,
                    session_index=pending.session_index,
                    day=pending.day,
                    time_slot_id=pending.time_slot_id,
                    teacher_id=pending.teacher_id,
                    reason=reason,
                    confirm_soft_warnings=confirm,
                )
        except Exception as exc:
            return self._action_failed("時間割変更", exc)
        return self._action_succeeded("時間割を変更し、自動保存しました")

    def _move_target(
        self,
        kind: str,
        lesson_request_id: int,
        session_index: int,
        day_value: str,
        time_slot_id: int,
        teacher_id: int,
        *,
        is_locked: bool | None = None,
        note: str | None = None,
    ) -> _PendingEdit | None:
        if lesson_request_id <= 0 or session_index <= 0:
            self._set_error("移動する授業が不正です")
            return None
        try:
            target_day = date.fromisoformat(day_value)
        except ValueError:
            self._set_error("移動先の日付が不正です")
            return None
        if time_slot_id <= 0 or teacher_id <= 0:
            self._set_error("移動先のコマまたは講師が不正です")
            return None
        return _PendingEdit(
            kind=kind,
            lesson_request_id=lesson_request_id,
            session_index=session_index,
            day=target_day,
            time_slot_id=time_slot_id,
            teacher_id=teacher_id,
            is_locked=is_locked,
            note=note,
        )

    def _action_succeeded(self, message: str) -> bool:
        try:
            board = self._service.load_board()
        except Exception as exc:
            return self._action_failed("変更後の再読込み", exc, reload_board=False)
        self._apply_board(board, preserve_date=True)
        self._set_status(message)
        self.scheduleSaved.emit()
        return True

    def _action_failed(
        self,
        operation: str,
        exc: Exception,
        *,
        reload_board: bool = True,
    ) -> bool:
        save_was_running = self._is_saving
        self._log_unexpected(operation, exc)
        if reload_board and self._projects.current is not None:
            try:
                self._apply_board(self._service.load_board(), preserve_date=True)
            except Exception as reload_exc:
                self._log_unexpected("失敗後の時間割再読込み", reload_exc)
        self._is_saving = False
        if save_was_running:
            self._save_failed = True
        self.saveStateChanged.emit()
        message = str(exc).strip()
        self._set_error(message or f"{operation}を完了できませんでした")
        return False

    def _begin_save(self) -> None:
        self._is_saving = True
        self._save_failed = False
        self.saveStateChanged.emit()

    def _finish_save(self) -> None:
        self._is_saving = False
        self._save_failed = False
        self.saveStateChanged.emit()

    def _set_pending_edit(self, value: _PendingEdit | None) -> None:
        if self._pending_edit == value:
            return
        self._pending_edit = value
        self.saveStateChanged.emit()

    def _refresh_selection(self) -> None:
        if self._selected_key is None:
            self._selected_lesson = {}
            self.selectionChanged.emit()
            return
        key = self._selected_key
        board = self._board
        if board is not None:
            for card in board.cards:
                if (card.lesson_request_id, card.session_index) == key:
                    self._selected_lesson = self._card_dict(card)
                    self.selectionChanged.emit()
                    return
            for row in board.unassigned:
                if (row.lesson_request_id, row.session_index) == key:
                    self._selected_lesson = self._unassigned_dict(row)
                    self.selectionChanged.emit()
                    return
        self._selected_key = None
        self._selected_lesson = {}
        self.selectionChanged.emit()

    def _move_date(self, delta: int) -> None:
        board = self._board
        index = self._date_index()
        if board is None or index < 0:
            return
        target = index + delta
        if target < 0 or target >= len(board.dates):
            return
        self._current_date = board.dates[target].day
        self._replace_grid()
        self._clear_messages()
        self.navigationChanged.emit()

    def _date_index(self) -> int:
        board = self._board
        if board is None or self._current_date is None:
            return -1
        return next(
            (index for index, row in enumerate(board.dates) if row.day == self._current_date),
            -1,
        )

    def _filters_changed(self) -> None:
        self._replace_grid()
        self._refresh_selection()
        self.filterChanged.emit()

    def _matches_card(self, card: ScheduleCardDto, teacher_name: str) -> bool:
        if self._search_query and self._search_query not in (
            f"{card.student_name} {teacher_name}".casefold()
        ):
            return False
        if self._grade_filter and card.grade != self._grade_filter:
            return False
        if self._subject_filter and card.subject_code != self._subject_filter:
            return False
        if self._flag_filters["oneToOne"] and not card.one_to_one_required:
            return False
        if self._flag_filters["priority5"] and not card.priority_five:
            return False
        if self._flag_filters["unassigned"]:
            return False
        if self._flag_filters["warning"] and card.warning_count == 0 and not card.warning_messages:
            return False
        return not self._flag_filters["locked"] or card.is_locked

    def _matches_unassigned(self, row: UnassignedSessionDto) -> bool:
        if self._search_query and self._search_query not in row.student_name.casefold():
            return False
        if self._grade_filter and row.grade != self._grade_filter:
            return False
        if self._subject_filter and row.subject_code != self._subject_filter:
            return False
        if self._flag_filters["oneToOne"] and not row.one_to_one_required:
            return False
        if self._flag_filters["priority5"] and not row.priority_five:
            return False
        if self._flag_filters["locked"]:
            return False
        return True

    def _clear_messages(self) -> None:
        if not self._status_message and not self._error_message:
            return
        self._status_message = ""
        self._error_message = ""
        self.messageChanged.emit()

    def _set_status(self, message: str) -> None:
        self._status_message = message
        self._error_message = ""
        self.messageChanged.emit()

    def _set_error(self, message: str) -> None:
        self._status_message = ""
        self._error_message = message
        self.messageChanged.emit()

    @staticmethod
    def _log_unexpected(operation: str, exc: Exception) -> None:
        # 例外値には氏名・備考が含まれ得るため技術ログへは型名だけを残す。
        logger.warning(
            "Phase 5の%sを完了できませんでした（%s）",
            operation,
            type(exc).__name__,
        )


def _date_label(value: date) -> str:
    return f"{value:%m/%d}（{_WEEKDAYS[value.weekday()]}）"


def _dictionary_int(values: dict[str, object], key: str) -> int:
    value = values.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _cell_key(day_value: date, time_slot_id: int, teacher_id: int) -> str:
    return f"{day_value.isoformat()}|{time_slot_id}|{teacher_id}"


def _group_dict(group: GroupBlockDto) -> dict[str, object]:
    return {
        "id": group.id,
        "groupCode": group.group_code,
        "courseName": group.course_name or group.group_code,
        "grade": group.grade,
        "subjectName": group.subject_name,
        "date": group.day.isoformat(),
        "startTime": group.start_time.strftime("%H:%M"),
        "endTime": group.end_time.strftime("%H:%M"),
        "teacherId": group.teacher_id or 0,
    }


def _history_dict(row: AuditLogDto) -> dict[str, object]:
    before_summary = _assignment_snapshot_summary(row.before_json)
    after_summary = _assignment_snapshot_summary(row.after_json)
    return {
        "id": row.id,
        "timestamp": row.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "action": row.action,
        "actionLabel": _ACTION_LABELS.get(row.action, row.action),
        "entityType": row.entity_type,
        "entityId": row.entity_id,
        "beforeSummary": before_summary,
        "afterSummary": after_summary,
        "summary": f"{before_summary} → {after_summary}",
        "reason": row.reason,
        "source": row.source,
        "operationId": row.operation_id or "",
    }


def _assignment_snapshot_summary(payload: str | None) -> str:
    """Assignment snapshotを個人情報本文なしの業務要約へ変換する。"""
    if payload is None:
        return "未配置"
    try:
        document: object = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return "変更内容を要約できません"
    if not isinstance(document, dict):
        return "変更内容を要約できません"
    values = cast(dict[str, object], document)
    day_value = values.get("day", values.get("date"))
    time_slot_id = values.get("time_slot_id")
    teacher_id = values.get("teacher_id")
    is_locked = values.get("is_locked")
    if (
        not isinstance(day_value, str)
        or not _is_iso_date(day_value)
        or not _is_identifier(time_slot_id)
        or not _is_identifier(teacher_id)
        or not isinstance(is_locked, bool)
    ):
        return "変更内容を要約できません"
    note = values.get("note")
    note_label = "備考あり" if isinstance(note, str) and note.strip() else "備考なし"
    lock_label = "ロック済み" if is_locked else "ロックなし"
    return (
        f"{day_value} / コマID {time_slot_id} / 講師ID {teacher_id} / {lock_label} / {note_label}"
    )


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_identifier(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _diff_dict(row: ScheduleDiffDto) -> dict[str, object]:
    codes = row.change_codes or tuple(value for value in row.change_type.split("+") if value)
    labels = [_DIFF_LABELS.get(code, code) for code in codes]
    return {
        "lessonRequestId": row.lesson_request_id,
        "sessionIndex": row.session_index,
        "changeType": row.change_type,
        "changeCodes": list(codes),
        "changeTypeLabel": "・".join(labels) or row.change_type,
        "beforeSummary": row.before_summary,
        "afterSummary": row.after_summary,
        "beforePairingSize": row.before_pairing_size or 0,
        "afterPairingSize": row.after_pairing_size or 0,
        "summary": f"{row.before_summary or '未配置'} → {row.after_summary or '未配置'}",
    }


def _reoptimization_dict(row: ReoptimizationSummaryDto) -> dict[str, object]:
    return {
        "projectId": row.project_id,
        "assignmentCount": row.assignment_count,
        "lockCount": row.lock_count,
        "manualCount": row.manual_count,
        "unassignedCount": row.unassigned_count,
        "editableCount": max(0, row.assignment_count - row.lock_count),
        "fingerprint": row.fingerprint,
    }


__all__ = [
    "ScheduleEditServiceProtocol",
    "ScheduleEditorViewModel",
    "ScheduleGridModel",
]
