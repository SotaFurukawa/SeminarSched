"""Phase 3 の生徒・講師可用性ファイルを安全に取り込む Application Service.

QML からはこのサービスだけを呼び出し、ファイル形式、ORM、transaction の詳細を
画面に漏らさない。可用性は生徒/講師単位のデータである一方、受講科目は生徒の
``LessonRequest`` に紐付くため、生徒用ファイルの科目・希望講師は同じ行で検証し、
希望講師だけを更新する。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal, cast

from summer_scheduler.application.phase3_dto import (
    AvailabilityDiffDto,
    AvailabilityImportPreview,
    AvailabilityKind,
    AvailabilityRow,
    ImportApplyResult,
    ImportIssueDto,
)
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.infrastructure.db.models import (
    AuditLog,
    ImportBatch,
    ImportSourceSnapshot,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TimeSlot,
)
from summer_scheduler.infrastructure.importing import (
    CsvEncoding,
    ImportIssue,
    ImportSchema,
    MappingResult,
    SourceInspection,
    map_table,
    preview_source_table,
    read_source_table,
    student_availability_schema,
    suggest_column_mapping,
    teacher_availability_schema,
    write_student_availability_template,
    write_teacher_availability_template,
)
from summer_scheduler.infrastructure.importing import (
    inspect_source as inspect_import_source,
)
from summer_scheduler.infrastructure.repositories.master_repository import MasterRepository

_IMPORT_TYPES: Final[dict[AvailabilityKind, str]] = {
    "student": "student_availability",
    "teacher": "teacher_availability",
}
_PROTECTED_HEADER_MARKERS: Final[tuple[str, ...]] = (
    "通常担当",
    "regular_teacher",
    "priority5",
    "優先度5",
    "1対1",
    "１対１",
    "one_to_one",
)

_AvailabilityEntity = Student | Teacher


@dataclass(frozen=True, slots=True)
class AvailabilitySourceInspection:
    """UI 向けに種別も保持した入力元の調査結果。"""

    kind: AvailabilityKind
    source: SourceInspection
    selected_sheet: str
    headers: tuple[str, ...]
    preview_rows: tuple[Mapping[str, object], ...]
    suggested_mapping: Mapping[str, str]
    mapping_fields: tuple[tuple[str, str, bool], ...]
    encoding: str


class AvailabilityImportError(ValueError):
    """エラーを含むプレビューを適用しようとした場合の明示的な失敗。"""


class AvailabilityImportService:
    """可用性ファイルの確認、差分表示、明示的な反映を提供する。"""

    def __init__(self, projects: ProjectService) -> None:
        self._projects = projects

    def inspect_source(
        self,
        kind: AvailabilityKind,
        path: Path,
        *,
        encoding: str = "auto",
        sheet_name: str | None = None,
    ) -> AvailabilitySourceInspection:
        """ファイル種別、シート、CSV 文字コードを非破壊で検査する。

        ``sheet_name`` は CSV では使わず、xlsx では利用者が選べることを UI 契約に
        残す。選択値の妥当性は ``prepare_import`` 時に reader が検証する。
        """
        import_kind = self._kind(kind)
        requested_encoding = _encoding(encoding)
        source = inspect_import_source(path, csv_encoding=requested_encoding)
        selected_sheet = sheet_name or source.sheets[0].name
        table = preview_source_table(
            path,
            sheet_name=selected_sheet,
            csv_encoding=requested_encoding,
            row_limit=20,
        )
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            slot_codes = tuple(
                slot.code
                for slot in repository.list_time_slots(
                    project_id=project_id,
                    enabled_only=True,
                )
            )
            schema = self._schema(import_kind, slot_codes)
            suggested = dict(suggest_column_mapping(schema, table.headers))
            saved = self._saved_mapping(repository, project_id, import_kind)
            if saved is not None and set(saved.values()).issubset(table.headers):
                suggested = saved
        return AvailabilitySourceInspection(
            kind=import_kind,
            source=source,
            selected_sheet=table.sheet_name,
            headers=table.headers,
            preview_rows=tuple(row.raw_values for row in table.rows),
            suggested_mapping=suggested,
            mapping_fields=tuple(
                (field.key, field.label, field.required)
                for field in schema.fields
                if field.key != "example"
            ),
            encoding=(table.detected_encoding or requested_encoding).value,
        )

    def export_student_template(self, path: Path) -> None:
        students, teachers, subjects = self._template_master_references()
        write_student_availability_template(
            path,
            self._slot_codes(),
            reference_students=students,
            reference_teachers=teachers,
            reference_subjects=subjects,
        )

    def export_teacher_template(self, path: Path) -> None:
        students, teachers, subjects = self._template_master_references()
        write_teacher_availability_template(
            path,
            self._slot_codes(),
            reference_students=students,
            reference_teachers=teachers,
            reference_subjects=subjects,
        )

    def latest_source_name(self, kind: AvailabilityKind) -> str:
        """プロジェクト内へ保持している直近アンケート原本名を返す。"""
        import_kind = self._kind(kind)
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            snapshot = MasterRepository(session).get_import_source_snapshot(
                project_id=project_id,
                import_type=_IMPORT_TYPES[import_kind],
            )
            return snapshot.source_file_name if snapshot is not None else ""

    def _template_master_references(
        self,
    ) -> tuple[
        tuple[Mapping[str, object], ...],
        tuple[Mapping[str, object], ...],
        tuple[Mapping[str, object], ...],
    ]:
        """テンプレートへ同梱する有効なマスターの表示用snapshotを返す。"""
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            students = tuple(
                {
                    "external_id": student.external_id,
                    "name": student.name,
                    "grade": student.grade,
                }
                for student in repository.list_students(active_only=True)
            )
            teachers = tuple(
                {"external_id": teacher.external_id, "name": teacher.name}
                for teacher in repository.list_teachers(active_only=True)
            )
            subjects = tuple(
                {"code": subject.code, "display_name": subject.display_name}
                for subject in repository.list_subjects(active_only=True)
            )
        return students, teachers, subjects

    def prepare_import(
        self,
        kind: AvailabilityKind,
        path: Path,
        *,
        sheet_name: str | None = None,
        encoding: str = "auto",
        mapping: Mapping[str, str] | None = None,
    ) -> AvailabilityImportPreview:
        """入力を読み、参照整合性を検査してセル単位の差分を返す。

        未指定の mapping は同じ project / import type の直近成功取込で保存した
        mapping を優先し、現在のヘッダに合わなければ importing 層の自動対応付けに
        委ねる。検証エラーがあってもプレビューは返し、適用だけを拒否する。
        """
        import_kind = self._kind(kind)
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            slots = repository.list_time_slots(project_id=project_id, enabled_only=True)
            schema = self._schema(import_kind, tuple(slot.code for slot in slots))
            source_table = read_source_table(
                path,
                sheet_name=sheet_name,
                csv_encoding=_encoding(encoding),
            )
            saved_mapping = self._saved_mapping(repository, project_id, import_kind)
            selected_mapping = (
                dict(mapping)
                if mapping is not None
                else (
                    saved_mapping
                    if saved_mapping is not None
                    and set(saved_mapping.values()).issubset(source_table.headers)
                    else None
                )
            )
            mapped = map_table(source_table, schema, selected_mapping)
            return self._preview_from_mapping(
                repository,
                project_id=project_id,
                kind=import_kind,
                path=source_table.source_path,
                sheet_name=source_table.sheet_name,
                encoding=(
                    source_table.detected_encoding.value
                    if source_table.detected_encoding is not None
                    else None
                ),
                mapped=mapped,
                slots_by_code={slot.code: slot for slot in slots},
            )

    def apply_import(
        self,
        preview: AvailabilityImportPreview,
        *,
        include_deletes: bool = False,
    ) -> ImportApplyResult:
        """ファイルを再読込・再検証し、可用性と希望講師を一つの transaction で反映する。"""
        current_project = self._projects.require_project()
        if preview.project_id != current_project.project_id:
            raise AvailabilityImportError("別のプロジェクトで作成したプレビューは適用できません。")
        if preview.has_errors:
            raise AvailabilityImportError("検証エラーがあるため、可用性を取り込めません。")

        checked = self.prepare_import(
            preview.kind,
            preview.source_path,
            sheet_name=preview.sheet_name or None,
            encoding=preview.encoding or "auto",
            mapping=preview.mapping,
        )
        if not _availability_previews_match(preview, checked):
            raise AvailabilityImportError(
                "プレビュー後に入力ファイルまたはプロジェクトが変更されました。"
                "再度検証して差分を確認してください。"
            )
        if checked.has_errors:
            raise AvailabilityImportError("検証エラーがあるため、可用性を取り込めません。")

        try:
            source_content = checked.source_path.read_bytes()
        except OSError as exc:
            raise AvailabilityImportError(
                "アンケート原本をプロジェクト内へ保存できませんでした。"
            ) from exc
        source_hash = sha256(source_content).hexdigest()

        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            added = changed = unchanged = deleted = 0
            for diff in checked.diffs:
                if diff.operation == "delete_candidate":
                    if include_deletes:
                        deleted += int(
                            self._delete_cell(repository, checked.kind, checked.project_id, diff)
                        )
                    continue
                if diff.operation == "add":
                    added += 1
                elif diff.operation == "change":
                    changed += 1
                else:
                    unchanged += 1
                self._upsert_cell(repository, checked.kind, checked.project_id, diff)

            if checked.kind == "student":
                self._apply_student_preferences(repository, checked)

            batch = repository.create_import_batch(
                ImportBatch(
                    project_id=checked.project_id,
                    import_type=_IMPORT_TYPES[checked.kind],
                    source_file_name=checked.source_path.name,
                    row_count=len(checked.rows),
                    success_count=len(checked.rows),
                    warning_count=sum(issue.severity == "warning" for issue in checked.issues),
                    error_count=0,
                    mapping_json=json.dumps(
                        {
                            "mapping": checked.mapping,
                            "sheet_name": checked.sheet_name,
                            "encoding": checked.encoding,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
            repository.replace_import_source_snapshot(
                ImportSourceSnapshot(
                    project_id=checked.project_id,
                    import_type=_IMPORT_TYPES[checked.kind],
                    source_file_name=checked.source_path.name,
                    content=source_content,
                    sha256=source_hash,
                    size_bytes=len(source_content),
                    imported_at=datetime.now(UTC),
                )
            )
            repository.create_audit_log(
                AuditLog(
                    project_id=checked.project_id,
                    action="availability_imported",
                    entity_type=checked.kind + "_availability",
                    entity_id=str(batch.id),
                    before_json=None,
                    after_json=json.dumps(
                        {
                            "added": added,
                            "changed": changed,
                            "unchanged": unchanged,
                            "deleted": deleted,
                            "source_file_name": checked.source_path.name,
                            "source_sha256": source_hash,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
            return ImportApplyResult(
                batch_id=batch.id,
                added=added,
                changed=changed,
                unchanged=unchanged,
                deleted=deleted,
                warnings=sum(issue.severity == "warning" for issue in checked.issues),
            )

    def _preview_from_mapping(
        self,
        repository: MasterRepository,
        *,
        project_id: int,
        kind: AvailabilityKind,
        path: Path,
        sheet_name: str,
        encoding: str | None,
        mapped: MappingResult,
        slots_by_code: Mapping[str, TimeSlot],
    ) -> AvailabilityImportPreview:
        issues = [_dto_issue(issue) for issue in mapped.issues]
        rows: list[AvailabilityRow] = []
        entity_by_external: dict[str, _AvailabilityEntity | None] = {}
        subject_by_code: dict[str, Subject | None] = {}
        seen_preferences: dict[tuple[int, int], tuple[int | None, int | None, int | None]] = {}
        project = repository.get_project(project_id)
        if project is None:
            raise ProjectFileError("プロジェクトが見つかりません。")
        open_dates = {
            row.date: row.is_open for row in repository.list_open_dates(project_id=project_id)
        }

        for normalized in mapped.rows:
            values = normalized.values
            source_row = normalized.row_number
            self._protected_column_issues(normalized.raw_values, source_row, sheet_name, issues)
            external_id_key = "student_id" if kind == "student" else "teacher_id"
            name_key = "student_name" if kind == "student" else "name"
            external_id = _required_text(values.get(external_id_key))
            entity = entity_by_external.get(external_id)
            if entity is None and external_id:
                entity = (
                    repository.get_student_by_external_id(external_id)
                    if kind == "student"
                    else repository.get_teacher_by_external_id(external_id)
                )
                entity_by_external[external_id] = entity
            if entity is None:
                issues.append(
                    _error(
                        "unknown_id", "未登録のIDです。", sheet_name, source_row, external_id_key
                    )
                )
                continue
            supplied_name = _required_text(values.get(name_key))
            if supplied_name != entity.name:
                issues.append(
                    _error(
                        "name_mismatch",
                        "IDと氏名が一致しません。",
                        sheet_name,
                        source_row,
                        name_key,
                    )
                )
            if not entity.active:
                issues.append(
                    _error(
                        "inactive_entity",
                        "無効なIDは取り込めません。",
                        sheet_name,
                        source_row,
                        external_id_key,
                    )
                )

            day = values.get("date")
            if not isinstance(day, date):
                continue
            if day < project.start_date or day > project.end_date:
                issues.append(
                    _error(
                        "outside_project_period",
                        "プロジェクト期間外の日付です。",
                        sheet_name,
                        source_row,
                        "date",
                    )
                )
            elif not open_dates.get(day, False):
                issues.append(
                    _error(
                        "closed_date",
                        "休校日には可用性を登録できません。",
                        sheet_name,
                        source_row,
                        "date",
                    )
                )

            slot_levels: dict[str, int] = {}
            for slot_code in slots_by_code:
                value = values.get(f"slot:{slot_code}")
                if isinstance(value, int) and value in {0, 1, 2}:
                    slot_levels[slot_code] = value
                elif value is not None:
                    issues.append(
                        _error(
                            "invalid_availability",
                            "可用性は 0、1、2 のいずれかです。",
                            sheet_name,
                            source_row,
                            f"slot:{slot_code}",
                        )
                    )
            if len(slot_levels) != len(slots_by_code):
                continue

            subject_code: str | None = None
            preferences: tuple[int | None, int | None, int | None] = (None, None, None)
            preference_fields_supplied = (False, False, False)
            if kind == "student":
                subject_code = _required_text(values.get("subject_code"))
                subject = subject_by_code.get(subject_code)
                if subject is None and subject_code:
                    subject = repository.get_subject_by_code(subject_code)
                    subject_by_code[subject_code] = subject
                if subject is None or not subject.active:
                    issues.append(
                        _error(
                            "unknown_subject",
                            "未登録または無効な科目です。",
                            sheet_name,
                            source_row,
                            "subject_code",
                        )
                    )
                else:
                    lesson_request = repository.get_lesson_request_by_student_subject(
                        project_id=project_id,
                        student_id=entity.id,
                        subject_id=subject.id,
                    )
                    if lesson_request is None:
                        issues.append(
                            _error(
                                "missing_lesson_request",
                                "この生徒・科目の受講希望がありません。",
                                sheet_name,
                                source_row,
                                "subject_code",
                            )
                        )
                    preferences = self._teacher_preferences(
                        repository,
                        values,
                        subject.id,
                        source_row,
                        sheet_name,
                        issues,
                    )
                    preference_fields_supplied = cast(
                        tuple[bool, bool, bool],
                        tuple(
                            f"preferred_teacher_{position}" in values for position in range(1, 4)
                        ),
                    )
                    if lesson_request is not None:
                        key = (entity.id, subject.id)
                        previous = seen_preferences.get(key)
                        if previous is not None and previous != preferences:
                            issues.append(
                                _error(
                                    "conflicting_preferences",
                                    "同一生徒・科目の希望講師が日付間で矛盾しています。",
                                    sheet_name,
                                    source_row,
                                    "preferred_teacher_1",
                                )
                            )
                        seen_preferences[key] = preferences

            rows.append(
                AvailabilityRow(
                    source_row=source_row,
                    external_id=external_id,
                    name=entity.name,
                    day=day,
                    slot_levels=slot_levels,
                    subject_code=subject_code,
                    preferred_teacher_ids=(
                        _external_teacher_id(repository, preferences[0]),
                        _external_teacher_id(repository, preferences[1]),
                        _external_teacher_id(repository, preferences[2]),
                    ),
                    preferred_teacher_fields_supplied=preference_fields_supplied,
                    note=_optional_text(values.get("note")) or "",
                )
            )

        diffs = self._diffs(repository, project_id, kind, rows, entity_by_external, slots_by_code)
        return AvailabilityImportPreview(
            project_id=project_id,
            kind=kind,
            source_path=path,
            sheet_name=sheet_name,
            encoding=encoding,
            mapping=dict(mapped.applied_mapping),
            rows=tuple(rows),
            diffs=tuple(diffs),
            issues=tuple(issues),
        )

    def _diffs(
        self,
        repository: MasterRepository,
        project_id: int,
        kind: AvailabilityKind,
        rows: list[AvailabilityRow],
        entity_by_external: Mapping[str, _AvailabilityEntity | None],
        slots_by_code: Mapping[str, TimeSlot],
    ) -> list[AvailabilityDiffDto]:
        incoming: dict[tuple[int, date, int], tuple[str, str, int]] = {}
        for row in rows:
            entity = entity_by_external.get(row.external_id)
            if entity is None:
                continue
            for code, level in row.slot_levels.items():
                slot = slots_by_code[code]
                incoming[(entity.id, row.day, slot.id)] = (row.external_id, entity.name, level)
        existing: list[StudentAvailability] | list[TeacherAvailability] = (
            repository.list_student_availabilities(project_id=project_id)
            if kind == "student"
            else repository.list_teacher_availabilities(project_id=project_id)
        )
        result: list[AvailabilityDiffDto] = []
        existing_keys: set[tuple[int, date, int]] = set()
        for stored in existing:
            entity_id = (
                stored.student_id if isinstance(stored, StudentAvailability) else stored.teacher_id
            )
            key = (entity_id, stored.date, stored.time_slot_id)
            existing_keys.add(key)
            incoming_value = incoming.get(key)
            if incoming_value is None:
                entity = _entity_by_id(repository, kind, entity_id)
                slot = _slot_by_id(slots_by_code, stored.time_slot_id)
                result.append(
                    AvailabilityDiffDto(
                        "delete_candidate",
                        entity_id,
                        entity.external_id,
                        entity.name,
                        stored.date,
                        stored.time_slot_id,
                        slot.code,
                        stored.availability_level,
                        None,
                        "ファイルにない既存セル",
                    )
                )
                continue
            external_id, name, level = incoming_value
            slot = _slot_by_id(slots_by_code, stored.time_slot_id)
            operation: Literal["add", "change", "unchanged", "delete_candidate"] = (
                "unchanged" if stored.availability_level == level else "change"
            )
            result.append(
                AvailabilityDiffDto(
                    operation,
                    entity_id,
                    external_id,
                    name,
                    stored.date,
                    stored.time_slot_id,
                    slot.code,
                    stored.availability_level,
                    level,
                    "可用性セル",
                )
            )
        for (entity_id, day, slot_id), (external_id, name, level) in incoming.items():
            if (entity_id, day, slot_id) in existing_keys:
                continue
            slot = _slot_by_id(slots_by_code, slot_id)
            result.append(
                AvailabilityDiffDto(
                    "add",
                    entity_id,
                    external_id,
                    name,
                    day,
                    slot_id,
                    slot.code,
                    None,
                    level,
                    "新しい可用性セル",
                )
            )
        return sorted(result, key=lambda item: (item.day, item.entity_id, item.time_slot_id))

    def _teacher_preferences(
        self,
        repository: MasterRepository,
        values: Mapping[str, object],
        subject_id: int,
        source_row: int,
        sheet_name: str,
        issues: list[ImportIssueDto],
    ) -> tuple[int | None, int | None, int | None]:
        ids: list[int | None] = []
        for position in range(1, 4):
            key = f"preferred_teacher_{position}"
            external_id = _optional_text(values.get(key))
            if external_id is None:
                ids.append(None)
                continue
            teacher = repository.get_teacher_by_external_id(external_id)
            if teacher is None or not teacher.active:
                issues.append(
                    _error(
                        "unknown_preferred_teacher",
                        "希望講師IDが未登録または無効です。",
                        sheet_name,
                        source_row,
                        key,
                    )
                )
                ids.append(None)
                continue
            qualifications = repository.list_teacher_qualifications(
                teacher_id=teacher.id,
                subject_id=subject_id,
            )
            if not any(row.can_teach for row in qualifications):
                issues.append(
                    _error(
                        "unqualified_preferred_teacher",
                        "希望講師はこの科目を担当できません。",
                        sheet_name,
                        source_row,
                        key,
                    )
                )
            ids.append(teacher.id)
        return cast(tuple[int | None, int | None, int | None], tuple(ids))

    def _protected_column_issues(
        self,
        values: Mapping[str, object],
        source_row: int,
        sheet_name: str,
        issues: list[ImportIssueDto],
    ) -> None:
        for header, value in values.items():
            normalized = header.casefold().replace(" ", "").replace("_", "")
            if (
                any(
                    marker.casefold().replace("_", "") in normalized
                    for marker in _PROTECTED_HEADER_MARKERS
                )
                and _optional_text(value) is not None
            ):
                issues.append(
                    _error(
                        "protected_field",
                        "通常担当・優先度5・1対1必須は可用性取込で変更できません。",
                        sheet_name,
                        source_row,
                        header,
                    )
                )

    def _apply_student_preferences(
        self, repository: MasterRepository, preview: AvailabilityImportPreview
    ) -> None:
        # 同一生徒・科目の希望講師矛盾は prepare で拒否済み。ここでも source rows の
        # 最新状態を使用して LessonRequest を一度だけ更新する。
        seen: set[tuple[int, str]] = set()
        for row in preview.rows:
            if row.subject_code is None or not any(row.preferred_teacher_fields_supplied):
                continue
            student = repository.get_student_by_external_id(row.external_id)
            subject = repository.get_subject_by_code(row.subject_code)
            if student is None or subject is None:
                raise AvailabilityImportError("適用中に生徒または科目が見つかりません。")
            identity = (student.id, subject.code)
            if identity in seen:
                continue
            seen.add(identity)
            request = repository.get_lesson_request_by_student_subject(
                project_id=preview.project_id,
                student_id=student.id,
                subject_id=subject.id,
            )
            if request is None:
                raise AvailabilityImportError("適用中に受講希望が見つかりません。")
            current_teacher_ids = [
                request.preferred_teacher_1_id_optional,
                request.preferred_teacher_2_id_optional,
                request.preferred_teacher_3_id_optional,
            ]
            teacher_ids: list[int | None] = []
            for index, external_id in enumerate(row.preferred_teacher_ids):
                if not row.preferred_teacher_fields_supplied[index]:
                    teacher_ids.append(current_teacher_ids[index])
                    continue
                teacher = (
                    repository.get_teacher_by_external_id(external_id)
                    if external_id is not None
                    else None
                )
                teacher_ids.append(teacher.id if teacher is not None else None)
            repository.update_lesson_request(
                request,
                preferred_teacher_1_id_optional=teacher_ids[0],
                preferred_teacher_2_id_optional=teacher_ids[1],
                preferred_teacher_3_id_optional=teacher_ids[2],
            )

    @staticmethod
    def _upsert_cell(
        repository: MasterRepository,
        kind: AvailabilityKind,
        project_id: int,
        diff: AvailabilityDiffDto,
    ) -> None:
        if diff.after is None:
            raise AvailabilityImportError("削除候補を可用性として保存できません。")
        if kind == "student":
            repository.upsert_student_availability(
                project_id=project_id,
                student_id=diff.entity_id,
                date_value=diff.day,
                time_slot_id=diff.time_slot_id,
                availability_level=diff.after,
            )
        else:
            repository.upsert_teacher_availability(
                project_id=project_id,
                teacher_id=diff.entity_id,
                date_value=diff.day,
                time_slot_id=diff.time_slot_id,
                availability_level=diff.after,
            )

    @staticmethod
    def _delete_cell(
        repository: MasterRepository,
        kind: AvailabilityKind,
        project_id: int,
        diff: AvailabilityDiffDto,
    ) -> bool:
        if kind == "student":
            return repository.delete_student_availability(
                project_id=project_id,
                student_id=diff.entity_id,
                date_value=diff.day,
                time_slot_id=diff.time_slot_id,
            )
        return repository.delete_teacher_availability(
            project_id=project_id,
            teacher_id=diff.entity_id,
            date_value=diff.day,
            time_slot_id=diff.time_slot_id,
        )

    def _slot_codes(self) -> tuple[str, ...]:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            return tuple(
                slot.code
                for slot in MasterRepository(session).list_time_slots(
                    project_id=project_id, enabled_only=True
                )
            )

    @staticmethod
    def _kind(kind: AvailabilityKind) -> AvailabilityKind:
        if kind not in _IMPORT_TYPES:
            raise ValueError("可用性取込種別は student または teacher を指定してください。")
        return kind

    @staticmethod
    def _schema(
        kind: AvailabilityKind,
        slot_codes: tuple[str, ...],
    ) -> ImportSchema:
        return (
            student_availability_schema(slot_codes)
            if kind == "student"
            else teacher_availability_schema(slot_codes)
        )

    @staticmethod
    def _saved_mapping(
        repository: MasterRepository, project_id: int, kind: AvailabilityKind
    ) -> dict[str, str] | None:
        latest = repository.get_latest_import_batch(
            project_id=project_id, import_type=_IMPORT_TYPES[kind]
        )
        if latest is None:
            return None
        try:
            mapping = json.loads(latest.mapping_json).get("mapping")
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return (
            dict(mapping)
            if isinstance(mapping, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items())
            else None
        )


def _encoding(value: str) -> CsvEncoding:
    try:
        return CsvEncoding(value.casefold())
    except ValueError as exc:
        raise ValueError("CSV文字コードは auto、utf-8、utf-8-sig、cp932 のいずれかです。") from exc


def _dto_issue(issue: ImportIssue) -> ImportIssueDto:
    return ImportIssueDto(
        issue.severity.value,
        issue.message,
        issue.code,
        issue.sheet_name or "",
        issue.row_number,
        issue.source_header or issue.column_key or "",
    )


def _error(code: str, message: str, sheet: str, row: int, column: str) -> ImportIssueDto:
    return ImportIssueDto("error", message, code, sheet, row, column)


def _required_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    text = _required_text(value)
    return text or None


def _external_teacher_id(
    repository: MasterRepository,
    teacher_id: int | None,
) -> str | None:
    if teacher_id is None:
        return None
    teacher = _entity_by_id(repository, "teacher", teacher_id)
    return teacher.external_id


def _entity_by_id(
    repository: MasterRepository,
    kind: AvailabilityKind,
    entity_id: int,
) -> _AvailabilityEntity:
    rows = repository.list_students() if kind == "student" else repository.list_teachers()
    for row in rows:
        if row.id == entity_id:
            return row
    raise AvailabilityImportError("可用性の参照先が見つかりません。")


def _slot_by_id(
    slots_by_code: Mapping[str, TimeSlot],
    slot_id: int,
) -> TimeSlot:
    for slot in slots_by_code.values():
        if slot.id == slot_id:
            return slot
    raise AvailabilityImportError("可用性のコマが見つかりません。")


def _availability_previews_match(
    expected: AvailabilityImportPreview,
    actual: AvailabilityImportPreview,
) -> bool:
    """利用者が確認した内容と適用直前の再検証結果が同じか判定する。"""
    return (
        expected.project_id == actual.project_id
        and expected.kind == actual.kind
        and expected.sheet_name == actual.sheet_name
        and expected.encoding == actual.encoding
        and expected.mapping == actual.mapping
        and expected.rows == actual.rows
        and expected.diffs == actual.diffs
        and expected.issues == actual.issues
    )


__all__ = [
    "AvailabilityImportError",
    "AvailabilityImportService",
    "AvailabilitySourceInspection",
]
