"""SQLAlchemy Sessionを使うマスターデータExcel入出力サービス。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db.models import (
    CourseProject,
    LessonRequest,
    Student,
    Subject,
    Teacher,
    TeacherQualification,
)
from summer_scheduler.infrastructure.excel.contracts import (
    ImportIssue,
    ImportPreview,
    ImportResult,
    ImportRow,
    IssueSeverity,
    MasterDataImportError,
    immutable_counts,
)
from summer_scheduler.infrastructure.excel.reader import read_master_data_workbook
from summer_scheduler.infrastructure.excel.schema import (
    LESSON_REQUEST_SHEET,
    QUALIFICATION_SHEET,
    SHEET_NAMES,
    STUDENT_SHEET,
    SUBJECT_SHEET,
    TEACHER_SHEET,
)
from summer_scheduler.infrastructure.excel.template import write_master_data_workbook
from summer_scheduler.infrastructure.excel.validation import (
    ExistingLessonState,
    ExistingMasterData,
    TeacherState,
    validate_master_rows,
)


class MasterDataExcelService:
    """1プロジェクトのmaster_data.xlsxを入出力するインフラアダプター。

    ``preview_import`` はDBを書き換えない。``apply_import`` は検証済みプレビューを
    SAVEPOINT内でupsertし、flushまで行う。アプリケーション層が外側のトランザクション
    をcommitすることで反映を確定するため、このクラスは呼出側のcommit境界を奪わない。
    """

    def __init__(self, session: Session, project_id: int) -> None:
        if project_id <= 0:
            raise ValueError("project_idは1以上で指定してください。")
        self._session = session
        self._project_id = project_id

    def export_template(self, path: Path) -> Path:
        """現在のマスターデータと架空の例示行を含むブックを出力する。"""
        destination = _require_xlsx_path(path)
        with self._session.no_autoflush:
            self._require_project()
            rows_by_sheet = self._export_rows()
        write_master_data_workbook(destination, rows_by_sheet)
        return destination

    def preview_import(self, path: Path) -> ImportPreview:
        """ファイル全体を検証し、新規・更新件数を含むプレビューを返す。"""
        source = _require_xlsx_path(path)
        read_result = read_master_data_workbook(source)
        issues = list(read_result.issues)

        with self._session.no_autoflush:
            if self._session.get(CourseProject, self._project_id) is None:
                issues.append(
                    ImportIssue(
                        IssueSeverity.ERROR,
                        "反映先のプロジェクトが存在しません。",
                        code="unknown_project",
                    ),
                )
                existing = _empty_existing_data()
            else:
                existing = self._load_existing_data()

        validation = validate_master_rows(read_result.rows, existing)
        issues.extend(validation.issues)
        return ImportPreview(
            source_path=source,
            project_id=self._project_id,
            rows=validation.rows,
            issues=tuple(issues),
            new_counts=immutable_counts(validation.new_counts),
            update_counts=immutable_counts(validation.update_counts),
        )

    def apply_import(self, preview: ImportPreview) -> ImportResult:
        """確認済みプレビューを1つのSAVEPOINT内でupsertし、flushする。

        反映前にSessionが未保存の変更を持つ場合は、取込み以外の変更を同じflushへ
        巻き込まないため拒否する。成功後は呼出側で ``session.commit()``、後続処理が
        失敗した場合は ``session.rollback()`` を実行する。
        """
        if preview.project_id != self._project_id:
            raise MasterDataImportError("別プロジェクト用のプレビューは反映できません。")
        if preview.has_errors:
            first_error = next(
                issue for issue in preview.issues if issue.severity is IssueSeverity.ERROR
            )
            location = f"{first_error.location}: " if first_error.location else ""
            raise MasterDataImportError(
                f"取込みエラーがあるため反映できません。{location}{first_error.message}",
            )
        if self._session.new or self._session.dirty or self._session.deleted:
            raise MasterDataImportError(
                "Sessionに取込み以外の未保存変更があります。先に保存または取消してください。",
            )

        rows_by_sheet = {
            sheet_name: [row for row in preview.rows if row.sheet_name == sheet_name]
            for sheet_name in SHEET_NAMES
        }
        with self._session.begin_nested():
            self._require_project()
            students = self._upsert_students(rows_by_sheet[STUDENT_SHEET.name])
            teachers = self._upsert_teachers(rows_by_sheet[TEACHER_SHEET.name])
            subjects = self._upsert_subjects(rows_by_sheet[SUBJECT_SHEET.name])
            self._session.flush()
            self._upsert_qualifications(
                rows_by_sheet[QUALIFICATION_SHEET.name],
                teachers,
                subjects,
            )
            self._upsert_lesson_requests(
                rows_by_sheet[LESSON_REQUEST_SHEET.name],
                students,
                teachers,
                subjects,
            )
            self._session.flush()

        return ImportResult(
            new_counts=immutable_counts(preview.new_counts),
            update_counts=immutable_counts(preview.update_counts),
            warning_count=preview.warning_count,
        )

    def _require_project(self) -> CourseProject:
        project = self._session.get(CourseProject, self._project_id)
        if project is None:
            raise MasterDataImportError("反映先のプロジェクトが存在しません。")
        return project

    def _export_rows(self) -> dict[str, list[dict[str, object]]]:
        students = list(
            self._session.scalars(select(Student).order_by(Student.external_id)),
        )
        teachers = list(
            self._session.scalars(select(Teacher).order_by(Teacher.external_id)),
        )
        subjects = list(
            self._session.scalars(select(Subject).order_by(Subject.sort_order, Subject.code)),
        )
        qualifications = list(
            self._session.scalars(
                select(TeacherQualification).order_by(
                    TeacherQualification.teacher_id,
                    TeacherQualification.subject_id,
                ),
            ),
        )
        lesson_requests = list(
            self._session.scalars(
                select(LessonRequest)
                .where(LessonRequest.project_id == self._project_id)
                .order_by(LessonRequest.student_id, LessonRequest.subject_id),
            ),
        )
        student_external_ids = {student.id: student.external_id for student in students}
        teacher_external_ids = {teacher.id: teacher.external_id for teacher in teachers}
        subject_codes = {subject.id: subject.code for subject in subjects}

        return {
            STUDENT_SHEET.name: [
                {
                    "external_id": student.external_id,
                    "name": student.name,
                    "grade": student.grade,
                    "default_max_consecutive_slots": student.default_max_consecutive_slots,
                    "allow_gap": student.allow_gap,
                    "note": student.note,
                    "active": student.active,
                }
                for student in students
            ],
            TEACHER_SHEET.name: [
                {
                    "external_id": teacher.external_id,
                    "name": teacher.name,
                    "allow_gap": teacher.allow_gap,
                    "note": teacher.note,
                    "active": teacher.active,
                }
                for teacher in teachers
            ],
            SUBJECT_SHEET.name: [
                {
                    "code": subject.code,
                    "display_name": subject.display_name,
                    "school_level": _school_level_for_excel(subject.school_level),
                    "sort_order": subject.sort_order,
                    "active": subject.active,
                }
                for subject in subjects
            ],
            QUALIFICATION_SHEET.name: [
                {
                    "teacher_external_id": teacher_external_ids[qualification.teacher_id],
                    "subject_code": subject_codes[qualification.subject_id],
                    "can_teach": qualification.can_teach,
                    "note": qualification.note,
                }
                for qualification in qualifications
            ],
            LESSON_REQUEST_SHEET.name: [
                {
                    "student_external_id": student_external_ids[request.student_id],
                    "subject_code": subject_codes[request.subject_id],
                    "required_sessions": request.required_sessions,
                    "regular_teacher_external_id": _external_id_for(
                        request.regular_teacher_id_optional,
                        teacher_external_ids,
                    ),
                    "regular_teacher_priority": request.regular_teacher_priority,
                    "preferred_teacher_1_external_id": _external_id_for(
                        request.preferred_teacher_1_id_optional,
                        teacher_external_ids,
                    ),
                    "preferred_teacher_2_external_id": _external_id_for(
                        request.preferred_teacher_2_id_optional,
                        teacher_external_ids,
                    ),
                    "preferred_teacher_3_external_id": _external_id_for(
                        request.preferred_teacher_3_id_optional,
                        teacher_external_ids,
                    ),
                    "one_to_one_required": request.one_to_one_required,
                    "max_consecutive_slots_override": (
                        request.max_consecutive_slots_override_optional
                    ),
                    "allow_gap_override": request.allow_gap_override_optional,
                    "note": request.note,
                }
                for request in lesson_requests
            ],
        }

    def _load_existing_data(self) -> ExistingMasterData:
        students = list(self._session.scalars(select(Student)))
        teachers = list(self._session.scalars(select(Teacher)))
        subjects = list(self._session.scalars(select(Subject)))
        qualifications = list(self._session.scalars(select(TeacherQualification)))
        lessons = list(
            self._session.scalars(
                select(LessonRequest).where(
                    LessonRequest.project_id == self._project_id,
                ),
            ),
        )

        teacher_external_ids = {teacher.id: teacher.external_id for teacher in teachers}
        student_external_ids = {student.id: student.external_id for student in students}
        subject_codes = {subject.id: subject.code for subject in subjects}
        return ExistingMasterData(
            students={student.external_id: student.name for student in students},
            teachers={
                teacher.external_id: TeacherState(
                    database_id=teacher.id,
                    active=teacher.active,
                    name=teacher.name,
                )
                for teacher in teachers
            },
            subjects={subject.code for subject in subjects},
            qualifications={
                (
                    teacher_external_ids[qualification.teacher_id],
                    subject_codes[qualification.subject_id],
                ): qualification.can_teach
                for qualification in qualifications
            },
            lessons={
                (
                    student_external_ids[lesson.student_id],
                    subject_codes[lesson.subject_id],
                ): ExistingLessonState(
                    regular_teacher_external_id=_external_id_for(
                        lesson.regular_teacher_id_optional,
                        teacher_external_ids,
                    ),
                    preferred_teacher_1_external_id=_external_id_for(
                        lesson.preferred_teacher_1_id_optional,
                        teacher_external_ids,
                    ),
                    preferred_teacher_2_external_id=_external_id_for(
                        lesson.preferred_teacher_2_id_optional,
                        teacher_external_ids,
                    ),
                    preferred_teacher_3_external_id=_external_id_for(
                        lesson.preferred_teacher_3_id_optional,
                        teacher_external_ids,
                    ),
                )
                for lesson in lessons
            },
        )

    def _upsert_students(self, rows: list[ImportRow]) -> dict[str, Student]:
        existing = {
            student.external_id: student for student in self._session.scalars(select(Student))
        }
        for row in rows:
            values = row.values
            external_id = _as_string(values, "external_id")
            student = existing.get(external_id)
            if student is None:
                student = Student(
                    external_id=external_id,
                    name=_as_string(values, "name"),
                    grade=_as_string(values, "grade"),
                    default_max_consecutive_slots=_as_int(
                        values,
                        "default_max_consecutive_slots",
                    ),
                    allow_gap=_as_bool(values, "allow_gap"),
                    note=_as_optional_string(values, "note"),
                    active=_as_bool(values, "active"),
                )
                self._session.add(student)
                existing[external_id] = student
            else:
                student.name = _as_string(values, "name")
                student.grade = _as_string(values, "grade")
                student.default_max_consecutive_slots = _as_int(
                    values,
                    "default_max_consecutive_slots",
                )
                student.allow_gap = _as_bool(values, "allow_gap")
                student.note = _as_optional_string(values, "note")
                student.active = _as_bool(values, "active")
        return existing

    def _upsert_teachers(self, rows: list[ImportRow]) -> dict[str, Teacher]:
        existing = {
            teacher.external_id: teacher for teacher in self._session.scalars(select(Teacher))
        }
        for row in rows:
            values = row.values
            external_id = _as_string(values, "external_id")
            teacher = existing.get(external_id)
            if teacher is None:
                teacher = Teacher(
                    external_id=external_id,
                    name=_as_string(values, "name"),
                    allow_gap=_as_bool(values, "allow_gap"),
                    note=_as_optional_string(values, "note"),
                    active=_as_bool(values, "active"),
                )
                self._session.add(teacher)
                existing[external_id] = teacher
            else:
                teacher.name = _as_string(values, "name")
                teacher.allow_gap = _as_bool(values, "allow_gap")
                teacher.note = _as_optional_string(values, "note")
                teacher.active = _as_bool(values, "active")
        return existing

    def _upsert_subjects(self, rows: list[ImportRow]) -> dict[str, Subject]:
        existing = {subject.code: subject for subject in self._session.scalars(select(Subject))}
        for row in rows:
            values = row.values
            code = _as_string(values, "code")
            subject = existing.get(code)
            if subject is None:
                subject = Subject(
                    code=code,
                    display_name=_as_string(values, "display_name"),
                    school_level=_school_level_for_database(
                        _as_string(values, "school_level"),
                    ),
                    sort_order=_as_int(values, "sort_order"),
                    active=_as_bool(values, "active"),
                )
                self._session.add(subject)
                existing[code] = subject
            else:
                subject.display_name = _as_string(values, "display_name")
                subject.school_level = _school_level_for_database(
                    _as_string(values, "school_level"),
                )
                subject.sort_order = _as_int(values, "sort_order")
                subject.active = _as_bool(values, "active")
        return existing

    def _upsert_qualifications(
        self,
        rows: list[ImportRow],
        teachers: dict[str, Teacher],
        subjects: dict[str, Subject],
    ) -> None:
        existing = {
            (qualification.teacher_id, qualification.subject_id): qualification
            for qualification in self._session.scalars(select(TeacherQualification))
        }
        for row in rows:
            values = row.values
            teacher = teachers[_as_string(values, "teacher_external_id")]
            subject = subjects[_as_string(values, "subject_code")]
            key = (teacher.id, subject.id)
            qualification = existing.get(key)
            if qualification is None:
                qualification = TeacherQualification(
                    teacher_id=teacher.id,
                    subject_id=subject.id,
                    can_teach=_as_bool(values, "can_teach"),
                    note=_as_optional_string(values, "note"),
                )
                self._session.add(qualification)
                existing[key] = qualification
            else:
                qualification.can_teach = _as_bool(values, "can_teach")
                qualification.note = _as_optional_string(values, "note")

    def _upsert_lesson_requests(
        self,
        rows: list[ImportRow],
        students: dict[str, Student],
        teachers: dict[str, Teacher],
        subjects: dict[str, Subject],
    ) -> None:
        existing = {
            (lesson.student_id, lesson.subject_id): lesson
            for lesson in self._session.scalars(
                select(LessonRequest).where(
                    LessonRequest.project_id == self._project_id,
                ),
            )
        }
        for row in rows:
            values = row.values
            student = students[_as_string(values, "student_external_id")]
            subject = subjects[_as_string(values, "subject_code")]
            key = (student.id, subject.id)
            lesson = existing.get(key)
            teacher_ids = _lesson_teacher_database_ids(values, teachers)
            if lesson is None:
                lesson = LessonRequest(
                    project_id=self._project_id,
                    student_id=student.id,
                    subject_id=subject.id,
                    required_sessions=_as_int(values, "required_sessions"),
                    regular_teacher_id_optional=teacher_ids["regular"],
                    regular_teacher_priority=_as_int(
                        values,
                        "regular_teacher_priority",
                    ),
                    preferred_teacher_1_id_optional=teacher_ids["preferred_1"],
                    preferred_teacher_2_id_optional=teacher_ids["preferred_2"],
                    preferred_teacher_3_id_optional=teacher_ids["preferred_3"],
                    one_to_one_required=_as_bool(values, "one_to_one_required"),
                    max_consecutive_slots_override_optional=_as_optional_int(
                        values,
                        "max_consecutive_slots_override",
                    ),
                    allow_gap_override_optional=_as_optional_bool(
                        values,
                        "allow_gap_override",
                    ),
                    note=_as_optional_string(values, "note"),
                )
                self._session.add(lesson)
                existing[key] = lesson
            else:
                lesson.required_sessions = _as_int(values, "required_sessions")
                lesson.regular_teacher_id_optional = teacher_ids["regular"]
                lesson.regular_teacher_priority = _as_int(
                    values,
                    "regular_teacher_priority",
                )
                lesson.preferred_teacher_1_id_optional = teacher_ids["preferred_1"]
                lesson.preferred_teacher_2_id_optional = teacher_ids["preferred_2"]
                lesson.preferred_teacher_3_id_optional = teacher_ids["preferred_3"]
                lesson.one_to_one_required = _as_bool(values, "one_to_one_required")
                lesson.max_consecutive_slots_override_optional = _as_optional_int(
                    values,
                    "max_consecutive_slots_override",
                )
                lesson.allow_gap_override_optional = _as_optional_bool(
                    values,
                    "allow_gap_override",
                )
                lesson.note = _as_optional_string(values, "note")


def _empty_existing_data() -> ExistingMasterData:
    return ExistingMasterData({}, {}, set(), {}, {})


def _require_xlsx_path(path: Path) -> Path:
    normalized = path.expanduser()
    if normalized.suffix.casefold() != ".xlsx":
        raise ValueError("master_dataのファイル拡張子は.xlsxを指定してください。")
    return normalized


def _external_id_for(
    database_id: int | None,
    external_ids: Mapping[int, str],
) -> str | None:
    if database_id is None:
        return None
    return external_ids[database_id]


def _lesson_teacher_database_ids(
    values: Mapping[str, object],
    teachers: Mapping[str, Teacher],
) -> dict[str, int | None]:
    def resolve(key: str) -> int | None:
        external_id = _as_optional_string(values, key)
        return teachers[external_id].id if external_id is not None else None

    return {
        "regular": resolve("regular_teacher_external_id"),
        "preferred_1": resolve("preferred_teacher_1_external_id"),
        "preferred_2": resolve("preferred_teacher_2_external_id"),
        "preferred_3": resolve("preferred_teacher_3_external_id"),
    }


def _school_level_for_excel(database_value: str) -> str:
    labels = {
        "elementary": "小学校",
        "junior_high": "中学校",
        "high_school": "高校",
    }
    return labels.get(database_value, database_value)


def _school_level_for_database(excel_value: str) -> str:
    values = {
        "小学校": "elementary",
        "中学校": "junior_high",
        "高校": "high_school",
    }
    return values[excel_value]


def _as_string(values: Mapping[str, object], key: str) -> str:
    value = values[key]
    if not isinstance(value, str):
        raise AssertionError(f"{key} は文字列ではありません。")
    return value


def _as_optional_string(values: Mapping[str, object], key: str) -> str | None:
    value = values[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise AssertionError(f"{key} は文字列ではありません。")
    return value


def _as_int(values: Mapping[str, object], key: str) -> int:
    value = values[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{key} は整数ではありません。")
    return value


def _as_optional_int(values: Mapping[str, object], key: str) -> int | None:
    value = values[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{key} は整数ではありません。")
    return value


def _as_bool(values: Mapping[str, object], key: str) -> bool:
    value = values[key]
    if not isinstance(value, bool):
        raise AssertionError(f"{key} は真偽値ではありません。")
    return value


def _as_optional_bool(values: Mapping[str, object], key: str) -> bool | None:
    value = values[key]
    if value is None:
        return None
    if not isinstance(value, bool):
        raise AssertionError(f"{key} は真偽値ではありません。")
    return value
