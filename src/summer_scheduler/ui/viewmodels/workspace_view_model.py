"""Phase 2のプロジェクト・マスター管理状態をQMLへ公開する。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import TypeVar

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from summer_scheduler.application.master_data_service import MasterDataService
from summer_scheduler.application.project_service import (
    ProjectFileError,
    ProjectService,
    ProjectSummary,
    RecoveryCandidate,
)
from summer_scheduler.application.shared_roster_service import SharedRosterService
from summer_scheduler.domain.defaults import SCHOOL_LEVEL_LABELS
from summer_scheduler.domain.validation import (
    DomainValidationError,
    parse_hhmm,
    parse_iso_date,
)
from summer_scheduler.infrastructure.excel import (
    ImportPreview,
    IssueSeverity,
    MasterDataExcelService,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class WorkspaceViewModel(QObject):
    """QML用の表示状態とPhase 2ユースケース呼出しをまとめる。

    QMLへ公開する値は辞書・基本型へ変換し、SQLAlchemyのSessionやORMモデルを
    画面へ渡さない。すべての永続化はアプリケーションサービスを経由する。
    """

    projectStateChanged = Signal()
    workflowProgressChanged = Signal()
    recentProjectsChanged = Signal()
    recoveryCandidatesChanged = Signal()
    studentsChanged = Signal()
    teachersChanged = Signal()
    subjectsChanged = Signal()
    timeSlotsChanged = Signal()
    openDatesChanged = Signal()
    lessonRequestsChanged = Signal()
    currentTeacherQualificationsChanged = Signal()
    excelPreviewChanged = Signal()
    messageChanged = Signal()
    dirtyChanged = Signal()

    def __init__(
        self,
        projects: ProjectService,
        master_data: MasterDataService,
        shared_roster: SharedRosterService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._projects = projects
        self._master_data = master_data
        self._shared_roster = shared_roster or SharedRosterService(projects)
        self._project_change_guard: Callable[[], None] | None = None
        self._status_message = ""
        self._error_message = ""
        self._dirty = False
        self._student_search = ""
        self._student_grade = ""
        self._teacher_search = ""
        self._selected_teacher_id: int | None = None
        self._students: list[dict[str, object]] = []
        self._teachers: list[dict[str, object]] = []
        self._subjects: list[dict[str, object]] = []
        self._time_slots: list[dict[str, object]] = []
        self._open_dates: list[dict[str, object]] = []
        self._lesson_requests: list[dict[str, object]] = []
        self._qualifications: list[dict[str, object]] = []
        self._recent_projects: list[dict[str, object]] = []
        self._workflow_completed_step = 0
        self._recovery_candidates: list[dict[str, object]] = []
        self._excel_preview: ImportPreview | None = None
        self._excel_preview_summary: dict[str, int] | None = None
        self._excel_issues: list[dict[str, object]] = []
        self._refresh_recent_projects()
        self._refresh_recovery_candidates()

    # Project and status properties

    def _get_has_open_project(self) -> bool:
        return self._projects.current is not None

    hasOpenProject = Property(
        bool,
        _get_has_open_project,
        notify=projectStateChanged,
    )

    def _get_current_project_title(self) -> str:
        current = self._projects.current
        return current.title if current is not None else ""

    currentProjectTitle = Property(
        str,
        _get_current_project_title,
        notify=projectStateChanged,
    )

    def _get_current_campus_name(self) -> str:
        current = self._projects.current
        return current.campus_name if current is not None else ""

    currentCampusName = Property(
        str,
        _get_current_campus_name,
        notify=projectStateChanged,
    )

    def _get_current_start_date(self) -> str:
        current = self._projects.current
        return current.start_date.isoformat() if current is not None else ""

    currentStartDate = Property(
        str,
        _get_current_start_date,
        notify=projectStateChanged,
    )

    def _get_current_end_date(self) -> str:
        current = self._projects.current
        return current.end_date.isoformat() if current is not None else ""

    currentEndDate = Property(
        str,
        _get_current_end_date,
        notify=projectStateChanged,
    )

    def _get_is_dirty(self) -> bool:
        return self._dirty

    isDirty = Property(bool, _get_is_dirty, notify=dirtyChanged)

    def _get_workflow_completed_step(self) -> int:
        return self._workflow_completed_step

    workflowCompletedStep = Property(
        int,
        _get_workflow_completed_step,
        notify=workflowProgressChanged,
    )

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=messageChanged)

    def _get_error_message(self) -> str:
        return self._error_message

    errorMessage = Property(str, _get_error_message, notify=messageChanged)

    # Collection properties

    def _get_recent_projects(self) -> list[dict[str, object]]:
        return self._recent_projects

    recentProjects = Property(
        list,
        _get_recent_projects,
        notify=recentProjectsChanged,
    )

    def _get_recovery_candidates(self) -> list[dict[str, object]]:
        return self._recovery_candidates

    recoveryCandidates = Property(
        list,
        _get_recovery_candidates,
        notify=recoveryCandidatesChanged,
    )

    def _get_recovery_target_path(self) -> str:
        target = self._projects.recovery_target_path
        if target is None and self._projects.current is not None:
            target = self._projects.current.path
        return str(target) if target is not None else ""

    recoveryTargetPath = Property(
        str,
        _get_recovery_target_path,
        notify=recoveryCandidatesChanged,
    )

    def _get_projects_directory_url(self) -> str:
        return QUrl.fromLocalFile(str(self._projects.projects_directory)).toString()

    projectsDirectoryUrl = Property(str, _get_projects_directory_url, constant=True)

    def _get_workspace_directory(self) -> str:
        return str(self._projects.workspace_directory)

    workspaceDirectory = Property(str, _get_workspace_directory, constant=True)

    def _get_shared_roster_path(self) -> str:
        return str(self._shared_roster.path)

    sharedRosterPath = Property(str, _get_shared_roster_path, constant=True)

    def _get_students(self) -> list[dict[str, object]]:
        return self._students

    students = Property(list, _get_students, notify=studentsChanged)

    def _get_teachers(self) -> list[dict[str, object]]:
        return self._teachers

    teachers = Property(list, _get_teachers, notify=teachersChanged)

    def _get_subjects(self) -> list[dict[str, object]]:
        return self._subjects

    subjects = Property(list, _get_subjects, notify=subjectsChanged)

    def _get_time_slots(self) -> list[dict[str, object]]:
        return self._time_slots

    timeSlots = Property(list, _get_time_slots, notify=timeSlotsChanged)

    def _get_open_dates(self) -> list[dict[str, object]]:
        return self._open_dates

    openDates = Property(list, _get_open_dates, notify=openDatesChanged)

    def _get_lesson_requests(self) -> list[dict[str, object]]:
        return self._lesson_requests

    lessonRequests = Property(
        list,
        _get_lesson_requests,
        notify=lessonRequestsChanged,
    )

    def _get_current_teacher_qualifications(self) -> list[dict[str, object]]:
        return self._qualifications

    currentTeacherQualifications = Property(
        list,
        _get_current_teacher_qualifications,
        notify=currentTeacherQualificationsChanged,
    )

    def _get_excel_preview_summary(self) -> dict[str, int] | None:
        return self._excel_preview_summary

    excelPreviewSummary = Property(
        object,
        _get_excel_preview_summary,
        notify=excelPreviewChanged,
    )

    def _get_excel_issues(self) -> list[dict[str, object]]:
        return self._excel_issues

    excelIssues = Property(
        list,
        _get_excel_issues,
        notify=excelPreviewChanged,
    )

    # Project lifecycle

    def ensure_project_switch_allowed(self) -> None:
        """別ViewModelからのプロジェクト切替にも未保存draftの保護を適用する。"""
        self._ensure_no_unsaved_draft()

    def set_project_change_guard(self, guard: Callable[[], None] | None) -> None:
        """最適化等の実行中にプロジェクト切替を防ぐ追加guardを設定する。"""
        self._project_change_guard = guard

    @Slot()
    def refreshProjectState(self) -> None:
        """共有ProjectServiceが外部ユースケースで切り替わった後に再同期する。"""
        if self._projects.current is None:
            self._set_dirty(False)
            self._workflow_completed_step = 0
            self.workflowProgressChanged.emit()
            self._clear_project_collections()
            self.projectStateChanged.emit()
            self._refresh_recent_projects()
            self._refresh_recovery_candidates()
            return
        self._after_project_opened()

    @Slot(str, str, str, str, str, result=bool)
    def createProject(
        self,
        path_value: str,
        title: str,
        campus_name: str,
        start_date_value: str,
        end_date_value: str,
    ) -> bool:
        """既定マスター付きの新規プロジェクトを作成して開く。"""

        def action() -> None:
            self._ensure_no_unsaved_draft()
            self._shared_roster.ensure_workbook()
            self._projects.create_project(
                _path_from_qml(path_value),
                title=title,
                campus_name=campus_name,
                start_date=parse_iso_date(start_date_value, "start_date"),
                end_date=parse_iso_date(end_date_value, "end_date"),
            )
            self._shared_roster.sync_to_current_project()
            self._after_project_opened()

        result = self._perform(action, "プロジェクトを作成しました")
        if result:
            self._show_safety_warning_if_any()
        return result

    @Slot(str, str, str, result=bool)
    def createProjectInWorkspace(
        self,
        title: str,
        start_date_value: str,
        end_date_value: str,
    ) -> bool:
        """保存先・校舎名を意識させず、既定のプロジェクト領域へ作成する。"""

        def action() -> None:
            self._ensure_no_unsaved_draft()
            self._shared_roster.ensure_workbook()
            self._projects.create_project_in_workspace(
                title=title,
                start_date=parse_iso_date(start_date_value, "start_date"),
                end_date=parse_iso_date(end_date_value, "end_date"),
            )
            self._shared_roster.sync_to_current_project()
            self._after_project_opened()

        result = self._perform(action, "プロジェクトを作成しました")
        if result:
            self._show_safety_warning_if_any()
        return result

    @Slot(str, result=bool)
    def openProject(self, path_value: str) -> bool:
        """ファイル選択結果を正規化して既存プロジェクトを開く。"""

        def action() -> None:
            self._ensure_no_unsaved_draft()
            self._projects.open_project(_path_from_qml(path_value))
            self._shared_roster.ensure_workbook()
            self._shared_roster.sync_to_current_project()
            self._after_project_opened()

        result = self._perform(action, "プロジェクトを開きました")
        self._refresh_recovery_candidates()
        if result:
            self._show_safety_warning_if_any()
        return result

    @Slot(str, result=bool)
    def openRecent(self, path_value: str) -> bool:
        """最近使用したプロジェクトを開く。"""
        return self.openProject(path_value)

    @Slot(str, result=bool)
    def hideRecent(self, path_value: str) -> bool:
        """プロジェクト本体を削除せず、最近使用した一覧だけから隠す。"""

        def action() -> None:
            self._projects.hide_recent_project(_path_from_qml(path_value))
            self._refresh_recent_projects()

        return self._perform(action, "最近使用した一覧から非表示にしました")

    @Slot(int)
    def markWorkflowStepComplete(self, step: int) -> None:
        if self._projects.current is None:
            return
        self._workflow_completed_step = self._projects.mark_workflow_step_complete(step)
        self.workflowProgressChanged.emit()

    @Slot(str, str, str, str, result=bool)
    def saveProjectInfo(
        self,
        title: str,
        campus_name: str,
        start_date_value: str,
        end_date_value: str,
    ) -> bool:
        """プロジェクト・校舎・講習期間を保存する。"""

        def action() -> None:
            self._master_data.update_project(
                title=title,
                campus_name=campus_name,
                start_date=parse_iso_date(start_date_value, "start_date"),
                end_date=parse_iso_date(end_date_value, "end_date"),
            )
            self._set_dirty(False)
            self._refresh_all_collections()
            self.projectStateChanged.emit()
            self._refresh_recent_projects()

        return self._perform(action, "プロジェクト情報を保存しました")

    @Slot(str, result=bool)
    def saveAs(self, path_value: str) -> bool:
        """現在のプロジェクトを別名へ保存して、そのファイルへ切り替える。"""

        def action() -> None:
            self._ensure_no_unsaved_draft()
            self._projects.save_as(_path_from_qml(path_value))
            self._after_project_opened()

        return self._perform(action, "名前を付けて保存しました")

    @Slot(str, result=bool)
    def duplicateProject(self, path_value: str) -> bool:
        """現在のプロジェクトを複製する。"""

        def action() -> None:
            self._ensure_no_unsaved_draft()
            self._projects.duplicate(_path_from_qml(path_value))

        return self._perform(action, "プロジェクトを複製しました")

    @Slot(str, result=bool)
    def backupProject(self, path_value: str) -> bool:
        """現在のプロジェクトを指定先へバックアップする。"""

        created: Path | None = None

        def action() -> None:
            nonlocal created
            self._ensure_no_unsaved_draft()
            created = self._projects.backup(_path_from_qml(path_value))

        result = self._perform(action, "バックアップを作成しました")
        if result and created is not None:
            self._set_status(
                f"バックアップを作成しました: {created}。"
                "バックアップにも生徒・講師などの個人情報が含まれます"
            )
        self._refresh_recovery_candidates()
        return result

    @Slot(result=bool)
    def createAutomaticBackup(self) -> bool:
        """一定間隔のtimerから現在のプロジェクトを世代管理backupへ保存する。"""
        if self._projects.current is None:
            return True
        try:
            created = self._projects.create_automatic_backup()
        except ProjectFileError as exc:
            logger.warning("自動バックアップを作成できませんでした")
            self._set_error(f"自動バックアップに失敗しました。{exc}")
            self._refresh_recovery_candidates()
            return False
        logger.info("自動バックアップを更新しました（file=%s）", created.name)
        self._refresh_recovery_candidates()
        return True

    @Slot(str, result=bool)
    def restoreProject(self, backup_path_value: str) -> bool:
        """確認済みのbackup選択を、現在または失敗したopen先へ安全に復元する。"""

        detail_message = ""

        def action() -> None:
            nonlocal detail_message
            self._ensure_no_unsaved_draft()
            result = self._projects.restore_from_backup(
                _path_from_qml(backup_path_value),
            )
            self._after_project_opened()
            pre_restore = (
                str(result.pre_restore_backup)
                if result.pre_restore_backup is not None
                else "（復元先に既存ファイルなし）"
            )
            detail_message = (
                "バックアップから復元しました。"
                f"復元前のファイル: {pre_restore}。"
                "これらのファイルにも個人情報が含まれます"
            )

        result = self._perform(action, "バックアップから復元しました")
        if result and detail_message:
            self._set_status(detail_message)
        self._refresh_recovery_candidates()
        return result

    @Slot(result=bool)
    def checkCurrentProjectIntegrity(self) -> bool:
        """現在のプロジェクトへ利用者操作で整合性検査を実行する。"""
        if self._projects.current is None:
            self._set_error("先にプロジェクトを作成または開いてください")
            return False
        check = self._projects.check_integrity()
        if not check.is_valid:
            self._set_error(check.message)
            return False
        self._set_status(check.message)
        return True

    @Slot()
    def refreshRecoveryCandidates(self) -> None:
        """異常終了・open失敗後を含む復旧候補を再走査する。"""
        self._refresh_recovery_candidates()

    @Slot(bool, result=bool)
    def closeProject(self, force: bool) -> bool:
        """未保存状態を確認し、現在のプロジェクトを閉じる。"""
        try:
            self._ensure_external_project_change_allowed()
        except ProjectFileError as exc:
            self._set_error(str(exc))
            return False
        if self._dirty and not force:
            self._set_error("未保存の変更があります。保存または取消後に閉じてください")
            return False
        self._projects.close_project()
        self._clear_project_collections()
        self._selected_teacher_id = None
        self._workflow_completed_step = 0
        self.workflowProgressChanged.emit()
        self._set_dirty(False)
        self.projectStateChanged.emit()
        self._refresh_recent_projects()
        self._refresh_recovery_candidates()
        self._set_status("プロジェクトを閉じました")
        return True

    @Slot()
    def markDirty(self) -> None:
        """QML上の未保存編集をプロジェクト状態へ反映する。"""
        if self._projects.current is not None:
            self._set_dirty(True)

    @Slot()
    def discardDraft(self) -> None:
        """QMLが入力をDB値へ戻した後、未保存表示を解除する。"""
        self._set_dirty(False)

    # Refresh and filters

    @Slot(result=bool)
    def refreshAll(self) -> bool:
        """開いているプロジェクトの全表示データを読み直す。"""
        if self._projects.current is None:
            self._refresh_recent_projects()
            return True
        return self._perform(
            self._refresh_all_collections,
            "表示データを更新しました",
        )

    @Slot(str, str)
    def setStudentFilter(self, search: str, grade: str) -> None:
        self._student_search = search
        self._student_grade = grade
        if self._projects.current is not None:
            self._refresh_students()

    @Slot(str)
    def setTeacherFilter(self, search: str) -> None:
        self._teacher_search = search
        if self._projects.current is not None:
            self._refresh_teachers()

    # Students

    @Slot(int, str, str, str, int, bool, str, bool, result=bool)
    def saveStudent(
        self,
        record_id: int,
        external_id: str,
        name: str,
        grade: str,
        max_consecutive: int,
        allow_gap: bool,
        note: str,
        active: bool,
    ) -> bool:
        def action() -> str:
            result = self._master_data.save_student(
                record_id=_optional_id(record_id),
                external_id=external_id,
                name=name,
                grade=grade,
                default_max_consecutive_slots=max_consecutive,
                allow_gap=allow_gap,
                note=note,
                active=active,
            )
            self._refresh_students()
            self._refresh_lesson_requests()
            self._shared_roster.sync_from_current_project()
            self._set_dirty(False)
            return "、".join(result.warnings)

        return self._perform_with_warnings(action, "生徒情報を保存しました")

    @Slot(int, result=bool)
    def deactivateStudent(self, record_id: int) -> bool:
        def action() -> None:
            self._master_data.deactivate_student(record_id)
            self._refresh_students()
            self._shared_roster.sync_from_current_project()

        return self._perform(action, "生徒を使用停止にしました")

    @Slot(int, result=bool)
    def deleteStudent(self, record_id: int) -> bool:
        def action() -> None:
            self._master_data.delete_student(record_id)
            self._refresh_students()
            self._refresh_lesson_requests()
            self._shared_roster.sync_from_current_project()

        return self._perform(action, "生徒を削除しました")

    # Subjects

    @Slot(int, str, str, str, int, bool, result=bool)
    def saveSubject(
        self,
        record_id: int,
        code: str,
        display_name: str,
        school_level: str,
        sort_order: int,
        active: bool,
    ) -> bool:
        def action() -> None:
            self._master_data.save_subject(
                record_id=_optional_id(record_id),
                code=code,
                display_name=display_name,
                school_level=_normalize_school_level(school_level),
                sort_order=sort_order,
                active=active,
            )
            self._refresh_subjects()
            self._refresh_qualifications()
            self._refresh_lesson_requests()
            self._shared_roster.sync_from_current_project()
            self._set_dirty(False)

        return self._perform(action, "科目情報を保存しました")

    @Slot(int, result=bool)
    def deactivateSubject(self, record_id: int) -> bool:
        def action() -> None:
            self._master_data.deactivate_subject(record_id)
            self._refresh_subjects()
            self._refresh_qualifications()
            self._shared_roster.sync_from_current_project()

        return self._perform(action, "科目を使用停止にしました")

    # Teachers and qualifications

    @Slot(int, str, str, bool, str, bool, result=bool)
    def saveTeacher(
        self,
        record_id: int,
        external_id: str,
        name: str,
        allow_gap: bool,
        note: str,
        active: bool,
    ) -> bool:
        def action() -> str:
            result = self._master_data.save_teacher(
                record_id=_optional_id(record_id),
                external_id=external_id,
                name=name,
                allow_gap=allow_gap,
                note=note,
                active=active,
            )
            self._refresh_teachers()
            self._refresh_lesson_requests()
            self._shared_roster.sync_from_current_project()
            self._set_dirty(False)
            return "、".join(result.warnings)

        return self._perform_with_warnings(action, "講師情報を保存しました")

    @Slot(int, result=bool)
    def deactivateTeacher(self, record_id: int) -> bool:
        def action() -> None:
            self._master_data.deactivate_teacher(record_id)
            self._refresh_teachers()
            self._shared_roster.sync_from_current_project()

        return self._perform(action, "講師を使用停止にしました")

    @Slot(int, result=bool)
    def deleteTeacher(self, record_id: int) -> bool:
        def action() -> None:
            self._master_data.delete_teacher(record_id)
            self._selected_teacher_id = None
            self._qualifications = []
            self.currentTeacherQualificationsChanged.emit()
            self._refresh_teachers()
            self._refresh_lesson_requests()
            self._shared_roster.sync_from_current_project()

        return self._perform(action, "講師を削除しました")

    @Slot(int)
    def selectTeacher(self, teacher_id: int) -> None:
        self._selected_teacher_id = _optional_id(teacher_id)
        self._refresh_qualifications()

    @Slot(int, bool, result=bool)
    def setQualification(self, subject_id: int, can_teach: bool) -> bool:
        teacher_id = self._selected_teacher_id
        if teacher_id is None:
            self._set_error("先に講師を選択してください")
            return False

        def action() -> None:
            self._master_data.set_qualification(
                teacher_id,
                subject_id,
                can_teach=can_teach,
            )
            self._refresh_qualifications()
            self._shared_roster.sync_from_current_project()

        return self._perform(action, "指導可否を保存しました")

    @Slot("QVariantMap", result=bool)
    def saveQualifications(self, draft_value: object) -> bool:
        """QMLの資格ドラフトを一括保存し、途中状態をDBへ公開しない。"""
        teacher_id = self._selected_teacher_id
        if teacher_id is None:
            self._set_error("先に講師を選択してください")
            return False
        if not isinstance(draft_value, dict):
            self._set_error("指導可否の入力形式が不正です")
            return False
        try:
            qualifications = {
                int(str(subject_id)): bool(can_teach)
                for subject_id, can_teach in draft_value.items()
            }
        except (TypeError, ValueError):
            self._set_error("指導可否に不正な科目IDが含まれています")
            return False

        def action() -> None:
            self._master_data.replace_qualifications(
                teacher_id,
                qualifications,
            )
            self._refresh_qualifications()
            self._shared_roster.sync_from_current_project()
            self._set_dirty(False)

        return self._perform(action, "指導可否を保存しました")

    @Slot(str, bool, result=bool)
    def setAllQualifications(self, school_level: str, can_teach: bool) -> bool:
        """学校段階単位で指導可否を保存する（空欄は全段階）。"""
        teacher_id = self._selected_teacher_id
        if teacher_id is None:
            self._set_error("先に講師を選択してください")
            return False

        def action() -> None:
            levels = (
                tuple(SCHOOL_LEVEL_LABELS)
                if not school_level
                else (_normalize_school_level(school_level),)
            )
            for level in levels:
                self._master_data.set_all_qualifications(
                    teacher_id,
                    level,
                    can_teach=can_teach,
                )
            self._refresh_qualifications()
            self._shared_roster.sync_from_current_project()

        return self._perform(action, "指導可否を一括更新しました")

    @Slot("QVariant", result=bool)
    def copyQualifications(self, source_teacher_value: object) -> bool:
        teacher_id = self._selected_teacher_id
        source_teacher_id = _optional_int(source_teacher_value)
        if teacher_id is None or source_teacher_id is None:
            self._set_error("コピー元とコピー先の講師を選択してください")
            return False

        def action() -> None:
            self._master_data.copy_qualifications(
                source_teacher_id=source_teacher_id,
                target_teacher_id=teacher_id,
            )
            self._refresh_qualifications()
            self._shared_roster.sync_from_current_project()

        return self._perform(action, "指導可否をコピーしました")

    # Time slots and open dates

    @Slot(int, str, str, str, str, int, bool, result=bool)
    def saveTimeSlot(
        self,
        record_id: int,
        code: str,
        display_name: str,
        start_time_value: str,
        end_time_value: str,
        sort_order: int,
        enabled: bool,
    ) -> bool:
        def action() -> None:
            self._master_data.save_time_slot(
                record_id=_optional_id(record_id),
                code=code,
                display_name=display_name,
                start_time=parse_hhmm(start_time_value, "start_time"),
                end_time=parse_hhmm(end_time_value, "end_time"),
                sort_order=sort_order,
                enabled=enabled,
            )
            self._refresh_time_slots()
            self._set_dirty(False)

        return self._perform(action, "コマ設定を保存しました")

    @Slot(int, result=bool)
    def deleteTimeSlot(self, record_id: int) -> bool:
        def action() -> None:
            self._master_data.delete_time_slot(record_id)
            self._refresh_time_slots()

        return self._perform(action, "コマを削除しました")

    @Slot("QVariantList", result=bool)
    def reorderTimeSlots(self, ordered_values: Sequence[object]) -> bool:
        def action() -> None:
            self._master_data.reorder_time_slots(
                _required_int(value, "コマID") for value in ordered_values
            )
            self._refresh_time_slots()

        return self._perform(action, "コマの順序を変更しました")

    @Slot(str, bool, str, result=bool)
    def setOpenDate(self, date_value: str, is_open: bool, note: str) -> bool:
        def action() -> None:
            self._master_data.set_open_date(
                parse_iso_date(date_value, "date"),
                is_open=is_open,
                note=note,
            )
            self._refresh_open_dates()
            self._set_dirty(False)

        return self._perform(action, "開校日設定を保存しました")

    @Slot(result=bool)
    def setAllDatesOpen(self) -> bool:
        def action() -> None:
            self._master_data.set_all_dates_open()
            self._refresh_open_dates()

        return self._perform(action, "期間内をすべて開校日にしました")

    @Slot("QVariantList", bool, result=bool)
    def setOpenDates(self, date_values: list[object], is_open: bool) -> bool:
        """QMLでチェックした複数日を一括更新する。"""

        def action() -> None:
            days = tuple(parse_iso_date(str(value), "dates") for value in date_values)
            self._master_data.set_open_dates_state(days, is_open=is_open)
            self._refresh_open_dates()
            self._set_dirty(False)

        state_label = "開校日" if is_open else "休校日"
        return self._perform(action, f"選択した日付を一括で{state_label}にしました")

    @Slot("QVariantList", "QVariantList", result=bool)
    def setOpenDateTimeSlots(
        self,
        date_values: Sequence[object],
        time_slot_values: Sequence[object],
    ) -> bool:
        def action() -> None:
            days = tuple(parse_iso_date(str(value), "dates") for value in date_values)
            self._master_data.set_open_dates_time_slots(
                days,
                (_required_int(value, "コマID") for value in time_slot_values),
            )
            self._refresh_open_dates()

        return self._perform(action, "選択した日付の有効コマを保存しました")

    @Slot("QVariantList", result=bool)
    def saveOpenDateSchedule(self, entry_values: Sequence[object]) -> bool:
        """QMLで保持した全日程のドラフトを一括保存する。"""

        def action() -> None:
            entries: list[tuple[date, bool, tuple[int, ...]]] = []
            for value in entry_values:
                if not isinstance(value, dict):
                    raise ValueError("開校日設定の入力形式が不正です")
                slot_values = value.get("enabledTimeSlotIds", [])
                if not isinstance(slot_values, (list, tuple)):
                    raise ValueError("開校日のコマ設定が不正です")
                entries.append(
                    (
                        parse_iso_date(str(value.get("date", "")), "date"),
                        bool(value.get("isOpen", False)),
                        tuple(_required_int(item, "コマID") for item in slot_values),
                    )
                )
            self._master_data.save_open_date_schedule(entries)
            self._refresh_open_dates()
            self._set_dirty(False)

        return self._perform(action, "開校日・休校日と使用コマを保存しました")

    @Slot(int, result=bool)
    def setWeekdayClosed(self, sunday_first_index: int) -> bool:
        def action() -> None:
            # QMLの一覧は日曜始まり、datetime.date.weekday()は月曜始まり。
            weekday = (sunday_first_index + 6) % 7
            self._master_data.set_weekday_closed(weekday)
            self._refresh_open_dates()

        return self._perform(action, "指定曜日を休校日にしました")

    # Lesson requests

    @Slot(
        int,
        int,
        "QVariant",
        int,
        "QVariant",
        int,
        "QVariant",
        "QVariant",
        "QVariant",
        bool,
        str,
        "QVariant",
        str,
        result=bool,
    )
    def saveLessonRequest(
        self,
        record_id: int,
        student_id: int,
        subject_value: object,
        required_sessions: int,
        regular_teacher_value: object,
        regular_teacher_priority: int,
        preferred_teacher_1_value: object,
        preferred_teacher_2_value: object,
        preferred_teacher_3_value: object,
        one_to_one_required: bool,
        max_consecutive_value: str,
        allow_gap_value: object,
        note: str,
    ) -> bool:
        def action() -> str:
            result = self._master_data.save_lesson_request(
                record_id=_optional_id(record_id),
                student_id=student_id,
                subject_id=_required_int(subject_value, "科目"),
                required_sessions=required_sessions,
                regular_teacher_id=_optional_int(regular_teacher_value),
                regular_teacher_priority=regular_teacher_priority,
                preferred_teacher_1_id=_optional_int(preferred_teacher_1_value),
                preferred_teacher_2_id=_optional_int(preferred_teacher_2_value),
                preferred_teacher_3_id=_optional_int(preferred_teacher_3_value),
                one_to_one_required=one_to_one_required,
                max_consecutive_slots_override=(
                    int(max_consecutive_value) if max_consecutive_value.strip() else None
                ),
                allow_gap_override=_optional_bool(allow_gap_value),
                note=note,
            )
            self._refresh_lesson_requests()
            self._set_dirty(False)
            return "、".join(result.warnings)

        return self._perform_with_warnings(action, "受講希望を保存しました")

    @Slot(int, result=bool)
    def deleteLessonRequest(self, record_id: int) -> bool:
        def action() -> None:
            self._master_data.delete_lesson_request(record_id)
            self._refresh_lesson_requests()

        return self._perform(action, "受講希望を削除しました")

    # Excel import and export

    @Slot(result=bool)
    def openSharedRoster(self) -> bool:
        """講習に依存しない共通名簿を作成し、既定のExcelで開く。"""

        def action() -> None:
            path = self._shared_roster.ensure_workbook()
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise OSError("Excelファイルを開けませんでした")

        return self._perform(action, "生徒・講師の基本情報を開きました")

    @Slot(str, result=bool)
    def exportSharedRosterTemplate(self, path_value: str) -> bool:
        """共通正本を変更せず、入力用の新しい基本情報テンプレートを保存する。"""

        return self._perform(
            lambda: self._shared_roster.export_new_template(_xlsx_path_from_qml(path_value)),
            "新しい基本情報テンプレートを保存しました",
        )

    @Slot(str, result=bool)
    def importSharedRoster(self, path_value: str) -> bool:
        """作成済み基本情報を共通正本へ取り込み、開いている講習へ反映する。"""

        def action() -> None:
            self._shared_roster.import_workbook(_xlsx_path_from_qml(path_value))
            if self._projects.current is not None:
                self._refresh_all_collections()
                self.projectStateChanged.emit()

        return self._perform(action, "基本情報を取り込み、現在の講習へ反映しました")

    @Slot(result=bool)
    def applySharedRoster(self) -> bool:
        """保存済みの共通名簿を現在の講習へ反映する。"""

        def action() -> None:
            self._shared_roster.sync_to_current_project()
            self._refresh_all_collections()
            self.projectStateChanged.emit()

        return self._perform(action, "共通名簿を現在の講習へ反映しました")

    @Slot(str, result=bool)
    def exportMasterData(self, path_value: str) -> bool:
        """現在のマスターを5シートのExcelブックへ出力する。"""

        def action() -> None:
            project = self._projects.require_project()
            database = self._projects.require_database()
            with database.session_factory() as session:
                MasterDataExcelService(session, project.project_id).export_template(
                    _xlsx_path_from_qml(path_value)
                )

        return self._perform(action, "マスターデータをExcelへ出力しました")

    @Slot(str, result=bool)
    def previewMasterImport(self, path_value: str) -> bool:
        """Excelを検証し、DBを変更せず件数と問題一覧を公開する。"""
        self._clear_excel_preview()

        def action() -> None:
            project = self._projects.require_project()
            database = self._projects.require_database()
            with database.session_factory() as session:
                preview = MasterDataExcelService(
                    session,
                    project.project_id,
                ).preview_import(_xlsx_path_from_qml(path_value))
            self._set_excel_preview(preview)
            if preview.has_errors:
                self._set_error(f"取込み前の検証で{preview.error_count}件のエラーが見つかりました")

        result = self._perform(action, "Excel取込み内容を検証しました")
        if result and self._excel_preview is not None and self._excel_preview.has_errors:
            # _performの成功メッセージで上書きされた後、反映不可を明示する。
            self._set_error(
                f"取込み前の検証で{self._excel_preview.error_count}件のエラーが見つかりました"
            )
        return result

    @Slot(result=bool)
    def applyMasterImport(self) -> bool:
        """直前に検証したExcelプレビューを1トランザクションで反映する。"""
        preview = self._excel_preview
        if preview is None:
            self._set_error("先にExcelファイルを選択してプレビューしてください")
            return False

        def action() -> None:
            project = self._projects.require_project()
            if preview.project_id != project.project_id:
                raise ValueError("別のプロジェクトで作成したプレビューは反映できません")
            database = self._projects.require_database()
            with database.session_factory.begin() as session:
                MasterDataExcelService(session, project.project_id).apply_import(preview)
            self._excel_preview = None
            self._refresh_all_collections()
            self.excelPreviewChanged.emit()

        return self._perform(action, "Excelのマスターデータを反映しました")

    # Messages

    @Slot()
    def clearMessages(self) -> None:
        self._status_message = ""
        self._error_message = ""
        self.messageChanged.emit()

    # Internal refresh and error boundary

    def _after_project_opened(self) -> None:
        self._selected_teacher_id = None
        self._clear_excel_preview()
        self._set_dirty(False)
        self._refresh_all_collections()
        self.projectStateChanged.emit()
        self._refresh_recent_projects()
        self._workflow_completed_step = self._projects.workflow_completed_step()
        self.workflowProgressChanged.emit()
        self._refresh_recovery_candidates()

    def _refresh_all_collections(self) -> None:
        self._refresh_students()
        self._refresh_teachers()
        self._refresh_subjects()
        self._refresh_time_slots()
        self._refresh_open_dates()
        self._refresh_lesson_requests()
        self._refresh_qualifications()

    def _refresh_students(self) -> None:
        rows = self._master_data.list_students(
            search=self._student_search,
            grade=self._student_grade,
        )
        self._students = [
            {
                "id": row.id,
                "externalId": row.external_id,
                "name": row.name,
                "grade": row.grade,
                "maxConsecutive": row.default_max_consecutive_slots,
                "allowGap": row.allow_gap,
                "note": row.note,
                "active": row.active,
            }
            for row in rows
        ]
        self.studentsChanged.emit()

    def _refresh_teachers(self) -> None:
        rows = self._master_data.list_teachers(search=self._teacher_search)
        self._teachers = [
            {
                "id": row.id,
                "externalId": row.external_id,
                "name": row.name,
                "allowGap": row.allow_gap,
                "note": row.note,
                "active": row.active,
            }
            for row in rows
        ]
        self.teachersChanged.emit()

    def _refresh_subjects(self) -> None:
        rows = self._master_data.list_subjects()
        self._subjects = [
            {
                "id": row.id,
                "code": row.code,
                "displayName": row.display_name,
                "schoolLevel": row.school_level,
                "sortOrder": row.sort_order,
                "active": row.active,
            }
            for row in rows
        ]
        self.subjectsChanged.emit()

    def _refresh_time_slots(self) -> None:
        rows = self._master_data.list_time_slots()
        self._time_slots = [
            {
                "id": row.id,
                "code": row.code,
                "displayName": row.display_name,
                "startTime": row.start_time.strftime("%H:%M"),
                "endTime": row.end_time.strftime("%H:%M"),
                "sortOrder": row.sort_order,
                "enabled": row.enabled,
            }
            for row in rows
        ]
        self.timeSlotsChanged.emit()

    def _refresh_open_dates(self) -> None:
        rows = self._master_data.list_open_dates()
        self._open_dates = [
            {
                "id": row.id,
                "date": row.date.isoformat(),
                "isOpen": row.is_open,
                "note": row.note,
                "enabledTimeSlotIds": list(row.enabled_time_slot_ids),
                "enabledSlotCodes": "・".join(
                    str(slot["code"])
                    for slot in self._time_slots
                    if _required_int(slot["id"], "コマID") in row.enabled_time_slot_ids
                ),
            }
            for row in rows
        ]
        self.openDatesChanged.emit()

    def _refresh_lesson_requests(self) -> None:
        rows = self._master_data.list_lesson_requests()
        self._lesson_requests = [
            {
                "id": row.id,
                "projectId": row.project_id,
                "studentId": row.student_id,
                "studentName": row.student_name,
                "subjectId": row.subject_id,
                "subjectName": row.subject_name,
                "requiredSessions": row.required_sessions,
                "regularTeacherId": row.regular_teacher_id,
                "regularTeacherName": row.regular_teacher_name,
                "regularTeacherPriority": row.regular_teacher_priority,
                "preferredTeacher1Id": row.preferred_teacher_1_id,
                "preferredTeacher2Id": row.preferred_teacher_2_id,
                "preferredTeacher3Id": row.preferred_teacher_3_id,
                "oneToOneRequired": row.one_to_one_required,
                "maxConsecutiveOverride": row.max_consecutive_slots_override,
                "allowGapOverride": row.allow_gap_override,
                "note": row.note,
            }
            for row in rows
        ]
        self.lessonRequestsChanged.emit()

    def _refresh_qualifications(self) -> None:
        if self._selected_teacher_id is None:
            self._qualifications = []
        else:
            rows = self._master_data.list_qualifications(self._selected_teacher_id)
            self._qualifications = [
                {
                    "teacherId": row.teacher_id,
                    "subjectId": row.subject_id,
                    "code": row.subject_code,
                    "displayName": row.subject_name,
                    "schoolLevel": row.school_level,
                    "canTeach": row.can_teach,
                    "note": row.note,
                }
                for row in rows
            ]
        self.currentTeacherQualificationsChanged.emit()

    def _refresh_recent_projects(self) -> None:
        self._recent_projects = [
            _recent_project_dict(summary) for summary in self._projects.recent_projects()
        ]
        self.recentProjectsChanged.emit()

    def _refresh_recovery_candidates(self) -> None:
        try:
            candidates = self._projects.recovery_candidates()
        except ProjectFileError as exc:
            logger.warning("復旧候補を更新できませんでした: %s", exc)
            self._recovery_candidates = []
            self.recoveryCandidatesChanged.emit()
            return
        self._recovery_candidates = [
            _recovery_candidate_dict(candidate) for candidate in candidates
        ]
        self.recoveryCandidatesChanged.emit()

    def _show_safety_warning_if_any(self) -> None:
        warning = self._projects.safety_warning
        if warning:
            self._set_error(warning)

    def _clear_project_collections(self) -> None:
        self._students = []
        self._teachers = []
        self._subjects = []
        self._time_slots = []
        self._open_dates = []
        self._lesson_requests = []
        self._qualifications = []
        self._clear_excel_preview()
        self.studentsChanged.emit()
        self.teachersChanged.emit()
        self.subjectsChanged.emit()
        self.timeSlotsChanged.emit()
        self.openDatesChanged.emit()
        self.lessonRequestsChanged.emit()
        self.currentTeacherQualificationsChanged.emit()

    def _set_excel_preview(self, preview: ImportPreview) -> None:
        self._excel_preview = preview
        new_count = sum(preview.new_counts.values())
        update_count = sum(preview.update_counts.values())
        self._excel_preview_summary = {
            "newCount": new_count,
            "updateCount": update_count,
            "unchangedCount": max(0, len(preview.rows) - new_count - update_count),
            "warningCount": preview.warning_count,
            "errorCount": preview.error_count,
        }
        self._excel_issues = [
            {
                "severity": issue.severity.value,
                "sheet": issue.sheet_name or "",
                "row": issue.row_number or "",
                "column": issue.column_name or issue.sheet_name or "",
                "message": issue.message,
            }
            for issue in preview.issues
            if issue.severity in {IssueSeverity.ERROR, IssueSeverity.WARNING}
        ]
        self.excelPreviewChanged.emit()

    def _clear_excel_preview(self) -> None:
        self._excel_preview = None
        self._excel_preview_summary = None
        self._excel_issues = []
        self.excelPreviewChanged.emit()

    def _perform(self, action: Callable[[], object], success_message: str) -> bool:
        self.clearMessages()
        try:
            action()
        except (DomainValidationError, ProjectFileError, OSError, ValueError) as exc:
            logger.warning(
                "Phase 2操作を完了できませんでした（%s）",
                type(exc).__name__,
            )
            self._set_error(str(exc))
            return False
        except Exception:
            logger.exception("Phase 2操作で予期しないエラーが発生しました")
            self._set_error("処理を完了できませんでした。ローカルログを確認してください")
            return False
        self._set_status(success_message)
        return True

    def _perform_with_warnings(
        self,
        action: Callable[[], str],
        success_message: str,
    ) -> bool:
        warnings = ""

        def wrapped() -> None:
            nonlocal warnings
            warnings = action()

        result = self._perform(wrapped, success_message)
        if result and warnings:
            self._set_status(f"{success_message}（警告: {warnings}）")
        return result

    def _ensure_no_unsaved_draft(self) -> None:
        if self._dirty:
            raise ProjectFileError(
                "未保存の変更があります。保存または取消後にプロジェクトを切り替えてください"
            )
        self._ensure_external_project_change_allowed()

    def _ensure_external_project_change_allowed(self) -> None:
        if self._project_change_guard is not None:
            self._project_change_guard()

    def _set_dirty(self, value: bool) -> None:
        if self._dirty == value:
            return
        self._dirty = value
        self.dirtyChanged.emit()

    def _set_status(self, message: str) -> None:
        self._status_message = message
        self._error_message = ""
        self.messageChanged.emit()

    def _set_error(self, message: str) -> None:
        self._status_message = ""
        self._error_message = message
        self.messageChanged.emit()


def _path_from_qml(value: str) -> Path:
    stripped = value.strip()
    if not stripped:
        raise ValueError("ファイルの保存先を選択してください")
    url = QUrl(stripped)
    if url.isLocalFile():
        local_path = url.toLocalFile()
        if local_path:
            return Path(local_path)
    return Path(stripped)


def _xlsx_path_from_qml(value: str) -> Path:
    path = _path_from_qml(value)
    if path.suffix.casefold() != ".xlsx":
        path = Path(f"{path}.xlsx")
    return path


def _optional_id(value: int) -> int | None:
    return value if value > 0 else None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("選択値が不正です") from exc
    return parsed if parsed > 0 else None


def _required_int(value: object, label: str) -> int:
    parsed = _optional_int(value)
    if parsed is None:
        raise ValueError(f"{label}を選択してください")
    return parsed


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError("空きコマ設定の選択値が不正です")


def _normalize_school_level(value: str) -> str:
    aliases = {
        "elementary": "elementary",
        "middle": "junior_high",
        "junior_high": "junior_high",
        "high": "high_school",
        "high_school": "high_school",
    }
    normalized = aliases.get(value)
    if normalized is None:
        raise ValueError("学校段階の選択値が不正です")
    return normalized


def _recent_project_dict(summary: ProjectSummary) -> dict[str, object]:
    return {
        "path": str(summary.path),
        "title": summary.title,
        "campusName": summary.campus_name,
        "startDate": summary.start_date.isoformat(),
        "endDate": summary.end_date.isoformat(),
        "lastOpenedAt": summary.last_opened_at.isoformat(),
    }


def _recovery_candidate_dict(candidate: RecoveryCandidate) -> dict[str, object]:
    kind_labels = {
        "automatic": "自動バックアップ",
        "migration": "マイグレーション前",
        "pre_restore": "前回の復元前",
    }
    return {
        "path": str(candidate.path),
        "targetPath": str(candidate.target_path),
        "kind": candidate.kind.value,
        "kindLabel": kind_labels[candidate.kind.value],
        "createdAt": candidate.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "sizeBytes": candidate.size_bytes,
        "isValid": candidate.integrity.is_valid,
        "integrityMessage": candidate.integrity.message,
    }
