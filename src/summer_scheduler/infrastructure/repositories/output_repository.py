"""Phase 6出力用の一括読取りとプロジェクト単位設定の永続化。"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db.models import (
    Assignment,
    Campus,
    CourseProject,
    GroupLesson,
    GroupLessonStudent,
    LessonRequest,
    OpenDate,
    OutputSetting,
    Student,
    Subject,
    Teacher,
    TimeSlot,
    ValidationIssue,
)
from summer_scheduler.reporting.data import (
    AssignmentRecord,
    DateRecord,
    GroupLessonRecord,
    LessonRequestRecord,
    OutputSnapshot,
    ProjectRecord,
    SlotRecord,
    StudentRecord,
    SubjectRecord,
    TeacherRecord,
    WarningRecord,
)
from summer_scheduler.reporting.settings import (
    OutputSettings,
    OutputSettingsDefaults,
    OutputSettingsValidationError,
    PageOrientation,
    PaperSize,
    StudentPageMode,
    StyleRule,
)


class OutputRepositoryError(RuntimeError):
    """出力用のDBデータまたは保存設定を安全に解釈できない。"""


class OutputRepository:
    """SQLAlchemy Sessionの範囲内で出力用DTOを一括構築する。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def build_base_snapshot(
        self,
        project_id: int,
        *,
        generated_at: datetime | None = None,
        include_resolved_warnings: bool = False,
    ) -> OutputSnapshot:
        """未配置診断以外の出力正本をSession非依存DTOへコピーする。"""
        project, campus = self._require_project_and_campus(project_id)
        open_dates = {
            row.date: row
            for row in self._session.scalars(
                select(OpenDate)
                .where(OpenDate.project_id == project_id)
                .order_by(OpenDate.date, OpenDate.id)
            )
        }
        slots = list(
            self._session.scalars(
                select(TimeSlot)
                .where(TimeSlot.project_id == project_id)
                .order_by(TimeSlot.sort_order, TimeSlot.id)
            )
        )
        students = list(
            self._session.scalars(select(Student).order_by(Student.external_id, Student.id))
        )
        teachers = list(
            self._session.scalars(select(Teacher).order_by(Teacher.external_id, Teacher.id))
        )
        subjects = list(
            self._session.scalars(select(Subject).order_by(Subject.sort_order, Subject.id))
        )
        requests = list(
            self._session.scalars(
                select(LessonRequest)
                .where(LessonRequest.project_id == project_id)
                .order_by(LessonRequest.id)
            )
        )
        assignments = list(
            self._session.scalars(
                select(Assignment)
                .where(Assignment.project_id == project_id)
                .order_by(
                    Assignment.date,
                    Assignment.time_slot_id,
                    Assignment.teacher_id,
                    Assignment.lesson_request_id,
                    Assignment.session_index,
                    Assignment.id,
                )
            )
        )
        groups = list(
            self._session.scalars(
                select(GroupLesson)
                .where(GroupLesson.project_id == project_id)
                .order_by(
                    GroupLesson.date,
                    GroupLesson.start_time,
                    GroupLesson.end_time,
                    GroupLesson.id,
                )
            )
        )
        members_by_group: dict[int, list[int]] = defaultdict(list)
        for row in self._session.scalars(
            select(GroupLessonStudent)
            .join(
                GroupLesson,
                GroupLesson.id == GroupLessonStudent.group_lesson_id,
            )
            .where(GroupLesson.project_id == project_id)
            .order_by(
                GroupLessonStudent.group_lesson_id,
                GroupLessonStudent.student_id,
            )
        ):
            members_by_group[row.group_lesson_id].append(row.student_id)

        issue_statement = select(ValidationIssue).where(ValidationIssue.project_id == project_id)
        if not include_resolved_warnings:
            issue_statement = issue_statement.where(ValidationIssue.resolved.is_(False))
        issues = list(self._session.scalars(issue_statement.order_by(ValidationIssue.id)))

        students_by_id = {row.id: row for row in students}
        teachers_by_id = {row.id: row for row in teachers}
        slots_by_id = {row.id: row for row in slots}
        requests_by_id = {row.id: row for row in requests}
        assignments_by_id = {row.id: row for row in assignments}
        groups_by_id = {row.id: row for row in groups}
        warnings = tuple(
            _warning_record(
                row,
                students=students_by_id,
                teachers=teachers_by_id,
                slots=slots_by_id,
                requests=requests_by_id,
                assignments=assignments_by_id,
                groups=groups_by_id,
                members_by_group=members_by_group,
            )
            for row in sorted(
                issues,
                key=lambda item: (
                    {"error": 0, "warning": 1, "info": 2}.get(item.severity, 9),
                    item.id,
                ),
            )
        )
        timestamp = generated_at or datetime.now(UTC)
        return OutputSnapshot(
            project=ProjectRecord(
                id=project.id,
                title=project.title,
                campus_name=campus.name,
                start_date=project.start_date,
                end_date=project.end_date,
                status=project.status,
                generated_at=timestamp,
                logo_path_optional=campus.logo_path_optional,
            ),
            dates=tuple(
                _date_record(day, open_dates.get(day))
                for day in _date_range(project.start_date, project.end_date)
            ),
            slots=tuple(
                SlotRecord(
                    id=row.id,
                    code=row.code,
                    display_name=row.display_name,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    sort_order=row.sort_order,
                    enabled=row.enabled,
                )
                for row in slots
            ),
            students=tuple(
                StudentRecord(
                    id=row.id,
                    external_id=row.external_id,
                    name=row.name,
                    grade=row.grade,
                    note=row.note or "",
                    active=row.active,
                )
                for row in students
            ),
            teachers=tuple(
                TeacherRecord(
                    id=row.id,
                    external_id=row.external_id,
                    name=row.name,
                    note=row.note or "",
                    active=row.active,
                )
                for row in teachers
            ),
            subjects=tuple(
                SubjectRecord(
                    id=row.id,
                    code=row.code,
                    name=row.display_name,
                    school_level=row.school_level,
                )
                for row in subjects
            ),
            lesson_requests=tuple(
                LessonRequestRecord(
                    id=row.id,
                    student_id=row.student_id,
                    subject_id=row.subject_id,
                    required_sessions=row.required_sessions,
                    regular_teacher_id_optional=row.regular_teacher_id_optional,
                    regular_teacher_priority=row.regular_teacher_priority,
                    one_to_one_required=row.one_to_one_required,
                    note=row.note or "",
                )
                for row in requests
            ),
            assignments=tuple(
                AssignmentRecord(
                    id=row.id,
                    lesson_request_id=row.lesson_request_id,
                    session_index=row.session_index,
                    day=row.date,
                    time_slot_id=row.time_slot_id,
                    teacher_id=row.teacher_id,
                    is_locked=row.is_locked,
                    is_manual=row.is_manual,
                    note=row.note or "",
                )
                for row in assignments
            ),
            group_lessons=tuple(
                GroupLessonRecord(
                    id=row.id,
                    group_code=row.group_code,
                    course_name=row.course_name or "",
                    grade=row.grade,
                    subject_id=row.subject_id,
                    day=row.date,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    teacher_id_optional=row.teacher_id_optional,
                    student_ids=tuple(members_by_group.get(row.id, ())),
                    room=row.room_optional or "",
                    note=row.note or "",
                )
                for row in groups
            ),
            unassigned=(),
            warnings=warnings,
        )

    def get_settings(
        self,
        project_id: int,
        *,
        defaults: OutputSettingsDefaults | None = None,
    ) -> OutputSettings:
        """保存行がなければ注入された既定値を使い、ロゴはCampusから読む。"""
        _project, campus = self._require_project_and_campus(project_id)
        row = self._session.get(OutputSetting, project_id)
        if row is None:
            if defaults is not None:
                return defaults.for_project(
                    project_id,
                    logo_path_optional=campus.logo_path_optional,
                )
            return OutputSettings(
                project_id=project_id,
                logo_path_optional=campus.logo_path_optional,
            )
        try:
            settings = OutputSettings(
                project_id=project_id,
                paper_size=cast(PaperSize, row.paper_size),
                orientation=cast(PageOrientation, row.orientation),
                logo_path_optional=campus.logo_path_optional,
                visible_fields=_decode_string_tuple(
                    row.visible_fields_json,
                    field_label="表示項目",
                ),
                days_per_page=row.days_per_page,
                teacher_columns_per_page=row.teacher_columns_per_page,
                font_size=row.font_size,
                margin_mm=row.margin_mm,
                file_name_pattern=row.file_name_pattern,
                default_output_directory_optional=(row.default_output_directory_optional),
                student_page_mode=cast(
                    StudentPageMode,
                    row.student_page_mode,
                ),
                csv_with_bom=row.csv_with_bom,
                style_rules=_decode_style_rules(row.style_rules_json),
            )
            settings.validate()
        except OutputSettingsValidationError as exc:
            raise OutputRepositoryError(
                "保存済みの出力設定が不正です。設定画面で確認してください。"
            ) from exc
        return settings

    def upsert_settings(self, settings: OutputSettings) -> OutputSettings:
        """全設定を欠落なく保存し、commitは呼出側へ委ねる。"""
        settings.validate()
        _project, campus = self._require_project_and_campus(settings.project_id)
        campus.logo_path_optional = settings.logo_path_optional
        values: dict[str, object] = {
            "paper_size": settings.paper_size,
            "orientation": settings.orientation,
            "visible_fields_json": _encode_json(list(settings.visible_fields)),
            "days_per_page": settings.days_per_page,
            "teacher_columns_per_page": settings.teacher_columns_per_page,
            "font_size": settings.font_size,
            "margin_mm": settings.margin_mm,
            "file_name_pattern": settings.file_name_pattern,
            "default_output_directory_optional": (settings.default_output_directory_optional),
            "student_page_mode": settings.student_page_mode,
            "csv_with_bom": settings.csv_with_bom,
            "style_rules_json": _encode_json(
                [
                    {
                        "code": rule.code,
                        "label": rule.label,
                        "marker": rule.marker,
                        "fill_color": rule.fill_color,
                        "text_color": rule.text_color,
                    }
                    for rule in settings.style_rules
                ]
            ),
        }
        row = self._session.get(OutputSetting, settings.project_id)
        if row is None:
            row = OutputSetting(project_id=settings.project_id, **values)
            self._session.add(row)
        else:
            for field, value in values.items():
                setattr(row, field, value)
        self._session.flush()
        return self.get_settings(settings.project_id)

    def _require_project_and_campus(
        self,
        project_id: int,
    ) -> tuple[CourseProject, Campus]:
        project = self._session.get(CourseProject, project_id)
        if project is None:
            raise OutputRepositoryError(
                f"出力対象プロジェクトが見つかりません: project_id={project_id}"
            )
        campus = self._session.get(Campus, project.campus_id)
        if campus is None:
            raise OutputRepositoryError("出力対象プロジェクトの校舎が見つかりません")
        return project, campus


def _warning_record(
    issue: ValidationIssue,
    *,
    students: dict[int, Student],
    teachers: dict[int, Teacher],
    slots: dict[int, TimeSlot],
    requests: dict[int, LessonRequest],
    assignments: dict[int, Assignment],
    groups: dict[int, GroupLesson],
    members_by_group: dict[int, list[int]],
) -> WarningRecord:
    details = _decode_json_object(issue.details_json)
    entity_id = _optional_int(issue.entity_id_optional)
    assignment = (
        assignments.get(entity_id)
        if issue.entity_type == "assignment" and entity_id is not None
        else None
    )
    request = (
        requests.get(entity_id)
        if issue.entity_type == "lesson_request" and entity_id is not None
        else None
    )
    group = (
        groups.get(entity_id)
        if issue.entity_type == "group_lesson" and entity_id is not None
        else None
    )

    if assignment is not None:
        request = requests.get(assignment.lesson_request_id)
    if group is None:
        group = _first_related_group(details, groups)

    day = _optional_date(details.get("date"))
    if day is None and assignment is not None:
        day = assignment.date
    if day is None and group is not None:
        day = group.date

    slot_id = _optional_int(details.get("time_slot_id"))
    if slot_id is None:
        slot_id = _optional_int(details.get("left_slot_id"))
    if slot_id is None and assignment is not None:
        slot_id = assignment.time_slot_id
    if slot_id is None and issue.entity_type == "time_slot":
        slot_id = entity_id
    slot = slots.get(slot_id) if slot_id is not None else None

    student_id = _optional_int(details.get("student_id"))
    if student_id is None and issue.entity_type == "student":
        student_id = entity_id
    if student_id is None and request is not None:
        student_id = request.student_id
    student_names: list[str] = []
    related_student_ids: list[int] = []
    student = students.get(student_id) if student_id is not None else None
    if student is not None:
        student_names.append(student.name)
        related_student_ids.append(student.id)
    elif group is not None:
        related_student_ids.extend(
            member_id for member_id in members_by_group.get(group.id, ()) if member_id in students
        )
        student_names.extend(students[member_id].name for member_id in related_student_ids)

    teacher_id = _optional_int(details.get("teacher_id"))
    if teacher_id is None and issue.entity_type == "teacher":
        teacher_id = entity_id
    if teacher_id is None and assignment is not None:
        teacher_id = assignment.teacher_id
    if teacher_id is None and group is not None:
        teacher_id = group.teacher_id_optional
    if (
        teacher_id is None
        and request is not None
        and (
            issue.issue_type.startswith("regular_teacher")
            or issue.issue_type.startswith("priority5_")
        )
    ):
        teacher_id = request.regular_teacher_id_optional
    if teacher_id is None and request is not None:
        teacher_id = _preferred_teacher_for_message(request, issue.message)
    teacher = teachers.get(teacher_id) if teacher_id is not None else None

    return WarningRecord(
        severity=issue.severity,
        issue_type=issue.issue_type,
        day_optional=day,
        slot_code=slot.code if slot is not None else "",
        student_name="、".join(dict.fromkeys(student_names)),
        teacher_name=teacher.name if teacher is not None else "",
        content=issue.message,
        status="対応済み" if issue.resolved else "未対応",
        student_ids=tuple(dict.fromkeys(related_student_ids)),
        teacher_id_optional=teacher.id if teacher is not None else None,
    )


def _date_record(day: date, row: OpenDate | None) -> DateRecord:
    if row is None:
        return DateRecord(
            day=day,
            is_open=False,
            note="",
            configured=False,
        )
    return DateRecord(
        day=day,
        is_open=row.is_open,
        note=row.note or "",
        configured=True,
    )


def _first_related_group(
    details: dict[str, object],
    groups: dict[int, GroupLesson],
) -> GroupLesson | None:
    for field in ("group_lesson_id", "left_group_id", "right_group_id"):
        group_id = _optional_int(details.get(field))
        group = groups.get(group_id) if group_id is not None else None
        if group is not None:
            return group
    return None


def _preferred_teacher_for_message(
    request: LessonRequest,
    message: str,
) -> int | None:
    values = (
        request.preferred_teacher_1_id_optional,
        request.preferred_teacher_2_id_optional,
        request.preferred_teacher_3_id_optional,
    )
    for rank, teacher_id in enumerate(values, start=1):
        if f"第{rank}希望" in message:
            return teacher_id
    return None


def _decode_string_tuple(payload: str, *, field_label: str) -> tuple[str, ...]:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise OutputRepositoryError(f"{field_label}の保存形式が不正です") from exc
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise OutputRepositoryError(f"{field_label}の保存形式が不正です")
    return tuple(raw)


def _decode_style_rules(payload: str) -> tuple[StyleRule, ...]:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise OutputRepositoryError("表示ルールの保存形式が不正です") from exc
    if not isinstance(raw, list):
        raise OutputRepositoryError("表示ルールの保存形式が不正です")
    result: list[StyleRule] = []
    for item in raw:
        if not isinstance(item, dict):
            raise OutputRepositoryError("表示ルールの保存形式が不正です")
        result.append(
            StyleRule(
                code=_required_string(item, "code"),
                label=_required_string(item, "label"),
                marker=_required_string(item, "marker"),
                fill_color=_required_string(item, "fill_color"),
                text_color=_required_string(item, "text_color"),
            )
        )
    return tuple(result)


def _required_string(value: dict[object, object], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str):
        raise OutputRepositoryError("表示ルールの保存形式が不正です")
    return item


def _decode_json_object(payload: str) -> dict[str, object]:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items()}


def _encode_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _optional_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _date_range(start: date, end: date) -> tuple[date, ...]:
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


__all__ = ["OutputRepository", "OutputRepositoryError"]
