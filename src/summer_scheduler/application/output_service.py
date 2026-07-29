"""Phase 6のデータ再診断・レイアウト・ファイル出力を調停する。"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Final

from summer_scheduler.application.optimization_input_builder import (
    build_optimization_input,
)
from summer_scheduler.application.phase6_dto import (
    OutputDateOptionDto,
    OutputPersonOptionDto,
    OutputResultDto,
    OutputWorkspaceDto,
)
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.application.project_validation_service import (
    ProjectValidationService,
)
from summer_scheduler.infrastructure.exporting import CsvRenderer, ExcelRenderer
from summer_scheduler.infrastructure.exporting.pdf_renderer import QtPdfRenderer
from summer_scheduler.infrastructure.repositories import OutputRepository
from summer_scheduler.optimization.candidates import generate_candidates
from summer_scheduler.optimization.dto import (
    CandidateGenerationResult,
    OptimizationInput,
    OptimizationSettings,
)
from summer_scheduler.optimization.result_validation import validate_optimization_result
from summer_scheduler.reporting.builder import ReportKind, build_report_document
from summer_scheduler.reporting.common import format_day
from summer_scheduler.reporting.data import (
    DEFAULT_OUTPUT_SELECTION,
    OutputSelection,
    OutputSnapshot,
)
from summer_scheduler.reporting.layout import LayoutDocument
from summer_scheduler.reporting.settings import OutputSettings, OutputSettingsDefaults
from summer_scheduler.reporting.unassigned_builder import (
    build_current_result,
    build_unassigned_records,
)
from summer_scheduler.shared.settings import OptimizationAppSettings

_REPORT_NAMES: Final = {
    "overall": "夏期講習時間割",
    "students": "生徒別時間割",
    "teachers": "講師別時間割",
    "issues": "未配置・警告一覧",
    "raw": "割当て生データ",
}
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class OutputServiceError(RuntimeError):
    """Phase 6ユースケースを安全に完了できない。"""


class OutputDataIntegrityError(OutputServiceError):
    """現在の時間割にハード制約違反または参照不整合がある。"""


@dataclass(frozen=True, slots=True)
class _PreparedOutput:
    project_id: int
    snapshot: OutputSnapshot
    settings: OutputSettings
    optimization_input: OptimizationInput
    generation: CandidateGenerationResult


class OutputService:
    """出力直前に現在DBを再検証し、rendererへORMを渡さない。"""

    def __init__(
        self,
        projects: ProjectService,
        optimization_settings: OptimizationAppSettings,
        *,
        output_defaults: OutputSettingsDefaults | None = None,
    ) -> None:
        self._projects = projects
        self._optimization_settings = optimization_settings
        self._output_defaults = output_defaults
        self._validation = ProjectValidationService(projects)
        self._lock = RLock()
        self._cache: _PreparedOutput | None = None

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None

    def load_workspace(self, *, refresh: bool = True) -> OutputWorkspaceDto:
        prepared = self._prepare(refresh=refresh)
        snapshot = prepared.snapshot
        return OutputWorkspaceDto(
            project_id=prepared.project_id,
            project_title=snapshot.project.title,
            campus_name=snapshot.project.campus_name,
            settings=prepared.settings,
            dates=tuple(
                OutputDateOptionDto(
                    value=row.day,
                    label=format_day(row.day) + ("" if row.is_open else " [休校]"),
                    is_open=row.is_open,
                )
                for row in snapshot.dates
            ),
            teachers=tuple(
                OutputPersonOptionDto(
                    id=row.id,
                    label=row.name,
                    secondary_text=row.external_id,
                )
                for row in snapshot.teachers
            ),
            students=tuple(
                OutputPersonOptionDto(
                    id=row.id,
                    label=row.name,
                    secondary_text=f"{row.grade}／{row.external_id}",
                )
                for row in snapshot.students
            ),
            assignment_count=len(snapshot.assignments),
            group_lesson_count=len(snapshot.group_lessons),
            unassigned_count=sum(row.missing_sessions for row in snapshot.unassigned),
            warning_count=sum(row.status == "未対応" for row in snapshot.warnings),
        )

    def save_settings(self, settings: OutputSettings) -> OutputSettings:
        project = self._projects.require_project()
        if settings.project_id != project.project_id:
            raise OutputServiceError("別プロジェクトの出力設定は保存できません")
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            saved = OutputRepository(session).upsert_settings(settings)
        with self._lock:
            if self._cache is not None and self._cache.project_id == project.project_id:
                self._cache = replace(self._cache, settings=saved)
        return saved

    def build_document(
        self,
        kind: ReportKind,
        selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
        *,
        settings_override: OutputSettings | None = None,
    ) -> LayoutDocument:
        prepared = self._prepare(refresh=False)
        settings = self._effective_settings(prepared, settings_override)
        return build_report_document(kind, prepared.snapshot, settings, selection)

    def export_excel(
        self,
        kind: ReportKind,
        destination: Path,
        selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
        *,
        settings_override: OutputSettings | None = None,
        overwrite: bool = False,
    ) -> OutputResultDto:
        prepared = self._prepare(refresh=True)
        settings = self._effective_settings(prepared, settings_override)
        document = build_report_document(kind, prepared.snapshot, settings, selection)
        path = ExcelRenderer(settings.style_rules).render(
            document,
            destination,
            overwrite=overwrite,
        )
        return OutputResultDto(
            kind=kind,
            format="xlsx",
            path=path,
            page_count_optional=document.page_count,
            record_count=self._record_count(prepared.snapshot, kind, selection),
        )

    def export_pdf(
        self,
        kind: ReportKind,
        destination: Path,
        selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
        *,
        settings_override: OutputSettings | None = None,
        overwrite: bool = False,
    ) -> OutputResultDto:
        prepared = self._prepare(refresh=True)
        settings = self._effective_settings(prepared, settings_override)
        document = build_report_document(kind, prepared.snapshot, settings, selection)
        path = QtPdfRenderer().render(
            document,
            settings,
            destination,
            overwrite=overwrite,
        )
        return OutputResultDto(
            kind=kind,
            format="pdf",
            path=path,
            page_count_optional=document.page_count,
            record_count=self._record_count(prepared.snapshot, kind, selection),
        )

    def export_csv(
        self,
        destination: Path,
        selection: OutputSelection = DEFAULT_OUTPUT_SELECTION,
        *,
        settings_override: OutputSettings | None = None,
        overwrite: bool = False,
    ) -> OutputResultDto:
        prepared = self._prepare(refresh=True)
        settings = self._effective_settings(prepared, settings_override)
        path = CsvRenderer().render(
            prepared.snapshot,
            destination,
            selection=selection,
            with_bom=settings.csv_with_bom,
            overwrite=overwrite,
        )
        return OutputResultDto(
            kind="raw",
            format="csv",
            path=path,
            page_count_optional=None,
            record_count=self._record_count(prepared.snapshot, "raw", selection),
        )

    def suggested_filename(
        self,
        kind: ReportKind | str,
        extension: str,
        *,
        settings_override: OutputSettings | None = None,
    ) -> str:
        prepared = self._prepare(refresh=False)
        settings = self._effective_settings(prepared, settings_override)
        report_name = _REPORT_NAMES.get(kind)
        if report_name is None:
            raise OutputServiceError(f"未対応の出力種別です: {kind}")
        stem = settings.file_name_pattern.format(
            project=prepared.snapshot.project.title,
            report=report_name,
            date=prepared.snapshot.project.generated_at.astimezone().strftime("%Y%m%d"),
        )
        safe_stem = _safe_filename_stem(stem)
        suffix = extension if extension.startswith(".") else f".{extension}"
        return f"{safe_stem}{suffix.casefold()}"

    def _prepare(self, *, refresh: bool) -> _PreparedOutput:
        project = self._projects.require_project()
        with self._lock:
            if (
                not refresh
                and self._cache is not None
                and self._cache.project_id == project.project_id
            ):
                return self._cache
            # 警告一覧を古い保存結果に依存させない。現在状態を再検査してから読む。
            self._validation.run_validation()
            database = self._projects.require_database()
            with database.session_factory() as session:
                repository = OutputRepository(session)
                snapshot = repository.build_base_snapshot(
                    project.project_id,
                    generated_at=datetime.now(UTC),
                )
                settings = repository.get_settings(
                    project.project_id,
                    defaults=self._output_defaults,
                )
                optimization_input = build_optimization_input(
                    session=session,
                    project_id=project.project_id,
                    settings=_solver_settings(self._optimization_settings),
                )
                generation = generate_candidates(optimization_input)
            current_result = build_current_result(
                snapshot,
                optimization_input,
                generation,
            )
            validation = validate_optimization_result(
                optimization_input,
                generation,
                current_result,
            )
            if not validation.is_valid:
                codes = "、".join(
                    dict.fromkeys(row.code.value for row in validation.violations[:5])
                )
                raise OutputDataIntegrityError(
                    "現在の時間割にハード制約違反または参照不整合があるため出力できません。"
                    f"時間割を確認してください（{codes}）"
                )
            snapshot = replace(
                snapshot,
                unassigned=build_unassigned_records(
                    snapshot,
                    optimization_input,
                    generation,
                ),
            )
            prepared = _PreparedOutput(
                project_id=project.project_id,
                snapshot=snapshot,
                settings=settings,
                optimization_input=optimization_input,
                generation=generation,
            )
            self._cache = prepared
            return prepared

    @staticmethod
    def _effective_settings(
        prepared: _PreparedOutput,
        override: OutputSettings | None,
    ) -> OutputSettings:
        settings = override or prepared.settings
        if settings.project_id != prepared.project_id:
            raise OutputServiceError("別プロジェクトの出力設定は使用できません")
        settings.validate()
        return settings

    @staticmethod
    def _record_count(
        snapshot: OutputSnapshot,
        kind: ReportKind | str,
        selection: OutputSelection,
    ) -> int:
        allowed_dates = set(selection.dates)
        allowed_teachers = set(selection.teacher_ids)
        allowed_students = set(selection.student_ids)
        requests = {row.id: row for row in snapshot.lesson_requests}
        assignments = tuple(
            row
            for row in snapshot.assignments
            if (not allowed_dates or row.day in allowed_dates)
            and (not allowed_teachers or row.teacher_id in allowed_teachers)
            and (
                not allowed_students
                or requests[row.lesson_request_id].student_id in allowed_students
            )
        )
        groups = tuple(
            row
            for row in snapshot.group_lessons
            if (not allowed_dates or row.day in allowed_dates)
            and (not allowed_teachers or row.teacher_id_optional in allowed_teachers)
            and (not allowed_students or bool(set(row.student_ids) & allowed_students))
        )
        if kind == "raw":
            group_rows = sum(
                (
                    len(set(row.student_ids) & allowed_students)
                    if allowed_students
                    else max(1, len(row.student_ids))
                )
                for row in groups
            )
            return len(assignments) + group_rows
        if kind == "issues":
            unassigned_count = sum(
                (not allowed_students or row.student_id in allowed_students)
                and (not allowed_teachers or row.regular_teacher_id_optional in allowed_teachers)
                for row in snapshot.unassigned
            )
            teacher_names = {row.name for row in snapshot.teachers if row.id in allowed_teachers}
            student_names = {row.name for row in snapshot.students if row.id in allowed_students}
            warning_count = sum(
                (not allowed_dates or row.day_optional is None or row.day_optional in allowed_dates)
                and (
                    not allowed_teachers
                    or (
                        row.teacher_id_optional in allowed_teachers
                        if row.teacher_id_optional is not None
                        else not row.teacher_name or row.teacher_name in teacher_names
                    )
                )
                and (
                    not allowed_students
                    or (
                        bool(set(row.student_ids) & allowed_students)
                        if row.student_ids
                        else not row.student_name or row.student_name in student_names
                    )
                )
                for row in snapshot.warnings
            )
            return unassigned_count + warning_count
        return len(assignments) + len(groups)


def _solver_settings(source: OptimizationAppSettings) -> OptimizationSettings:
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


def _safe_filename_stem(value: str) -> str:
    sanitized = _INVALID_FILENAME.sub("_", value).strip().rstrip(" .")
    if not sanitized:
        raise OutputServiceError("ファイル名規則から有効なファイル名を作成できません")
    # Windowsは ``CON.foo`` のように予約デバイス名へ拡張子を付けた名前も
    # ファイルとして扱えない。最初のdotより前を、Windowsが無視する末尾空白も
    # 除いて判定する。
    windows_base_name = sanitized.partition(".")[0].rstrip(" ").upper()
    if windows_base_name in _WINDOWS_RESERVED:
        sanitized = f"_{sanitized}"
    return sanitized[:180].rstrip(" .")


__all__ = [
    "OutputDataIntegrityError",
    "OutputService",
    "OutputServiceError",
]
