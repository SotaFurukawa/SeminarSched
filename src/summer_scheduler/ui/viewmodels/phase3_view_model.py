"""Phase 3の取込み・集団授業・入力検証をQMLへ公開する。"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from summer_scheduler.application.availability_import_service import (
    AvailabilityImportError,
    AvailabilityImportService,
    AvailabilitySourceInspection,
)
from summer_scheduler.application.course_survey_service import (
    CourseSurveyError,
    CourseSurveyPreview,
    CourseSurveyService,
)
from summer_scheduler.application.group_lesson_service import (
    GroupLessonImportError,
    GroupLessonService,
)
from summer_scheduler.application.phase3_dto import (
    AvailabilityDiffDto,
    AvailabilityImportPreview,
    AvailabilityKind,
    GroupImportPreview,
    GroupLessonDiffDto,
    ImportIssueDto,
    ValidationIssueDto,
)
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.application.project_validation_service import (
    ProjectValidationService,
)
from summer_scheduler.application.questionnaire_script_service import (
    QuestionnaireScriptService,
)
from summer_scheduler.application.sample_project_service import SampleProjectService

logger = logging.getLogger(__name__)


class Phase3ViewModel(QObject):
    """Phase 3の表示状態を基本型だけへ変換するプレゼンテーション境界。"""

    projectStateChanged = Signal()
    availabilityStateChanged = Signal()
    groupStateChanged = Signal()
    validationStateChanged = Signal()
    messageChanged = Signal()
    projectChanged = Signal()
    questionnaireScriptsChanged = Signal()

    def __init__(
        self,
        projects: ProjectService,
        availability: AvailabilityImportService,
        groups: GroupLessonService,
        validation: ProjectValidationService,
        samples: SampleProjectService,
        questionnaires: QuestionnaireScriptService | None = None,
        course_surveys: CourseSurveyService | None = None,
        before_project_change: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._projects = projects
        self._availability = availability
        self._groups = groups
        self._validation = validation
        self._samples = samples
        self._questionnaires = questionnaires or QuestionnaireScriptService(projects)
        self._course_surveys = course_surveys or CourseSurveyService(projects)
        self._before_project_change = before_project_change
        self._status_message = ""
        self._error_message = ""
        self._last_questionnaire_script_directory = ""
        self._combined_student_path = ""
        self._combined_teacher_path = ""
        self._combined_trial_student_rows: set[int] = set()
        self._combined_preview: CourseSurveyPreview | None = None
        self._combined_issues: list[dict[str, object]] = []
        self._combined_summary: dict[str, int] = {
            "studentCount": 0,
            "teacherCount": 0,
            "errorCount": 0,
            "warningCount": 0,
        }

        self._import_kind: AvailabilityKind = "student"
        self._source_path = ""
        self._stored_source_name = ""
        self._source_sheets: list[str] = []
        self._selected_sheet = ""
        self._source_encoding = "auto"
        self._source_headers: list[str] = []
        self._mapping_fields: list[tuple[str, str, bool]] = []
        self._mapping: dict[str, str] = {}
        self._source_preview_rows: list[dict[str, object]] = []
        self._availability_preview: AvailabilityImportPreview | None = None
        self._import_diffs: list[dict[str, object]] = []
        self._import_issues: list[dict[str, object]] = []
        self._import_summary = _empty_summary()

        self._group_preview: GroupImportPreview | None = None
        self._group_source_path = ""
        self._group_lessons: list[dict[str, object]] = []
        self._group_dates: list[dict[str, object]] = []
        self._group_subjects: list[dict[str, object]] = []
        self._group_teachers: list[dict[str, object]] = []
        self._group_slots: list[dict[str, object]] = []
        self._group_import_diffs: list[dict[str, object]] = []
        self._group_import_issues: list[dict[str, object]] = []
        self._group_import_summary = _empty_summary()

        self._validation_issues: list[dict[str, object]] = []
        self._validation_summary: dict[str, object] = {
            "errorCount": 0,
            "warningCount": 0,
            "infoCount": 0,
            "canOptimize": False,
        }
        self._validation_has_run = False
        self._observed_project_path: Path | None = None
        self.refreshPhase3()

    # Shared properties

    def _get_has_open_project(self) -> bool:
        return self._projects.current is not None

    hasOpenProject = Property(bool, _get_has_open_project, notify=projectStateChanged)

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=messageChanged)

    def _get_error_message(self) -> str:
        return self._error_message

    errorMessage = Property(str, _get_error_message, notify=messageChanged)

    def _get_default_questionnaire_directory_url(self) -> QUrl:
        current = self._projects.current
        if current is None:
            return QUrl()
        return QUrl.fromLocalFile(str(current.path.parent))

    defaultQuestionnaireDirectoryUrl = Property(
        QUrl,
        _get_default_questionnaire_directory_url,
        notify=projectStateChanged,
    )

    def _get_last_questionnaire_script_directory(self) -> str:
        return self._last_questionnaire_script_directory

    lastQuestionnaireScriptDirectory = Property(
        str,
        _get_last_questionnaire_script_directory,
        notify=questionnaireScriptsChanged,
    )

    combinedStudentPath = Property(
        str,
        lambda self: self._combined_student_path,
        notify=availabilityStateChanged,
    )
    combinedTeacherPath = Property(
        str,
        lambda self: self._combined_teacher_path,
        notify=availabilityStateChanged,
    )
    combinedIssues = Property(
        list,
        lambda self: self._combined_issues,
        notify=availabilityStateChanged,
    )
    combinedSummary = Property(
        object,
        lambda self: self._combined_summary,
        notify=availabilityStateChanged,
    )
    canValidateCombinedSurvey = Property(
        bool,
        lambda self: bool(self._combined_student_path and self._combined_teacher_path),
        notify=availabilityStateChanged,
    )
    canApplyCombinedSurvey = Property(
        bool,
        lambda self: self._combined_preview is not None and not self._combined_preview.has_errors,
        notify=availabilityStateChanged,
    )

    # Availability wizard properties

    def _get_import_kind(self) -> str:
        return self._import_kind

    importKind = Property(str, _get_import_kind, notify=availabilityStateChanged)

    def _get_source_path(self) -> str:
        return self._source_path

    sourcePath = Property(str, _get_source_path, notify=availabilityStateChanged)

    def _get_stored_source_name(self) -> str:
        return self._stored_source_name

    storedSourceName = Property(
        str,
        _get_stored_source_name,
        notify=availabilityStateChanged,
    )

    def _get_source_sheets(self) -> list[str]:
        return self._source_sheets

    sourceSheets = Property(list, _get_source_sheets, notify=availabilityStateChanged)

    def _get_selected_sheet(self) -> str:
        return self._selected_sheet

    selectedSheet = Property(str, _get_selected_sheet, notify=availabilityStateChanged)

    def _get_source_encoding(self) -> str:
        return self._source_encoding

    sourceEncoding = Property(str, _get_source_encoding, notify=availabilityStateChanged)

    def _get_source_headers(self) -> list[str]:
        return self._source_headers

    sourceHeaders = Property(list, _get_source_headers, notify=availabilityStateChanged)

    def _get_mapping_rows(self) -> list[dict[str, object]]:
        return [
            {
                "canonicalKey": key,
                "label": label,
                "required": required,
                "sourceHeader": self._mapping.get(key, ""),
            }
            for key, label, required in self._mapping_fields
        ]

    mappingRows = Property(list, _get_mapping_rows, notify=availabilityStateChanged)

    def _get_source_preview_rows(self) -> list[dict[str, object]]:
        return self._source_preview_rows

    sourcePreviewRows = Property(
        list,
        _get_source_preview_rows,
        notify=availabilityStateChanged,
    )

    def _get_import_diffs(self) -> list[dict[str, object]]:
        return self._import_diffs

    importDiffs = Property(list, _get_import_diffs, notify=availabilityStateChanged)

    def _get_import_issues(self) -> list[dict[str, object]]:
        return self._import_issues

    importIssues = Property(list, _get_import_issues, notify=availabilityStateChanged)

    def _get_import_summary(self) -> dict[str, int]:
        return self._import_summary

    importSummary = Property(object, _get_import_summary, notify=availabilityStateChanged)

    def _get_can_apply_import(self) -> bool:
        return self._availability_preview is not None and not self._availability_preview.has_errors

    canApplyImport = Property(bool, _get_can_apply_import, notify=availabilityStateChanged)

    # Group lesson properties

    def _get_group_lessons(self) -> list[dict[str, object]]:
        return self._group_lessons

    groupLessons = Property(list, _get_group_lessons, notify=groupStateChanged)

    groupDates = Property(
        list,
        lambda self: self._group_dates,
        notify=groupStateChanged,
    )
    groupSubjects = Property(
        list,
        lambda self: self._group_subjects,
        notify=groupStateChanged,
    )
    groupTeachers = Property(
        list,
        lambda self: self._group_teachers,
        notify=groupStateChanged,
    )
    groupSlots = Property(
        list,
        lambda self: self._group_slots,
        notify=groupStateChanged,
    )

    def _get_group_source_path(self) -> str:
        return self._group_source_path

    groupSourcePath = Property(
        str,
        _get_group_source_path,
        notify=groupStateChanged,
    )

    def _get_group_import_diffs(self) -> list[dict[str, object]]:
        return self._group_import_diffs

    groupImportDiffs = Property(list, _get_group_import_diffs, notify=groupStateChanged)

    def _get_group_import_issues(self) -> list[dict[str, object]]:
        return self._group_import_issues

    groupImportIssues = Property(list, _get_group_import_issues, notify=groupStateChanged)

    def _get_group_import_summary(self) -> dict[str, int]:
        return self._group_import_summary

    groupImportSummary = Property(
        object,
        _get_group_import_summary,
        notify=groupStateChanged,
    )

    def _get_can_apply_group_import(self) -> bool:
        return self._group_preview is not None and not self._group_preview.has_errors

    canApplyGroupImport = Property(
        bool,
        _get_can_apply_group_import,
        notify=groupStateChanged,
    )

    # Project validation properties

    def _get_validation_issues(self) -> list[dict[str, object]]:
        return self._validation_issues

    validationIssues = Property(
        list,
        _get_validation_issues,
        notify=validationStateChanged,
    )

    def _get_validation_summary(self) -> dict[str, object]:
        return self._validation_summary

    validationSummary = Property(
        object,
        _get_validation_summary,
        notify=validationStateChanged,
    )

    # Availability wizard actions

    @Slot(str)
    def setCombinedStudentSource(self, path_value: str) -> None:
        self._combined_student_path = str(_path_from_qml(path_value))
        self._combined_trial_student_rows.clear()
        self._clear_combined_preview()
        self._clear_messages()
        self.availabilityStateChanged.emit()

    @Slot(str)
    def setCombinedTeacherSource(self, path_value: str) -> None:
        self._combined_teacher_path = str(_path_from_qml(path_value))
        self._combined_trial_student_rows.clear()
        self._clear_combined_preview()
        self._clear_messages()
        self.availabilityStateChanged.emit()

    @Slot(result=bool)
    def validateCombinedSurvey(self) -> bool:
        """生徒・講師のGoogleフォーム回答を一度に検証する。"""

        def action() -> None:
            if not self._combined_student_path or not self._combined_teacher_path:
                raise CourseSurveyError("生徒回答と講師回答を両方選択してください。")
            preview = self._course_surveys.prepare(
                Path(self._combined_student_path),
                Path(self._combined_teacher_path),
                trial_student_rows=frozenset(self._combined_trial_student_rows),
            )
            self._set_combined_preview(preview)

        result = self._perform(action, "2つのアンケートをまとめて検証しました")
        if result and self._combined_preview is not None and self._combined_preview.has_errors:
            self._set_error(
                f"統合前の検証で{self._combined_summary['errorCount']}件のエラーが見つかりました"
            )
        return result

    @Slot(int, bool, result=bool)
    def setCombinedStudentTrialResolution(self, row: int, mark_as_trial: bool) -> bool:
        """未登録の生徒回答を、この講習だけの体験生として解決する。"""

        def action() -> None:
            if not self._combined_student_path or not self._combined_teacher_path:
                raise CourseSurveyError("生徒回答と講師回答を両方選択してください。")
            if mark_as_trial:
                self._combined_trial_student_rows.add(row)
            else:
                self._combined_trial_student_rows.discard(row)
            preview = self._course_surveys.prepare(
                Path(self._combined_student_path),
                Path(self._combined_teacher_path),
                trial_student_rows=frozenset(self._combined_trial_student_rows),
            )
            self._set_combined_preview(preview)

        return self._perform(
            action,
            "体験生の扱いを更新しました",
        )

    @Slot(result=bool)
    def applyCombinedSurvey(self) -> bool:
        """検証済み回答を一括反映し、原本と統合xlsxをプロジェクトへ保存する。"""

        message = "アンケートを統合しました"

        def action() -> None:
            nonlocal message
            if self._combined_preview is None:
                raise CourseSurveyError("先に2つのアンケートを検証してください。")
            result = self._course_surveys.apply(self._combined_preview)
            message = (
                f"アンケートを統合しました（生徒{result.students}、講師{result.teachers}、"
                f"受講希望{result.lesson_requests}、体験生{result.trial_students}）"
            )
            self._combined_trial_student_rows.clear()
            self._clear_combined_preview()
            self._refresh_stored_source_name()
            self.availabilityStateChanged.emit()
            self._refresh_validation_after_data_change()

        result = self._perform(action, "アンケートを統合しました")
        if result:
            self._set_status(message)
        return result

    @Slot(str, result=bool)
    def exportCombinedSurvey(self, path_value: str) -> bool:
        def action() -> None:
            self._course_surveys.export_latest_combined(_xlsx_path_from_qml(path_value))

        return self._perform(
            action,
            "プロジェクト内の統合アンケートを保存しました",
        )

    @Slot(str)
    def setImportKind(self, value: str) -> None:
        if value not in {"student", "teacher"}:
            self._set_error("取込み対象は生徒または講師を選択してください")
            return
        if self._import_kind == value:
            return
        self._import_kind = "student" if value == "student" else "teacher"
        self._reset_availability_source(keep_kind=True)
        self._refresh_stored_source_name()
        self._clear_messages()
        self.availabilityStateChanged.emit()

    @Slot(str, str, result=bool)
    def inspectAvailabilitySource(self, path_value: str, encoding: str) -> bool:
        def action() -> None:
            path = _path_from_qml(path_value)
            inspection = self._availability.inspect_source(
                self._import_kind,
                path,
                encoding=encoding or "auto",
            )
            self._apply_source_inspection(inspection)

        return self._perform(action, "入力ファイルを確認しました")

    @Slot(str, result=bool)
    def selectSourceSheet(self, sheet_name: str) -> bool:
        def action() -> None:
            if not self._source_path:
                raise ValueError("先に入力ファイルを選択してください")
            inspection = self._availability.inspect_source(
                self._import_kind,
                Path(self._source_path),
                encoding=self._source_encoding,
                sheet_name=sheet_name,
            )
            self._apply_source_inspection(inspection)

        return self._perform(action, "シートを選択しました")

    @Slot(str, result=bool)
    def setSourceEncoding(self, encoding: str) -> bool:
        self._source_encoding = encoding or "auto"
        if not self._source_path or Path(self._source_path).suffix.casefold() != ".csv":
            self.availabilityStateChanged.emit()
            return True

        def action() -> None:
            inspection = self._availability.inspect_source(
                self._import_kind,
                Path(self._source_path),
                encoding=self._source_encoding,
            )
            self._apply_source_inspection(inspection)

        return self._perform(action, "CSV文字コードを変更しました")

    @Slot(str, str)
    def setColumnMapping(self, canonical_key: str, source_header: str) -> None:
        valid_keys = {key for key, _label, _required in self._mapping_fields}
        if canonical_key not in valid_keys:
            self._set_error("列マッピングの保存先項目が不正です")
            return
        for other_key, mapped_header in tuple(self._mapping.items()):
            if other_key != canonical_key and source_header and mapped_header == source_header:
                del self._mapping[other_key]
        if source_header:
            self._mapping[canonical_key] = source_header
        else:
            self._mapping.pop(canonical_key, None)
        self._clear_availability_preview()
        self._clear_messages()
        self.availabilityStateChanged.emit()

    @Slot(result=bool)
    def validateAvailabilityImport(self) -> bool:
        def action() -> None:
            if not self._source_path:
                raise ValueError("先に入力ファイルを選択してください")
            preview = self._availability.prepare_import(
                self._import_kind,
                Path(self._source_path),
                sheet_name=self._selected_sheet or None,
                encoding=self._source_encoding,
                mapping=self._mapping,
            )
            self._set_availability_preview(preview)

        return self._perform(action, "アンケートを検証し差分を作成しました")

    @Slot(bool, result=bool)
    def applyAvailabilityImport(self, include_deletes: bool) -> bool:
        def action() -> None:
            if self._availability_preview is None:
                raise AvailabilityImportError("先に入力ファイルを検証してください")
            result = self._availability.apply_import(
                self._availability_preview,
                include_deletes=include_deletes,
            )
            self._clear_availability_preview()
            self._refresh_stored_source_name()
            self.availabilityStateChanged.emit()
            self._refresh_validation_after_data_change()
            self._set_status(
                "アンケートを反映しました"
                f"（追加{result.added}、変更{result.changed}、"
                f"削除{result.deleted}、警告{result.warnings}）"
            )

        return self._perform(action, "")

    @Slot()
    def clearImport(self) -> None:
        self._reset_availability_source(keep_kind=True)
        self._clear_messages()
        self.availabilityStateChanged.emit()

    @Slot(str, result=bool)
    def exportStudentTemplate(self, path_value: str) -> bool:
        return self._perform(
            lambda: self._availability.export_student_template(_xlsx_path_from_qml(path_value)),
            "生徒アンケートテンプレートを保存しました",
        )

    @Slot(str, result=bool)
    def exportTeacherTemplate(self, path_value: str) -> bool:
        return self._perform(
            lambda: self._availability.export_teacher_template(_xlsx_path_from_qml(path_value)),
            "講師アンケートテンプレートを保存しました",
        )

    @Slot(str, str, str, str, str, result=bool)
    def exportGoogleFormsScripts(
        self,
        directory_value: str,
        student_title: str,
        teacher_title: str,
        deadline: str,
        contact: str,
    ) -> bool:
        """現在の日程・コマを反映した生徒用／講師用Apps Scriptを生成する。"""

        def action() -> None:
            result = self._questionnaires.export_scripts(
                _path_from_qml(directory_value),
                student_title=student_title,
                teacher_title=teacher_title,
                deadline=deadline,
                contact=contact,
            )
            self._last_questionnaire_script_directory = str(result.directory)
            self.questionnaireScriptsChanged.emit()

        return self._perform(
            action,
            "生徒用・講師用Googleフォーム作成キットを保存しました",
        )

    @Slot(result=bool)
    def openQuestionnaireScriptDirectory(self) -> bool:
        """最後に生成したGoogleフォーム作成キットのフォルダーを開く。"""

        def action() -> None:
            if not self._last_questionnaire_script_directory:
                raise ValueError("先にGoogleフォーム作成キットを保存してください")
            directory = Path(self._last_questionnaire_script_directory)
            if not directory.is_dir():
                raise ValueError("Googleフォーム作成キットの保存先が見つかりません")
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
                raise OSError("保存先フォルダーを開けませんでした")

        return self._perform(action, "Googleフォーム作成キットの保存先を開きました")

    # Group lesson actions

    @Slot(str, result=bool)
    def inspectGroupSource(self, path_value: str) -> bool:
        def action() -> None:
            path = _path_from_qml(path_value)
            self._groups.inspect_group_import(path)
            self._group_source_path = str(path.resolve())
            self._clear_group_preview()
            self.groupStateChanged.emit()

        return self._perform(action, "集団授業ファイルの2シートを確認しました")

    @Slot(result=bool)
    def validateGroupImport(self) -> bool:
        def action() -> None:
            if not self._group_source_path:
                raise ValueError("先に集団授業ファイルを選択してください")
            preview = self._groups.prepare_group_import(Path(self._group_source_path))
            self._set_group_preview(preview)

        return self._perform(action, "集団授業を検証し差分を作成しました")

    @Slot(bool, result=bool)
    def applyGroupImport(self, include_deletes: bool) -> bool:
        def action() -> None:
            if self._group_preview is None:
                raise GroupLessonImportError("先に集団授業ファイルを検証してください")
            result = self._groups.apply_group_import(
                self._group_preview,
                include_deletes=include_deletes,
            )
            self._clear_group_preview()
            self._refresh_group_lessons()
            self.groupStateChanged.emit()
            self._refresh_validation_after_data_change()
            self._set_status(
                "集団授業を反映しました"
                f"（追加{result.added}、変更{result.changed}、"
                f"削除{result.deleted}、警告{result.warnings}）"
            )

        return self._perform(action, "")

    @Slot()
    def clearGroupImport(self) -> None:
        self._group_source_path = ""
        self._clear_group_preview()
        self._clear_messages()
        self.groupStateChanged.emit()

    @Slot(str, result=bool)
    def exportGroupTemplate(self, path_value: str) -> bool:
        return self._perform(
            lambda: self._groups.export_template(_xlsx_path_from_qml(path_value)),
            "集団授業テンプレートを保存しました",
        )

    @Slot(str, str, str, str, str, str, str, str, str, result=bool)
    def createCalendarGroupLesson(
        self,
        grade: str,
        subject_code: str,
        day_value: str,
        start_value: str,
        end_value: str,
        course_name: str,
        teacher_external_id: str,
        room: str,
        note: str,
    ) -> bool:
        def action() -> None:
            self._groups.create_calendar_lesson(
                grade=grade,
                subject_code=subject_code,
                day=date.fromisoformat(day_value),
                start_time=time.fromisoformat(start_value),
                end_time=time.fromisoformat(end_value),
                course_name=course_name,
                teacher_external_id=teacher_external_id or None,
                room=room,
                note=note,
            )
            self._refresh_group_lessons()
            self._refresh_validation_after_data_change()
            self.groupStateChanged.emit()

        return self._perform(action, "集団授業をカレンダーへ追加しました")

    @Slot(int, result=bool)
    def deleteCalendarGroupLesson(self, group_lesson_id: int) -> bool:
        def action() -> None:
            self._groups.delete_calendar_lesson(group_lesson_id)
            self._refresh_group_lessons()
            self._refresh_validation_after_data_change()
            self.groupStateChanged.emit()

        return self._perform(action, "集団授業を削除しました")

    # Validation and sample actions

    @Slot(result=bool)
    def runProjectValidation(self) -> bool:
        def action() -> None:
            issues = self._validation.run_validation()
            self._validation_has_run = True
            self._set_validation_issues(issues)

        return self._perform(action, "プロジェクト全体の入力を再検証しました")

    @Slot()
    def refreshPhase3(self) -> None:
        self._clear_messages()
        current_path = (
            self._projects.current.path.resolve() if self._projects.current is not None else None
        )
        if current_path != self._observed_project_path:
            self._observed_project_path = current_path
            self._last_questionnaire_script_directory = ""
            self._reset_availability_source(keep_kind=True)
            self._combined_student_path = ""
            self._combined_teacher_path = ""
            self._combined_trial_student_rows.clear()
            self._clear_combined_preview()
            self._group_source_path = ""
            self._clear_group_preview()
            self._validation_has_run = False
        if self._projects.current is None:
            self._stored_source_name = ""
            self._group_lessons = []
            self._group_dates = []
            self._group_subjects = []
            self._group_teachers = []
            self._group_slots = []
            self._validation_issues = []
            self._validation_has_run = False
            self._update_validation_summary()
        else:
            self._refresh_stored_source_name()
            self._refresh_group_options()
            self._refresh_group_lessons()
            self._set_validation_issues(self._validation.list_issues())
        self.projectStateChanged.emit()
        self.questionnaireScriptsChanged.emit()
        self.availabilityStateChanged.emit()
        self.groupStateChanged.emit()
        self.validationStateChanged.emit()

    @Slot(str, result=bool)
    def createAnonymousSample(self, path_value: str) -> bool:
        def action() -> None:
            if self._before_project_change is not None:
                self._before_project_change()
            self._samples.create_anonymous_sample(_path_from_qml(path_value))
            self.projectChanged.emit()
            self._reset_availability_source(keep_kind=True)
            self._refresh_stored_source_name()
            self._group_source_path = ""
            self._clear_group_preview()
            self._validation_has_run = True
            self._refresh_group_options()
            self._refresh_group_lessons()
            self._set_validation_issues(self._validation.list_issues())
            self.projectStateChanged.emit()
            self.availabilityStateChanged.emit()
            self.groupStateChanged.emit()

        return self._perform(action, "匿名サンプルプロジェクトを作成しました")

    @Slot()
    def clearMessages(self) -> None:
        self._clear_messages()

    # Internal state conversion

    def _apply_source_inspection(
        self,
        inspection: AvailabilitySourceInspection,
    ) -> None:
        # AvailabilitySourceInspection is kept behind the Application Service boundary;
        # its fields are converted immediately to QML-compatible primitives.
        source = inspection.source
        self._source_path = str(source.source_path.resolve())
        self._source_sheets = [sheet.name for sheet in source.sheets]
        self._selected_sheet = inspection.selected_sheet
        self._source_encoding = inspection.encoding
        self._source_headers = list(inspection.headers)
        self._mapping_fields = list(inspection.mapping_fields)
        self._mapping = dict(inspection.suggested_mapping)
        self._source_preview_rows = [
            {str(key): _qml_scalar(value) for key, value in row.items()}
            for row in inspection.preview_rows
        ]
        self._clear_availability_preview()
        self.availabilityStateChanged.emit()

    def _set_availability_preview(self, preview: AvailabilityImportPreview) -> None:
        self._availability_preview = preview
        self._import_diffs = [
            {
                "operation": row.operation,
                "entityName": row.entity_name,
                "externalId": row.external_id,
                "date": row.day.isoformat(),
                "slotCode": row.slot_code,
                "before": "" if row.before is None else row.before,
                "after": "" if row.after is None else row.after,
                "message": row.message,
            }
            for row in preview.diffs
        ]
        self._import_issues = [_issue_dict(issue) for issue in preview.issues]
        self._import_summary = _summary(preview.diffs, preview.issues)
        self.availabilityStateChanged.emit()

    def _set_combined_preview(self, preview: CourseSurveyPreview) -> None:
        self._combined_preview = preview
        self._combined_issues = [
            {
                "severity": issue.severity,
                "source": issue.source,
                "row": issue.row,
                "personName": issue.person_name,
                "message": issue.message,
                "resolution": issue.resolution,
                "canMarkTrial": issue.source == "生徒回答" and "基本情報にない" in issue.message,
                "markedTrial": issue.row in self._combined_trial_student_rows,
            }
            for issue in preview.issues
        ]
        self._combined_summary = {
            "studentCount": len(preview.students),
            "teacherCount": len(preview.teachers),
            "errorCount": sum(issue.severity == "error" for issue in preview.issues),
            "warningCount": sum(issue.severity == "warning" for issue in preview.issues),
        }
        self.availabilityStateChanged.emit()

    def _set_group_preview(self, preview: GroupImportPreview) -> None:
        self._group_preview = preview
        self._group_import_diffs = [
            {
                "operation": row.operation,
                "groupCode": row.group_code,
                "date": row.day.isoformat(),
                "slotCode": "",
                "before": row.before,
                "after": row.after,
                "message": row.message,
            }
            for row in preview.diffs
        ]
        self._group_import_issues = [_issue_dict(issue) for issue in preview.issues]
        self._group_import_summary = _summary(preview.diffs, preview.issues)
        self.groupStateChanged.emit()

    def _set_validation_issues(
        self,
        issues: tuple[ValidationIssueDto, ...],
    ) -> None:
        self._validation_issues = [
            {
                "id": issue.id,
                "severity": issue.severity,
                "type": issue.issue_type,
                "entityType": issue.entity_type,
                "entityId": issue.entity_id or "",
                "message": issue.message,
                "details": issue.details,
            }
            for issue in issues
            if not issue.resolved
        ]
        self._update_validation_summary()
        self.validationStateChanged.emit()

    def _update_validation_summary(self) -> None:
        error_count = sum(row["severity"] == "error" for row in self._validation_issues)
        warning_count = sum(row["severity"] == "warning" for row in self._validation_issues)
        info_count = sum(row["severity"] == "info" for row in self._validation_issues)
        self._validation_summary = {
            "errorCount": error_count,
            "warningCount": warning_count,
            "infoCount": info_count,
            "canOptimize": self._validation_has_run and error_count == 0,
        }

    def _refresh_group_lessons(self) -> None:
        self._group_lessons = [
            {
                "id": row.id,
                "groupCode": row.group_code,
                "grade": row.grade,
                "subjectName": row.subject_name,
                "courseName": row.course_name,
                "date": row.day.isoformat(),
                "startTime": row.start_time.strftime("%H:%M"),
                "endTime": row.end_time.strftime("%H:%M"),
                "teacherName": row.teacher_name,
                "room": row.room,
                "note": row.note,
                "studentCount": row.student_count,
            }
            for row in self._groups.list_group_lessons()
        ]

    def _refresh_group_options(self) -> None:
        options = self._groups.calendar_options()
        self._group_dates = list(options["dates"])
        self._group_subjects = list(options["subjects"])
        self._group_teachers = list(options["teachers"])
        self._group_slots = list(options["slots"])

    def _refresh_validation_after_data_change(self) -> None:
        self._validation_has_run = False
        self._set_validation_issues(self._validation.list_issues())

    def _refresh_stored_source_name(self) -> None:
        if self._projects.current is None:
            self._stored_source_name = ""
            return
        self._stored_source_name = self._availability.latest_source_name(self._import_kind)

    def _reset_availability_source(self, *, keep_kind: bool) -> None:
        if not keep_kind:
            self._import_kind = "student"
        self._source_path = ""
        self._source_sheets = []
        self._selected_sheet = ""
        self._source_encoding = "auto"
        self._source_headers = []
        self._mapping_fields = []
        self._mapping = {}
        self._source_preview_rows = []
        self._clear_availability_preview()

    def _clear_availability_preview(self) -> None:
        self._availability_preview = None
        self._import_diffs = []
        self._import_issues = []
        self._import_summary = _empty_summary()

    def _clear_combined_preview(self) -> None:
        self._combined_preview = None
        self._combined_issues = []
        self._combined_summary = {
            "studentCount": 0,
            "teacherCount": 0,
            "errorCount": 0,
            "warningCount": 0,
        }

    def _clear_group_preview(self) -> None:
        self._group_preview = None
        self._group_import_diffs = []
        self._group_import_issues = []
        self._group_import_summary = _empty_summary()

    def _perform(self, action: Callable[[], None], success_message: str) -> bool:
        self._clear_messages()
        try:
            action()
        except (
            AvailabilityImportError,
            GroupLessonImportError,
            ProjectFileError,
            OSError,
            ValueError,
        ) as exc:
            logger.warning(
                "Phase 3操作を完了できませんでした（%s）",
                type(exc).__name__,
            )
            self._set_error(str(exc))
            return False
        except Exception as exc:
            logger.error(
                "Phase 3操作で予期しないエラーが発生しました（%s、発生箇所: %s）",
                type(exc).__name__,
                _safe_traceback(exc),
            )
            self._set_error("処理を完了できませんでした。ローカルログを確認してください")
            return False
        if success_message:
            self._set_status(success_message)
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


def _empty_summary() -> dict[str, int]:
    return {
        "addCount": 0,
        "changeCount": 0,
        "unchangedCount": 0,
        "deleteCandidateCount": 0,
        "errorCount": 0,
        "warningCount": 0,
    }


def _safe_traceback(exc: BaseException) -> str:
    """例外値を記録せず、診断に必要なコード位置だけを返す。

    例外メッセージには入力ファイルの絶対パスや取込み値が含まれ得るため、
    ローカルログへは出さない。tracebackのファイル名もbasenameに限定する。
    """
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "取得不能"
    return " <- ".join(
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames
    )


def _summary(
    diffs: Sequence[AvailabilityDiffDto | GroupLessonDiffDto],
    issues: Sequence[ImportIssueDto],
) -> dict[str, int]:
    operations = [row.operation for row in diffs]
    return {
        "addCount": operations.count("add"),
        "changeCount": operations.count("change"),
        "unchangedCount": operations.count("unchanged"),
        "deleteCandidateCount": operations.count("delete_candidate"),
        "errorCount": sum(issue.severity == "error" for issue in issues),
        "warningCount": sum(issue.severity == "warning" for issue in issues),
    }


def _issue_dict(issue: ImportIssueDto) -> dict[str, object]:
    return {
        "severity": issue.severity,
        "code": issue.code,
        "sheet": issue.sheet,
        "row": "" if issue.row is None else issue.row,
        "column": issue.column,
        "message": issue.message,
    }


def _path_from_qml(value: str) -> Path:
    stripped = value.strip()
    if not stripped:
        raise ValueError("ファイルを選択してください")
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


def _qml_scalar(value: object) -> object:
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    return value


__all__ = ["Phase3ViewModel"]
