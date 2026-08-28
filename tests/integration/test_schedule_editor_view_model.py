"""ScheduleEditorViewModelのDTO変換・編集確認・仮想化境界テスト。"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from datetime import time as wall_time
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication

from summer_scheduler.application.phase5_dto import (
    AuditLogDto,
    CheckpointBackupDto,
    DropDecision,
    EditPreviewDto,
    EditResultDto,
    GroupBlockDto,
    ReoptimizationSummaryDto,
    ScheduleBoardDto,
    ScheduleCardDto,
    ScheduleCellDto,
    ScheduleDateDto,
    ScheduleDiffDto,
    ScheduleSlotDto,
    ScheduleTeacherDto,
    SessionKeyDto,
    SoftMetricDeltaDto,
    UnassignedSessionDto,
)
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.ui.viewmodels.schedule_editor_view_model import (
    ScheduleEditorViewModel,
    ScheduleEditServiceProtocol,
    ScheduleGridModel,
)

DAY = date(2026, 8, 3)


@pytest.fixture(scope="module")
def core_app(qt_gui_app: QCoreApplication) -> QCoreApplication:
    return qt_gui_app


def test_board_is_converted_to_virtualized_day_grid_and_details(
    core_app: QCoreApplication,
) -> None:
    del core_app
    service = _FakeScheduleEditService(_small_board())
    view_model = _view_model(service)
    grid = cast(ScheduleGridModel, view_model._get_grid_model())

    assert grid.rowCount() == 2
    assert grid.columnCount() == 2
    first = grid.data(grid.index(0, 0), ScheduleGridModel.CellDataRole)
    assert isinstance(first, dict)
    cards = first["lessonCards"]
    assert isinstance(cards, list)
    assert cards[0]["studentName"] == "架空 花子"
    assert cards[0]["oneToOneRequired"] is True
    assert cards[0]["isPriorityFive"] is True
    assert cards[0]["isLocked"] is False
    assert cards[0]["isManual"] is True
    assert cards[0]["hasWarning"] is True
    assert cards[0]["regularTeacherName"] == "架空講師A"
    assert cards[0]["preferredTeacherText"] == "架空講師A、架空講師B"
    assert "変更履歴" in cards[0]["detailText"]

    assert view_model._get_current_date() == DAY.isoformat()
    assert len(view_model._get_date_tabs()) == 2
    assert len(view_model._get_day_summaries()) == 2
    assert view_model._get_day_summaries()[0]["assignmentCount"] == 1
    assert view_model._get_unassigned_count() == 1
    assert view_model._get_unassigned_lessons()[0]["reasonText"] == "共通空き時間なし"
    history = view_model._get_history_rows()[0]
    assert history["reason"] == "架空理由"
    assert history["beforeSummary"] == (
        "2026-08-03 / コマID 100 / 講師ID 1 / ロックなし / 備考なし"
    )
    assert history["afterSummary"] == ("2026-08-04 / コマID 101 / 講師ID 2 / ロック済み / 備考あり")
    assert "個人名を含む備考" not in str(history)
    assert view_model._get_diff_rows()[0]["changeTypeLabel"] == "講師変更"


def test_date_navigation_multiple_summary_and_filters_keep_grid_shape(
    core_app: QCoreApplication,
) -> None:
    del core_app
    view_model = _view_model(_FakeScheduleEditService(_small_board()))
    grid = cast(ScheduleGridModel, view_model._get_grid_model())

    assert view_model._get_can_go_previous_date() is False
    assert view_model._get_can_go_next_date() is True
    view_model.nextDate()
    assert view_model._get_current_date() == (DAY + timedelta(days=1)).isoformat()
    assert view_model._get_can_go_previous_date() is True
    assert not view_model.selectDate("2030-01-01")
    assert "講習期間内" in view_model._get_error_message()
    assert view_model.selectDate(DAY.isoformat())

    view_model.setViewMode("multiple")
    assert view_model._get_view_mode() == "multiple"
    view_model.setZoomFactor(9.0)
    assert view_model._get_zoom_factor() == 1.5

    view_model.setSearchQuery("一致しない")
    first = grid.data(grid.index(0, 0), ScheduleGridModel.CellDataRole)
    assert isinstance(first, dict)
    cards = first["lessonCards"]
    assert isinstance(cards, list)
    assert cards[0]["matchesFilter"] is False
    assert grid.rowCount() == 2
    assert grid.columnCount() == 2

    view_model.setSearchQuery("架空 花子")
    view_model.setGradeFilter("中2")
    view_model.setSubjectFilter("JH_MATH")
    view_model.setFlagFilter("oneToOne", True)
    view_model.setFlagFilter("priority5", True)
    view_model.setFlagFilter("warning", True)
    first = grid.data(grid.index(0, 0), ScheduleGridModel.CellDataRole)
    assert isinstance(first, dict)
    filtered_cards = first["lessonCards"]
    assert isinstance(filtered_cards, list)
    assert filtered_cards[0]["matchesFilter"] is True

    view_model.setSearchQuery("")
    view_model.setGradeFilter("")
    view_model.setSubjectFilter("")
    view_model.setFlagFilter("oneToOne", False)
    view_model.setFlagFilter("priority5", False)
    view_model.setFlagFilter("warning", False)
    view_model.setFlagFilter("unassigned", True)
    first = grid.data(grid.index(0, 0), ScheduleGridModel.CellDataRole)
    assert isinstance(first, dict)
    unassigned_only_cards = first["lessonCards"]
    assert isinstance(unassigned_only_cards, list)
    assert unassigned_only_cards[0]["matchesFilter"] is False
    assert view_model._get_unassigned_lessons()[0]["matchesFilter"] is True


def test_drag_preview_rejects_red_confirms_yellow_and_applies_green(
    core_app: QCoreApplication,
) -> None:
    del core_app
    service = _FakeScheduleEditService(_small_board())
    view_model = _view_model(service)

    assert view_model.previewMove(10, 1, DAY.isoformat(), 100, 3) == "red"
    preview = view_model._get_drop_preview()
    assert preview["decision"] == "red"
    assert preview["code"] == "hard_rejected"
    assert preview["icon"] == "✕"
    assert preview["message"] == "講師科目資格がありません"
    assert preview["hardIssueCodes"] == ["teacher_not_qualified"]
    assert view_model.dropMove(10, 1, DAY.isoformat(), 100, 3) == "red"
    assert service.apply_calls == []

    assert view_model.dropMove(10, 1, DAY.isoformat(), 100, 2) == "yellow"
    preview = view_model._get_drop_preview()
    assert preview["icon"] == "△"
    deltas = preview["softDeltas"]
    assert isinstance(deltas, list)
    assert deltas[0] == {
        "code": "teacher_preference_penalty",
        "label": "講師希望違反",
        "direction": "minimize",
        "before": 0,
        "after": 4,
        "worsened": True,
        "message": "通常担当講師から外れます",
    }
    view_model.clearDropPreview()
    assert view_model._get_drop_preview()["decision"] == "yellow"
    assert view_model.confirmPendingMove("希望条件を確認")
    confirmed_apply = service.apply_calls[-1]
    assert confirmed_apply["confirm"] is True
    assert confirmed_apply["reason"] == "希望条件を確認"

    assert view_model.dropMove(10, 1, DAY.isoformat(), 100, 1) == "green"
    automatic_apply = service.apply_calls[-1]
    assert automatic_apply["confirm"] is False
    assert "自動保存" in view_model._get_status_message()


def test_preconfirmation_models_and_atomic_action_are_exposed(
    core_app: QCoreApplication,
) -> None:
    del core_app
    service = _FakeScheduleEditService(_small_board())
    view_model = _view_model(service)

    candidates = view_model._get_preconfirmation_candidates()
    assert candidates[0]["label"] == "架空 太郎／中学校・英語／第1回"
    assert view_model._get_preconfirmed_assignments() == []
    assert view_model.createPreconfirmedAssignment(
        11,
        1,
        DAY.isoformat(),
        100,
        1,
        "保護者と調整済み",
    )
    assert service.preconfirmation_calls == [
        {
            "lesson_request_id": 11,
            "session_index": 1,
            "day": DAY,
            "time_slot_id": 100,
            "teacher_id": 1,
            "note": "保護者と調整済み",
        }
    ]
    assert "ロックしました" in view_model._get_status_message()


def test_atomic_detail_lock_unassign_undo_redo_and_checkpoint(
    core_app: QCoreApplication,
) -> None:
    del core_app
    service = _FakeScheduleEditService(_small_board())
    view_model = _view_model(service)

    assert view_model.selectLesson(10, 1)
    preview_count = service.preview_calls
    assert (
        view_model.editSelected(
            DAY.isoformat(),
            100,
            1,
            False,
            "位置を変えない備考更新",
            "備考確認",
        )
        == "green"
    )
    assert service.preview_calls == preview_count
    assert service.edit_calls[-1]["note"] == "位置を変えない備考更新"

    assert view_model.toggleSelectedLock()
    locked_call = service.lock_calls[-1]
    assert locked_call["is_locked"] is True
    assert view_model.unassignSelected("ロック中") == "red"
    assert service.unassign_calls == []
    assert view_model.toggleSelectedLock()
    unlocked_call = service.lock_calls[-1]
    assert unlocked_call["is_locked"] is False

    assert (
        view_model.editSelected(
            DAY.isoformat(),
            100,
            2,
            False,
            "架空備考を更新",
            "詳細確認",
        )
        == "yellow"
    )
    assert view_model.confirmPendingMove("講師希望差を確認")
    assert service.edit_calls[-1]["confirm"] is True
    assert "架空備考を更新" in [str(call["note"]) for call in service.edit_calls]

    assert view_model.unassignSelected("未配置化を確認") == "yellow"
    assert service.unassign_calls == []
    assert view_model.confirmPendingMove("未配置数の増加を確認")
    assert service.unassign_calls == [{"reason": "未配置数の増加を確認", "confirm": True}]
    assert view_model.undo()
    assert service.undo_calls == 1
    assert view_model.redo()
    assert service.redo_calls == 1

    assert view_model.manualSave()
    assert service.manual_backup_calls == 1
    assert "架空手動保存点.backup" in view_model._get_status_message()
    assert "個人情報が含まれる可能性" in view_model._get_status_message()
    assert view_model.prepareReoptimization()
    summary = view_model._get_reoptimization_summary()
    assert summary["lockCount"] == 1
    assert summary["editableCount"] == 0
    assert view_model.createReoptimizationCheckpoint()
    assert service.checkpoint_calls == 1
    assert "個人情報が含まれる可能性" in view_model._get_status_message()


def test_draft_pending_saving_saved_and_failed_states_are_observable(
    core_app: QCoreApplication,
) -> None:
    del core_app
    service = _FakeScheduleEditService(_small_board())
    view_model = _view_model(service)
    observed: list[str] = []
    view_model.saveStateChanged.connect(lambda: observed.append(view_model._get_save_state_text()))

    assert view_model._get_has_unsaved_changes() is False
    assert view_model._get_save_state_text() == "✓ 自動保存済み"

    view_model.setDraftEditing(True)
    assert view_model._get_has_unsaved_changes() is True
    assert view_model._get_save_state_text() == "● 編集中・未保存"
    view_model.setDraftEditing(False)
    assert view_model._get_save_state_text() == "✓ 自動保存済み"

    assert view_model.dropMove(10, 1, DAY.isoformat(), 100, 2) == "yellow"
    assert view_model._get_has_unsaved_changes() is True
    assert view_model._get_save_state_text() == "△ 確認待ち・未保存"
    view_model.cancelPendingMove()
    assert view_model._get_has_unsaved_changes() is False

    observed.clear()
    assert view_model.dropMove(10, 1, DAY.isoformat(), 100, 1) == "green"
    assert "… 保存処理中" in observed
    assert view_model._get_save_state_text() == "✓ 自動保存済み"

    service.fail_next_apply = True
    assert view_model.dropMove(10, 1, DAY.isoformat(), 100, 1) == "red"
    assert view_model._get_has_unsaved_changes() is True
    assert view_model._get_save_state_text() == "⚠ 保存失敗・未反映"


def test_40_teachers_multiple_days_only_materialize_current_200_cells(
    core_app: QCoreApplication,
) -> None:
    del core_app
    board = _large_board(day_count=20, card_count=1000)
    service = _FakeScheduleEditService(board)

    started = time.perf_counter()
    view_model = _view_model(service)
    construction_seconds = time.perf_counter() - started
    grid = cast(ScheduleGridModel, view_model._get_grid_model())

    assert grid.rowCount() == 5
    assert grid.columnCount() == 40
    assert grid.rowCount() * grid.columnCount() == 200
    assert len(view_model._get_day_summaries()) == 20
    assert construction_seconds < 5.0

    started = time.perf_counter()
    for offset in range(20):
        assert view_model.selectDate((DAY + timedelta(days=offset)).isoformat())
        view_model.setSearchQuery("架空生徒" if offset % 2 else "")
        view_model.setFlagFilter("warning", offset % 2 == 0)
    interaction_seconds = time.perf_counter() - started

    assert grid.rowCount() == 5
    assert grid.columnCount() == 40
    assert interaction_seconds < 5.0


class _FakeProjects:
    def __init__(self) -> None:
        self.current: object | None = object()


class _FakeScheduleEditService:
    def __init__(self, board: ScheduleBoardDto) -> None:
        self.board = board
        self.apply_calls: list[dict[str, object]] = []
        self.edit_calls: list[dict[str, object]] = []
        self.preconfirmation_calls: list[dict[str, object]] = []
        self.lock_calls: list[dict[str, object]] = []
        self.unassign_calls: list[dict[str, object]] = []
        self.preview_calls = 0
        self.undo_calls = 0
        self.redo_calls = 0
        self.checkpoint_calls = 0
        self.manual_backup_calls = 0
        self.fail_next_apply = False

    def load_board(self) -> ScheduleBoardDto:
        return self.board

    def preview_move(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        day: date,
        time_slot_id: int,
        teacher_id: int,
    ) -> EditPreviewDto:
        del day, time_slot_id
        self.preview_calls += 1
        if teacher_id == 3:
            return _preview(
                lesson_request_id,
                session_index,
                decision="red",
                hard_issues=("講師科目資格がありません",),
            )
        if teacher_id == 2:
            return _preview(
                lesson_request_id,
                session_index,
                decision="yellow",
                soft_warnings=("通常担当講師から外れます",),
            )
        return _preview(lesson_request_id, session_index, decision="green")

    def preview_unassign(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
    ) -> EditPreviewDto:
        return _preview(
            lesson_request_id,
            session_index,
            decision="yellow",
            soft_warnings=("未配置数が1件増えます",),
        )

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
        del lesson_request_id, session_index, day, time_slot_id, teacher_id
        if self.fail_next_apply:
            self.fail_next_apply = False
            raise RuntimeError("架空の保存失敗")
        self.apply_calls.append({"reason": reason, "confirm": confirm_soft_warnings})
        self.board = replace(self.board, can_undo=True, can_redo=False)
        return _result()

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
        del lesson_request_id, session_index, day, time_slot_id, teacher_id, is_locked
        self.edit_calls.append(
            {
                "note": note,
                "reason": reason,
                "confirm": confirm_soft_warnings,
            }
        )
        self.board = replace(self.board, can_undo=True, can_redo=False)
        return _result()

    def create_preconfirmed_assignment(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        day: date,
        time_slot_id: int,
        teacher_id: int,
        note: str = "",
    ) -> EditResultDto:
        self.preconfirmation_calls.append(
            {
                "lesson_request_id": lesson_request_id,
                "session_index": session_index,
                "day": day,
                "time_slot_id": time_slot_id,
                "teacher_id": teacher_id,
                "note": note,
            }
        )
        self.board = replace(self.board, can_undo=True, can_redo=False)
        return _result()

    def unassign(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        reason: str,
        confirm_soft_warnings: bool = False,
    ) -> EditResultDto:
        del lesson_request_id, session_index
        self.unassign_calls.append({"reason": reason, "confirm": confirm_soft_warnings})
        self.board = replace(self.board, can_undo=True, can_redo=False)
        return _result()

    def set_lock(
        self,
        *,
        lesson_request_id: int,
        session_index: int,
        is_locked: bool,
        reason: str,
    ) -> EditResultDto:
        del lesson_request_id, session_index, reason
        self.lock_calls.append({"is_locked": is_locked})
        self.board = replace(
            self.board,
            cards=tuple(
                replace(card, is_locked=is_locked)
                if (card.lesson_request_id, card.session_index) == (10, 1)
                else card
                for card in self.board.cards
            ),
            lock_count=1 if is_locked else 0,
            can_undo=True,
            can_redo=False,
        )
        return _result()

    def undo(self) -> EditResultDto:
        self.undo_calls += 1
        self.board = replace(self.board, can_undo=False, can_redo=True)
        return _result()

    def redo(self) -> EditResultDto:
        self.redo_calls += 1
        self.board = replace(self.board, can_undo=True, can_redo=False)
        return _result()

    def reoptimization_summary(self) -> ReoptimizationSummaryDto:
        return ReoptimizationSummaryDto(
            project_id=1,
            assignment_count=1,
            lock_count=1,
            manual_count=1,
            unassigned_count=1,
            fingerprint=self.board.fingerprint,
        )

    def create_checkpoint_backup(self) -> CheckpointBackupDto:
        self.checkpoint_calls += 1
        return CheckpointBackupDto(
            path=Path("架空チェックポイント.backup"),
            lock_count=1,
            unassigned_count=1,
            fingerprint=self.board.fingerprint,
        )

    def create_manual_backup(self) -> CheckpointBackupDto:
        self.manual_backup_calls += 1
        return CheckpointBackupDto(
            path=Path("架空手動保存点.backup"),
            lock_count=1,
            unassigned_count=1,
            fingerprint=self.board.fingerprint,
        )


def _view_model(service: _FakeScheduleEditService) -> ScheduleEditorViewModel:
    return ScheduleEditorViewModel(
        cast(ScheduleEditServiceProtocol, service),
        cast(ProjectService, _FakeProjects()),
    )


def _preview(
    lesson_request_id: int,
    session_index: int,
    *,
    decision: DropDecision,
    hard_issues: tuple[str, ...] = (),
    soft_warnings: tuple[str, ...] = (),
) -> EditPreviewDto:
    soft_deltas = (
        (
            SoftMetricDeltaDto(
                code="teacher_preference_penalty",
                label="講師希望違反",
                direction="minimize",
                before_value=0,
                after_value=4,
                worsened=True,
                message=soft_warnings[0],
            ),
        )
        if soft_warnings
        else ()
    )
    return EditPreviewDto(
        action="move",
        lesson_request_id=lesson_request_id,
        session_index=session_index,
        allowed=decision != "red",
        decision=decision,
        preview_code=(
            "hard_rejected"
            if decision == "red"
            else ("soft_warning" if decision == "yellow" else "allowed")
        ),
        hard_issue_codes=(("teacher_not_qualified",) if hard_issues else ()),
        hard_issues=hard_issues,
        soft_warnings=soft_warnings,
        soft_deltas=soft_deltas,
        before_summary="2026-08-03 Y / 架空講師A",
        after_summary="2026-08-03 Y / 架空講師B",
        expected_fingerprint="fingerprint",
    )


def _result() -> EditResultDto:
    return EditResultDto(
        action="move",
        lesson_request_id=10,
        session_index=1,
        fingerprint="fingerprint",
        audit_log_id=1,
        can_undo=True,
        can_redo=False,
    )


def _small_board() -> ScheduleBoardDto:
    slots = _slots(2)
    teachers = _teachers(2)
    card = _card()
    group = GroupBlockDto(
        id=400,
        group_code="G-A",
        course_name="架空集団数学",
        grade="中2",
        subject_name="中学校・数学",
        day=DAY,
        start_time=wall_time(14, 10),
        end_time=wall_time(15, 30),
        teacher_id=2,
    )
    return ScheduleBoardDto(
        project_id=1,
        dates=(
            ScheduleDateDto(DAY, True, ""),
            ScheduleDateDto(DAY + timedelta(days=1), True, ""),
        ),
        slots=slots,
        teachers=teachers,
        cells=(
            ScheduleCellDto(
                day=DAY,
                time_slot_id=100,
                teacher_id=1,
                assignment_keys=(SessionKeyDto(10, 1),),
            ),
            ScheduleCellDto(
                day=DAY,
                time_slot_id=100,
                teacher_id=2,
                assignment_keys=(),
                group_lesson_ids=(400,),
            ),
        ),
        cards=(card,),
        group_blocks=(group,),
        unassigned=(
            UnassignedSessionDto(
                lesson_request_id=20,
                session_index=1,
                student_id=2,
                student_name="架空 太郎",
                grade="中1",
                subject_id=501,
                subject_code="JH_ENG",
                subject_name="中学校・英語",
                remaining_count=1,
                primary_reason="共通空き時間なし",
                candidate_count=0,
                priority_five=False,
                one_to_one_required=False,
            ),
        ),
        audit_logs=(
            AuditLogDto(
                id=1,
                timestamp=datetime(2026, 8, 1, 9, tzinfo=UTC),
                action="move",
                entity_type="AssignmentSession",
                entity_id="10:1",
                before_json=(
                    '{"day":"2026-08-03","is_locked":false,"note":null,'
                    '"teacher_id":1,"time_slot_id":100}'
                ),
                after_json=(
                    '{"day":"2026-08-04","is_locked":true,'
                    '"note":"個人名を含む備考","teacher_id":2,"time_slot_id":101}'
                ),
                reason="架空理由",
                source="manual",
                operation_id="op-1",
            ),
        ),
        diff=(
            ScheduleDiffDto(
                lesson_request_id=10,
                session_index=1,
                change_type="teacher",
                change_codes=("teacher",),
                before_summary="架空講師B",
                after_summary="架空講師A",
                before_pairing_size=1,
                after_pairing_size=2,
            ),
        ),
        lock_count=0,
        unassigned_count=1,
        fingerprint="fingerprint",
        can_undo=False,
        can_redo=False,
    )


def _large_board(*, day_count: int, card_count: int) -> ScheduleBoardDto:
    dates = tuple(
        ScheduleDateDto(DAY + timedelta(days=offset), True, "") for offset in range(day_count)
    )
    slots = _slots(5)
    teachers = _teachers(40)
    cells: list[ScheduleCellDto] = []
    cards: list[ScheduleCardDto] = []
    keys_by_cell: dict[tuple[date, int, int], list[SessionKeyDto]] = {}
    for index in range(card_count):
        day_value = dates[index % day_count].day
        slot = slots[(index // day_count) % len(slots)]
        teacher = teachers[(index // (day_count * len(slots))) % len(teachers)]
        lesson_request_id = 10_000 + index
        cards.append(
            replace(
                _card(),
                assignment_id=index + 1,
                lesson_request_id=lesson_request_id,
                student_id=index + 1,
                student_name=f"架空生徒{index:04d}",
                day=day_value,
                time_slot_id=slot.id,
                teacher_id=teacher.id,
                priority_five=index % 9 == 0,
                one_to_one_required=index % 7 == 0,
                warning_count=1 if index % 13 == 0 else 0,
                warning_messages=("架空警告",) if index % 13 == 0 else (),
            )
        )
        keys_by_cell.setdefault((day_value, slot.id, teacher.id), []).append(
            SessionKeyDto(lesson_request_id, 1)
        )
    for day_row in dates:
        for slot in slots:
            for teacher in teachers:
                cells.append(
                    ScheduleCellDto(
                        day=day_row.day,
                        time_slot_id=slot.id,
                        teacher_id=teacher.id,
                        assignment_keys=tuple(
                            keys_by_cell.get((day_row.day, slot.id, teacher.id), [])
                        ),
                    )
                )
    return ScheduleBoardDto(
        project_id=1,
        dates=dates,
        slots=slots,
        teachers=teachers,
        cells=tuple(cells),
        cards=tuple(cards),
        group_blocks=(),
        unassigned=(),
        audit_logs=(),
        diff=(),
        lock_count=0,
        unassigned_count=0,
        fingerprint="large-fingerprint",
        can_undo=False,
        can_redo=False,
    )


def _slots(count: int) -> tuple[ScheduleSlotDto, ...]:
    codes = ("Y", "Z", "A", "B", "C")
    return tuple(
        ScheduleSlotDto(
            id=100 + index,
            code=codes[index],
            display_name=f"{codes[index]}コマ",
            start_time=wall_time(14 + index, 10),
            end_time=wall_time(15 + index, 30),
            sort_order=index + 1,
            enabled=True,
        )
        for index in range(count)
    )


def _teachers(count: int) -> tuple[ScheduleTeacherDto, ...]:
    return tuple(
        ScheduleTeacherDto(
            id=index + 1,
            name=f"架空講師{index + 1:02d}",
            active=True,
        )
        for index in range(count)
    )


def _card() -> ScheduleCardDto:
    return ScheduleCardDto(
        assignment_id=1,
        lesson_request_id=10,
        session_index=1,
        student_id=1,
        student_name="架空 花子",
        grade="中2",
        subject_id=500,
        subject_code="JH_MATH",
        subject_name="中学校・数学",
        day=DAY,
        time_slot_id=100,
        teacher_id=1,
        one_to_one_required=True,
        priority_five=True,
        is_locked=False,
        is_manual=True,
        note="架空備考",
        regular_teacher_name="架空講師A",
        preferred_teacher_names=("架空講師A", "架空講師B"),
        availability_text="希望日時",
        consecutive_text="連続1コマ",
        gap_text="空きコマなし",
        warning_messages=("架空警告",),
        change_history=("2026-08-01 講師変更",),
        warning_count=1,
    )
