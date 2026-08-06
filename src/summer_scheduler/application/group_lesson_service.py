"""Phase 3 の集団授業テンプレート・取込みを扱う Application Service。

QML から SQLAlchemy や xlsx の詳細を直接扱わないための境界である。取込みは
必ずプレビュー、検証、明示確認、単一トランザクションでの反映という順に行う。
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, time
from pathlib import Path
from typing import Literal

from summer_scheduler.application.phase3_dto import (
    GroupImportPreview,
    GroupLessonDiffDto,
    GroupLessonDto,
    GroupLessonRow,
    ImportApplyResult,
    ImportIssueDto,
)
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.domain.time_ranges import time_ranges_overlap
from summer_scheduler.infrastructure.db.models import (
    AuditLog,
    GroupLesson,
    ImportBatch,
    Student,
)
from summer_scheduler.infrastructure.importing import (
    ImportIssue,
    ImportSourceError,
    NormalizedRow,
    group_lesson_schema,
    group_participant_schema,
    map_table,
    read_group_workbook,
    write_group_lessons_template,
)
from summer_scheduler.infrastructure.repositories import MasterRepository


class GroupLessonImportError(ValueError):
    """集団授業取込みを安全に反映できない場合に送出する。"""


_GROUP_ISSUE_COLUMNS = {
    "participants_missing": "group_lesson_id",
    "date_outside_project": "date",
    "closed_date": "date",
    "unknown_subject": "subject_code",
    "unknown_teacher": "teacher_id",
    "teacher_unqualified": "teacher_id",
    "teacher_time_conflict": "start_time",
    "student_time_conflict": "start_time",
}


class GroupLessonService:
    """集団授業の xlsx 入出力、検証、差分、反映を提供する。"""

    def __init__(self, projects: ProjectService) -> None:
        self._projects = projects

    def export_template(self, path: Path) -> None:
        """個人情報を含まない2シート構成のテンプレートを出力する。"""
        write_group_lessons_template(path)

    def inspect_group_import(self, path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """取込みウィザード用に二つのシートのヘッダーを返す。"""
        lessons, participants = read_group_workbook(path, preview_limit=20)
        return lessons.headers, participants.headers

    def prepare_group_import(
        self,
        path: Path,
        *,
        lesson_mapping: Mapping[str, str] | None = None,
        participant_mapping: Mapping[str, str] | None = None,
    ) -> GroupImportPreview:
        """xlsx を再読込し、参照・時刻・競合・差分を検証したプレビューを作る。"""
        project = self._projects.require_project()
        try:
            lessons_table, participants_table = read_group_workbook(path)
        except ImportSourceError as exc:
            raise GroupLessonImportError(str(exc)) from exc

        lessons_result = map_table(
            lessons_table,
            group_lesson_schema(),
            lesson_mapping,
        )
        participants_result = map_table(
            participants_table,
            group_participant_schema(),
            participant_mapping,
        )
        issues = [
            *_dto_issues(lessons_result.issues),
            *_dto_issues(participants_result.issues),
        ]
        declared_group_codes = {
            group_code
            for normalized in lessons_result.rows
            if isinstance(
                group_code := normalized.values.get("group_lesson_id"),
                str,
            )
            and group_code
        }
        participant_ids, participant_issues = _participant_ids(
            participants_result.rows,
            declared_group_codes,
            participants_result.applied_mapping,
        )
        issues.extend(participant_issues)
        rows, row_issues = _lesson_rows(
            lessons_result.rows,
            participant_ids,
            lessons_result.applied_mapping,
        )
        issues.extend(row_issues)

        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            issues.extend(
                _participant_reference_issues(
                    repository,
                    participants_result.rows,
                    participants_result.applied_mapping,
                )
            )
            issues.extend(self._validate_rows(repository, project.project_id, rows))
            diffs = self._build_diffs(repository, project.project_id, rows)

        return GroupImportPreview(
            project_id=project.project_id,
            source_path=path.resolve(),
            rows=tuple(rows),
            diffs=tuple(diffs),
            issues=tuple(issues),
            lesson_mapping=dict(lessons_result.applied_mapping),
            participant_mapping=dict(participants_result.applied_mapping),
        )

    def apply_group_import(
        self,
        preview: GroupImportPreview,
        *,
        include_deletes: bool = False,
    ) -> ImportApplyResult:
        """プレビュー対象を再読込・再検証してから一括反映する。

        deletion candidate は ``include_deletes`` が明示された時だけ削除する。失敗時は
        ``Session.begin`` により、集団授業・参加者・ImportBatch・AuditLog を全て戻す。
        """
        current = self._projects.require_project()
        if preview.project_id != current.project_id:
            raise GroupLessonImportError(
                "別のプロジェクトで作成した取込みプレビューは反映できません"
            )

        lesson_mapping = preview.lesson_mapping
        participant_mapping = preview.participant_mapping
        fresh = self.prepare_group_import(
            preview.source_path,
            lesson_mapping=lesson_mapping,
            participant_mapping=participant_mapping,
        )
        if not _group_previews_match(preview, fresh):
            raise GroupLessonImportError(
                "プレビュー後に入力ファイルまたはプロジェクトが変更されました。"
                "再度検証して差分を確認してください"
            )
        if fresh.has_errors:
            raise GroupLessonImportError(_issues_message(fresh.issues))

        added = sum(diff.operation == "add" for diff in fresh.diffs)
        changed = sum(diff.operation == "change" for diff in fresh.diffs)
        unchanged = sum(diff.operation == "unchanged" for diff in fresh.diffs)
        deleted = sum(diff.operation == "delete_candidate" for diff in fresh.diffs)
        warning_count = sum(issue.severity == "warning" for issue in fresh.issues)
        database = self._projects.require_database()

        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            existing_codes = {
                row.group_code: row
                for row in repository.list_group_lessons(project_id=current.project_id)
            }
            incoming_codes = {row.group_code for row in fresh.rows}
            for row in fresh.rows:
                subject = repository.get_subject_by_code(row.subject_code)
                teacher = (
                    repository.get_teacher_by_external_id(row.teacher_external_id)
                    if row.teacher_external_id is not None
                    else None
                )
                if subject is None:
                    raise GroupLessonImportError("検証後に科目参照が失われました")
                existing = existing_codes.get(row.group_code)
                changes = {
                    "grade": row.grade,
                    "subject_id": subject.id,
                    "course_name": row.course_name or None,
                    "date": row.day,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "teacher_id_optional": teacher.id if teacher is not None else None,
                    "room_optional": row.room or None,
                    "note": row.note or None,
                }
                if existing is None:
                    existing = repository.create_group_lesson(
                        GroupLesson(
                            project_id=current.project_id,
                            group_code=row.group_code,
                            **changes,
                        )
                    )
                else:
                    repository.update_group_lesson(existing, **changes)
                student_ids = [
                    _required_student(repository, external_id).id
                    for external_id in row.student_external_ids
                ]
                repository.replace_group_lesson_students(
                    group_lesson_id=existing.id,
                    student_ids=student_ids,
                )

            if include_deletes:
                for group_code, group in existing_codes.items():
                    if group_code not in incoming_codes:
                        repository.delete_group_lesson(group.id)
            else:
                deleted = 0

            batch = repository.create_import_batch(
                ImportBatch(
                    project_id=current.project_id,
                    import_type="group_lessons",
                    source_file_name=fresh.source_path.name,
                    row_count=len(fresh.rows),
                    success_count=len(fresh.rows),
                    warning_count=warning_count,
                    error_count=0,
                    mapping_json=json.dumps(
                        {
                            "format": "group_lessons",
                            "include_deletes": include_deletes,
                            "lesson_mapping": dict(lesson_mapping or {}),
                            "participant_mapping": dict(participant_mapping or {}),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
            repository.create_audit_log(
                AuditLog(
                    project_id=current.project_id,
                    action="group_lessons_imported",
                    entity_type="import_batch",
                    entity_id=str(batch.id),
                    before_json=None,
                    after_json=json.dumps(
                        {
                            "source_file_name": fresh.source_path.name,
                            "added": added,
                            "changed": changed,
                            "unchanged": unchanged,
                            "deleted": deleted,
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
            warnings=warning_count,
        )

    def list_group_lessons(self) -> tuple[GroupLessonDto, ...]:
        """表示用の集団授業一覧を時刻順に返す。"""
        project = self._projects.require_project()
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            rows: list[GroupLessonDto] = []
            for group in repository.list_group_lessons(project_id=project.project_id):
                subject = repository.get_subject(group.subject_id)
                teacher = (
                    repository.get_teacher(group.teacher_id_optional)
                    if group.teacher_id_optional is not None
                    else None
                )
                rows.append(
                    GroupLessonDto(
                        id=group.id,
                        group_code=group.group_code,
                        grade=group.grade,
                        subject_name=subject.display_name
                        if subject is not None
                        else "(削除済み科目)",
                        course_name=group.course_name or "",
                        day=group.date,
                        start_time=group.start_time,
                        end_time=group.end_time,
                        teacher_name=teacher.name if teacher is not None else "",
                        room=group.room_optional or "",
                        note=group.note or "",
                        student_count=len(
                            repository.list_group_lesson_students(group_lesson_id=group.id)
                        ),
                    )
                )
        return tuple(rows)

    def calendar_options(self) -> dict[str, tuple[dict[str, object], ...]]:
        """カレンダー登録画面で使用する有効な日付・科目・講師・コマを返す。"""
        project = self._projects.require_project()
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            return {
                "dates": tuple(
                    {"value": row.date.isoformat(), "label": row.date.strftime("%m/%d")}
                    for row in repository.list_open_dates(project_id=project.project_id)
                    if row.is_open
                ),
                "subjects": tuple(
                    {"code": row.code, "label": row.display_name}
                    for row in repository.list_subjects(active_only=True)
                ),
                "teachers": tuple(
                    {"externalId": row.external_id, "label": row.name}
                    for row in repository.list_teachers(active_only=True)
                ),
                "slots": tuple(
                    {
                        "code": row.code,
                        "label": f"{row.code} {row.start_time:%H:%M}～{row.end_time:%H:%M}",
                        "start": row.start_time.strftime("%H:%M"),
                        "end": row.end_time.strftime("%H:%M"),
                    }
                    for row in repository.list_time_slots(
                        project_id=project.project_id,
                        enabled_only=True,
                    )
                ),
            }

    def create_calendar_lesson(
        self,
        *,
        grade: str,
        subject_code: str,
        day: date,
        start_time: time,
        end_time: time,
        course_name: str = "",
        teacher_external_id: str | None = None,
        room: str = "",
        note: str = "",
    ) -> int:
        """画面入力した1件を既存の集団授業制約で検証して保存する。"""
        if not grade.strip():
            raise GroupLessonImportError("学年を選択してください")
        if not subject_code.strip():
            raise GroupLessonImportError("科目を選択してください")
        if start_time >= end_time:
            raise GroupLessonImportError("終了時刻は開始時刻より後にしてください")

        project = self._projects.require_project()
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            code_base = f"GROUP-{day:%Y%m%d}-{start_time:%H%M}-{subject_code.strip()}"
            group_code = code_base
            suffix = 2
            while repository.get_group_lesson_by_code(
                project_id=project.project_id,
                group_code=group_code,
            ) is not None:
                group_code = f"{code_base}-{suffix}"
                suffix += 1
            row = GroupLessonRow(
                source_row=1,
                group_code=group_code,
                grade=grade.strip(),
                subject_code=subject_code.strip(),
                course_name=course_name.strip(),
                day=day,
                start_time=start_time,
                end_time=end_time,
                teacher_external_id=teacher_external_id.strip()
                if teacher_external_id and teacher_external_id.strip()
                else None,
                room=room.strip() or None,
                note=note.strip(),
                student_external_ids=(),
            )
            issues = self._validate_rows(repository, project.project_id, (row,))
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                raise GroupLessonImportError(errors[0].message)
            subject = repository.get_subject_by_code(row.subject_code)
            if subject is None:
                raise GroupLessonImportError("科目が見つかりません")
            expected_school_level = _school_level_for_grade(row.grade)
            if expected_school_level is None or subject.school_level != expected_school_level:
                raise GroupLessonImportError("学年と科目の学校段階が一致していません")
            teacher = (
                repository.get_teacher_by_external_id(row.teacher_external_id)
                if row.teacher_external_id is not None
                else None
            )
            created = repository.create_group_lesson(
                GroupLesson(
                    project_id=project.project_id,
                    group_code=row.group_code,
                    grade=row.grade,
                    subject_id=subject.id,
                    course_name=row.course_name or None,
                    date=row.day,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    teacher_id_optional=teacher.id if teacher is not None else None,
                    room_optional=row.room,
                    note=row.note or None,
                )
            )
            repository.create_audit_log(
                AuditLog(
                    project_id=project.project_id,
                    action="group_lesson_created_from_calendar",
                    entity_type="group_lesson",
                    entity_id=str(created.id),
                    before_json=None,
                    after_json=json.dumps(
                        {"group_code": created.group_code, "date": created.date.isoformat()},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            )
            return created.id

    def delete_calendar_lesson(self, group_lesson_id: int) -> bool:
        """画面で選択した集団授業を監査記録付きで削除する。"""
        project = self._projects.require_project()
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            group = repository.get_group_lesson(group_lesson_id)
            if group is None or group.project_id != project.project_id:
                raise GroupLessonImportError("集団授業が見つかりません")
            before = {"group_code": group.group_code, "date": group.date.isoformat()}
            repository.delete_group_lesson(group.id)
            repository.create_audit_log(
                AuditLog(
                    project_id=project.project_id,
                    action="group_lesson_deleted_from_calendar",
                    entity_type="group_lesson",
                    entity_id=str(group_lesson_id),
                    before_json=json.dumps(before, ensure_ascii=False, sort_keys=True),
                    after_json=None,
                )
            )
            return True

    def _validate_rows(
        self,
        repository: MasterRepository,
        project_id: int,
        rows: Sequence[GroupLessonRow],
    ) -> list[ImportIssueDto]:
        project = repository.get_project(project_id)
        open_dates = {
            row.date: row.is_open for row in repository.list_open_dates(project_id=project_id)
        }
        students = {row.external_id: row for row in repository.list_students()}
        teachers = {row.external_id: row for row in repository.list_teachers()}
        subjects = {row.code: row for row in repository.list_subjects()}
        issues: list[ImportIssueDto] = []

        for row in rows:
            if project is not None and not (project.start_date <= row.day <= project.end_date):
                issues.append(_issue(row, "date_outside_project", "日付が講習期間外です"))
            if open_dates.get(row.day) is not True:
                issues.append(_issue(row, "closed_date", "日付が開校日に設定されていません"))
            subject = subjects.get(row.subject_code)
            if subject is None or not subject.active:
                issues.append(_issue(row, "unknown_subject", "科目コードが存在しないか無効です"))
            if row.teacher_external_id is not None:
                teacher = teachers.get(row.teacher_external_id)
                if teacher is None or not teacher.active:
                    issues.append(
                        _issue(row, "unknown_teacher", "担当講師IDが存在しないか無効です")
                    )
                elif subject is not None and not repository.can_teacher_teach(
                    teacher.id, subject.id
                ):
                    issues.append(
                        _issue(row, "teacher_unqualified", "担当講師はこの科目を担当できません")
                    )
        existing = repository.list_group_lessons(project_id=project_id)
        memberships = {
            group.id: {
                membership.student_id
                for membership in repository.list_group_lesson_students(group_lesson_id=group.id)
            }
            for group in existing
        }
        replacements = {row.group_code for row in rows}
        candidates: list[_Candidate] = [
            _Candidate(
                group_code=group.group_code,
                source_row=None,
                day=group.date,
                start_time=group.start_time,
                end_time=group.end_time,
                teacher_id=group.teacher_id_optional,
                student_ids=memberships[group.id],
            )
            for group in existing
            if group.group_code not in replacements
        ]
        for row in rows:
            teacher = teachers.get(row.teacher_external_id) if row.teacher_external_id else None
            candidates.append(
                _Candidate(
                    group_code=row.group_code,
                    source_row=row,
                    day=row.day,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    teacher_id=teacher.id if teacher is not None else None,
                    student_ids={
                        students[external_id].id
                        for external_id in row.student_external_ids
                        if external_id in students and students[external_id].active
                    },
                )
            )
        issues.extend(_conflict_issues(candidates))
        return issues

    def _build_diffs(
        self,
        repository: MasterRepository,
        project_id: int,
        rows: Sequence[GroupLessonRow],
    ) -> list[GroupLessonDiffDto]:
        existing = {
            group.group_code: group
            for group in repository.list_group_lessons(project_id=project_id)
        }
        existing_students = {
            group.id: _group_student_external_ids(repository, group.id)
            for group in existing.values()
        }
        diffs: list[GroupLessonDiffDto] = []
        incoming_codes = {row.group_code for row in rows}
        for row in rows:
            current = existing.get(row.group_code)
            after = _row_serialized(row)
            if current is None:
                diffs.append(
                    GroupLessonDiffDto("add", None, row.group_code, row.day, "", after, "追加")
                )
                continue
            before = _group_serialized(repository, current, existing_students[current.id])
            operation: Literal["change", "unchanged"] = "unchanged" if before == after else "change"
            diffs.append(
                GroupLessonDiffDto(
                    operation,
                    current.id,
                    row.group_code,
                    row.day,
                    before,
                    after,
                    "変更なし" if operation == "unchanged" else "更新",
                )
            )
        for group_code, group in existing.items():
            if group_code in incoming_codes:
                continue
            before = _group_serialized(repository, group, existing_students[group.id])
            diffs.append(
                GroupLessonDiffDto(
                    "delete_candidate",
                    group.id,
                    group_code,
                    group.date,
                    before,
                    "",
                    "削除候補（明示確認が必要）",
                )
            )
        return diffs


class _Candidate:
    def __init__(
        self,
        *,
        group_code: str,
        source_row: GroupLessonRow | None,
        day: date,
        start_time: time,
        end_time: time,
        teacher_id: int | None,
        student_ids: set[int],
    ) -> None:
        self.group_code = group_code
        self.source_row = source_row
        self.day = day
        self.start_time = start_time
        self.end_time = end_time
        self.teacher_id = teacher_id
        self.student_ids = student_ids


def _participant_reference_issues(
    repository: MasterRepository,
    rows: Sequence[NormalizedRow],
    source_columns: Mapping[str, str],
) -> list[ImportIssueDto]:
    """受講者シートの生徒参照を元シート・行・ヘッダー付きで検証する。"""
    issues: list[ImportIssueDto] = []
    source_header = source_columns.get("student_id", "student_id")
    for normalized in rows:
        student_external_id = normalized.values.get("student_id")
        if not isinstance(student_external_id, str) or not student_external_id:
            continue
        student = repository.get_student_by_external_id(student_external_id)
        if student is None or not student.active:
            issues.append(
                ImportIssueDto(
                    severity="error",
                    message="参加生徒IDが存在しないか無効です",
                    code="unknown_student",
                    sheet=normalized.sheet_name,
                    row=normalized.row_number,
                    column=source_header,
                )
            )
    return issues


def _participant_ids(
    rows: Sequence[NormalizedRow],
    declared_group_codes: set[str],
    source_columns: Mapping[str, str],
) -> tuple[dict[str, tuple[str, ...]], list[ImportIssueDto]]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    issues: list[ImportIssueDto] = []
    group_code_header = source_columns.get("group_lesson_id", "group_lesson_id")
    for normalized in rows:
        values = normalized.values
        group_code = values.get("group_lesson_id")
        student_id = values.get("student_id")
        if (
            isinstance(group_code, str)
            and group_code
            and isinstance(student_id, str)
            and student_id
        ):
            if group_code not in declared_group_codes:
                issues.append(
                    ImportIssueDto(
                        severity="error",
                        message="受講者が存在しない集団授業IDを参照しています",
                        code="unknown_group_lesson_reference",
                        sheet=normalized.sheet_name,
                        row=normalized.row_number,
                        column=group_code_header,
                    )
                )
                continue
            grouped[group_code].append(student_id)
    return {key: tuple(value) for key, value in grouped.items()}, issues


def _lesson_rows(
    normalized_rows: Sequence[NormalizedRow],
    participants: Mapping[str, tuple[str, ...]],
    source_columns: Mapping[str, str],
) -> tuple[list[GroupLessonRow], list[ImportIssueDto]]:
    rows: list[GroupLessonRow] = []
    issues: list[ImportIssueDto] = []
    for normalized in normalized_rows:
        values = normalized.values
        group_code = values.get("group_lesson_id")
        grade = values.get("grade")
        subject_code = values.get("subject_code")
        day = values.get("date")
        start = values.get("start_time")
        end = values.get("end_time")
        if not (
            isinstance(group_code, str)
            and isinstance(grade, str)
            and isinstance(subject_code, str)
            and isinstance(day, date)
            and isinstance(start, time)
            and isinstance(end, time)
        ):
            continue
        members = participants.get(group_code, ())
        row = GroupLessonRow(
            source_row=normalized.row_number,
            group_code=group_code,
            grade=grade,
            subject_code=subject_code,
            course_name=_optional_text(values.get("course_name")),
            day=day,
            start_time=start,
            end_time=end,
            teacher_external_id=_optional_text(values.get("teacher_id")) or None,
            room=_optional_text(values.get("room")) or None,
            note=_optional_text(values.get("note")),
            student_external_ids=members,
            source_columns=dict(source_columns),
        )
        if not members:
            issues.append(
                _issue(row, "participants_missing", "集団授業IDに対応する参加生徒がありません")
            )
        rows.append(row)
    return rows, issues


def _conflict_issues(candidates: Sequence[_Candidate]) -> list[ImportIssueDto]:
    issues: list[ImportIssueDto] = []
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            if left.day != right.day or not time_ranges_overlap(
                left.start_time,
                left.end_time,
                right.start_time,
                right.end_time,
            ):
                continue
            target = left.source_row or right.source_row
            if target is None:
                continue
            if left.teacher_id is not None and left.teacher_id == right.teacher_id:
                issues.append(
                    _issue(
                        target,
                        "teacher_time_conflict",
                        f"講師が集団授業 {left.group_code} と {right.group_code} で時間重複します",
                    )
                )
            shared = left.student_ids & right.student_ids
            if shared:
                issues.append(
                    _issue(
                        target,
                        "student_time_conflict",
                        f"参加生徒が集団授業 {left.group_code} と {right.group_code} で時間重複します",
                    )
                )
    return issues


def _group_serialized(
    repository: MasterRepository,
    group: GroupLesson,
    students: tuple[str, ...],
) -> str:
    subject = repository.get_subject(group.subject_id)
    teacher = (
        repository.get_teacher(group.teacher_id_optional)
        if group.teacher_id_optional is not None
        else None
    )
    return _canonical_json(
        {
            "group_code": group.group_code,
            "grade": group.grade,
            "subject_code": subject.code if subject is not None else "",
            "course_name": group.course_name or "",
            "date": group.date.isoformat(),
            "start_time": group.start_time.isoformat(timespec="minutes"),
            "end_time": group.end_time.isoformat(timespec="minutes"),
            "teacher_id": teacher.external_id if teacher is not None else "",
            "room": group.room_optional or "",
            "note": group.note or "",
            "students": students,
        }
    )


def _group_student_external_ids(
    repository: MasterRepository,
    group_lesson_id: int,
) -> tuple[str, ...]:
    external_ids: list[str] = []
    for membership in repository.list_group_lesson_students(group_lesson_id=group_lesson_id):
        student = repository.get_student(membership.student_id)
        if student is not None:
            external_ids.append(student.external_id)
    return tuple(sorted(external_ids))


def _row_serialized(row: GroupLessonRow) -> str:
    return _canonical_json(
        {
            "group_code": row.group_code,
            "grade": row.grade,
            "subject_code": row.subject_code,
            "course_name": row.course_name,
            "date": row.day.isoformat(),
            "start_time": row.start_time.isoformat(timespec="minutes"),
            "end_time": row.end_time.isoformat(timespec="minutes"),
            "teacher_id": row.teacher_external_id or "",
            "room": row.room or "",
            "note": row.note,
            "students": tuple(sorted(row.student_external_ids)),
        }
    )


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dto_issues(issues: Sequence[ImportIssue]) -> list[ImportIssueDto]:
    return [
        ImportIssueDto(
            severity=issue.severity.value,
            message=issue.message,
            code=issue.code,
            sheet=issue.sheet_name or "",
            row=issue.row_number,
            column=issue.source_header or issue.column_key or "",
        )
        for issue in issues
    ]


def _issue(row: GroupLessonRow, code: str, message: str) -> ImportIssueDto:
    return ImportIssueDto(
        severity="error",
        message=message,
        code=code,
        sheet="集団授業",
        row=row.source_row,
        column=row.source_columns.get(
            _GROUP_ISSUE_COLUMNS.get(code, ""),
            _GROUP_ISSUE_COLUMNS.get(code, ""),
        ),
    )


def _issues_message(issues: Sequence[ImportIssueDto]) -> str:
    errors = [issue.message for issue in issues if issue.severity == "error"]
    return " / ".join(errors[:3]) or "取込み検証に失敗しました"


def _school_level_for_grade(grade: str) -> str | None:
    normalized = grade.strip()
    if normalized.startswith("小"):
        return "elementary"
    if normalized.startswith("中"):
        return "junior_high"
    if normalized.startswith("高"):
        return "high_school"
    return None


def _optional_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _required_student(repository: MasterRepository, external_id: str) -> Student:
    student = repository.get_student_by_external_id(external_id)
    if student is None:
        raise GroupLessonImportError("検証後に参加生徒参照が失われました")
    return student


def _group_previews_match(
    expected: GroupImportPreview,
    actual: GroupImportPreview,
) -> bool:
    """利用者が確認した内容と適用直前の再検証結果が同じか判定する。"""
    return (
        expected.project_id == actual.project_id
        and expected.lesson_mapping == actual.lesson_mapping
        and expected.participant_mapping == actual.participant_mapping
        and expected.rows == actual.rows
        and expected.diffs == actual.diffs
        and expected.issues == actual.issues
    )


__all__ = ["GroupLessonImportError", "GroupLessonService"]
