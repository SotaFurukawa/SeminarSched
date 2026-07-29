"""Excel行同士および既存DB参照を横断する検証。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from summer_scheduler.infrastructure.excel.contracts import (
    ImportIssue,
    ImportRow,
    IssueSeverity,
    RowOperation,
    immutable_counts,
)
from summer_scheduler.infrastructure.excel.reader import ParsedRow
from summer_scheduler.infrastructure.excel.schema import (
    LESSON_REQUEST_SHEET,
    QUALIFICATION_SHEET,
    SHEET_NAMES,
    STUDENT_SHEET,
    SUBJECT_SHEET,
    TEACHER_SHEET,
)

_TEACHER_REFERENCE_COLUMNS: Final = (
    ("regular_teacher_external_id", "通常担当講師ID"),
    ("preferred_teacher_1_external_id", "第1希望講師ID"),
    ("preferred_teacher_2_external_id", "第2希望講師ID"),
    ("preferred_teacher_3_external_id", "第3希望講師ID"),
)
_PREFERRED_TEACHER_KEYS: Final = (
    "preferred_teacher_1_external_id",
    "preferred_teacher_2_external_id",
    "preferred_teacher_3_external_id",
)


@dataclass(frozen=True, slots=True)
class TeacherState:
    """参照検証に必要な講師の既存状態。"""

    database_id: int
    active: bool
    name: str


@dataclass(frozen=True, slots=True)
class ExistingLessonState:
    """無効講師を「新規選択」したか判定するための既存値。"""

    regular_teacher_external_id: str | None
    preferred_teacher_1_external_id: str | None
    preferred_teacher_2_external_id: str | None
    preferred_teacher_3_external_id: str | None

    def teacher_for(self, key: str) -> str | None:
        """Excelの内部列キーに対応する既存講師IDを返す。"""
        values = {
            "regular_teacher_external_id": self.regular_teacher_external_id,
            "preferred_teacher_1_external_id": self.preferred_teacher_1_external_id,
            "preferred_teacher_2_external_id": self.preferred_teacher_2_external_id,
            "preferred_teacher_3_external_id": self.preferred_teacher_3_external_id,
        }
        return values[key]


@dataclass(frozen=True, slots=True)
class ExistingMasterData:
    """DBから読み取った参照検証用スナップショット。"""

    students: dict[str, str]
    teachers: dict[str, TeacherState]
    subjects: set[str]
    qualifications: dict[tuple[str, str], bool]
    lessons: dict[tuple[str, str], ExistingLessonState]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """DB差分判定を含む検証結果。"""

    rows: tuple[ImportRow, ...]
    issues: tuple[ImportIssue, ...]
    new_counts: dict[str, int]
    update_counts: dict[str, int]


def validate_master_rows(
    parsed_rows: tuple[ParsedRow, ...],
    existing: ExistingMasterData,
) -> ValidationResult:
    """参照整合性・優先度・資格・無効講師選択を検証する。"""
    imported_by_sheet = {
        sheet_name: [row for row in parsed_rows if row.sheet_name == sheet_name]
        for sheet_name in SHEET_NAMES
    }
    effective_students = set(existing.students)
    effective_teachers = dict(existing.teachers)
    effective_subjects = set(existing.subjects)
    effective_qualifications = dict(existing.qualifications)

    for row in imported_by_sheet[STUDENT_SHEET.name]:
        effective_students.add(_required_string(row, "external_id"))
    for row in imported_by_sheet[TEACHER_SHEET.name]:
        external_id = _required_string(row, "external_id")
        effective_teachers[external_id] = TeacherState(
            database_id=existing.teachers.get(
                external_id,
                TeacherState(0, True, ""),
            ).database_id,
            active=_required_bool(row, "active"),
            name=_required_string(row, "name"),
        )
    for row in imported_by_sheet[SUBJECT_SHEET.name]:
        effective_subjects.add(_required_string(row, "code"))
    for row in imported_by_sheet[QUALIFICATION_SHEET.name]:
        effective_qualifications[
            (
                _required_string(row, "teacher_external_id"),
                _required_string(row, "subject_code"),
            )
        ] = _required_bool(row, "can_teach")

    issues: list[ImportIssue] = []
    _validate_same_names(imported_by_sheet[STUDENT_SHEET.name], existing.students, issues)
    _validate_same_teacher_names(
        imported_by_sheet[TEACHER_SHEET.name],
        existing.teachers,
        issues,
    )
    _validate_school_levels(imported_by_sheet[SUBJECT_SHEET.name], issues)
    _validate_qualifications(
        imported_by_sheet[QUALIFICATION_SHEET.name],
        effective_teachers,
        effective_subjects,
        issues,
    )
    _validate_lesson_requests(
        imported_by_sheet[LESSON_REQUEST_SHEET.name],
        effective_students,
        effective_teachers,
        effective_subjects,
        effective_qualifications,
        existing.lessons,
        issues,
    )

    rows: list[ImportRow] = []
    new_counts = dict.fromkeys(SHEET_NAMES, 0)
    update_counts = dict.fromkeys(SHEET_NAMES, 0)
    for parsed_row in parsed_rows:
        operation = _operation_for(parsed_row, existing)
        counts = new_counts if operation is RowOperation.NEW else update_counts
        counts[parsed_row.sheet_name] += 1
        rows.append(
            ImportRow(
                sheet_name=parsed_row.sheet_name,
                row_number=parsed_row.row_number,
                operation=operation,
                values=dict(parsed_row.values),
            ),
        )

    return ValidationResult(
        rows=tuple(rows),
        issues=tuple(issues),
        new_counts=dict(immutable_counts(new_counts)),
        update_counts=dict(immutable_counts(update_counts)),
    )


def _operation_for(row: ParsedRow, existing: ExistingMasterData) -> RowOperation:
    values = row.values
    if row.sheet_name == STUDENT_SHEET.name:
        exists = _string(values, "external_id") in existing.students
    elif row.sheet_name == TEACHER_SHEET.name:
        exists = _string(values, "external_id") in existing.teachers
    elif row.sheet_name == SUBJECT_SHEET.name:
        exists = _string(values, "code") in existing.subjects
    elif row.sheet_name == QUALIFICATION_SHEET.name:
        key = (
            _string(values, "teacher_external_id"),
            _string(values, "subject_code"),
        )
        exists = key in existing.qualifications
    elif row.sheet_name == LESSON_REQUEST_SHEET.name:
        key = (
            _string(values, "student_external_id"),
            _string(values, "subject_code"),
        )
        exists = key in existing.lessons
    else:
        raise AssertionError(f"未対応のシートです: {row.sheet_name}")
    return RowOperation.UPDATE if exists else RowOperation.NEW


def _validate_same_names(
    rows: list[ParsedRow],
    existing_students: dict[str, str],
    issues: list[ImportIssue],
) -> None:
    names_to_ids: dict[str, set[str]] = {}
    for external_id, name in existing_students.items():
        names_to_ids.setdefault(name, set()).add(external_id)
    for row in rows:
        external_id = _required_string(row, "external_id")
        name = _required_string(row, "name")
        other_ids = names_to_ids.get(name, set()) - {external_id}
        if other_ids:
            issues.append(
                _warning(
                    row,
                    "氏名",
                    "別の生徒IDに同姓同名の生徒がいます。IDを確認してください。",
                    "duplicate_student_name",
                ),
            )
        names_to_ids.setdefault(name, set()).add(external_id)


def _validate_same_teacher_names(
    rows: list[ParsedRow],
    existing_teachers: dict[str, TeacherState],
    issues: list[ImportIssue],
) -> None:
    names_to_ids: dict[str, set[str]] = {}
    for external_id, teacher in existing_teachers.items():
        names_to_ids.setdefault(teacher.name, set()).add(external_id)
    for row in rows:
        external_id = _required_string(row, "external_id")
        name = _required_string(row, "name")
        other_ids = names_to_ids.get(name, set()) - {external_id}
        if other_ids:
            issues.append(
                _warning(
                    row,
                    "氏名",
                    "別の講師IDに同姓同名の講師がいます。IDを確認してください。",
                    "duplicate_teacher_name",
                ),
            )
        names_to_ids.setdefault(name, set()).add(external_id)


def _validate_school_levels(
    rows: list[ParsedRow],
    issues: list[ImportIssue],
) -> None:
    valid_levels = {"小学校", "中学校", "高校"}
    for row in rows:
        if _required_string(row, "school_level") not in valid_levels:
            issues.append(
                _error(
                    row,
                    "学校段階",
                    "小学校・中学校・高校のいずれかを入力してください。",
                    "invalid_school_level",
                ),
            )


def _validate_qualifications(
    rows: list[ParsedRow],
    teachers: dict[str, TeacherState],
    subjects: set[str],
    issues: list[ImportIssue],
) -> None:
    for row in rows:
        teacher_id = _required_string(row, "teacher_external_id")
        subject_code = _required_string(row, "subject_code")
        if teacher_id not in teachers:
            issues.append(
                _error(
                    row,
                    "講師ID",
                    "講師シートまたは既存データに存在しない講師IDです。",
                    "unknown_teacher",
                ),
            )
        if subject_code not in subjects:
            issues.append(
                _error(
                    row,
                    "科目コード",
                    "科目シートまたは既存データに存在しない科目コードです。",
                    "unknown_subject",
                ),
            )


def _validate_lesson_requests(
    rows: list[ParsedRow],
    students: set[str],
    teachers: dict[str, TeacherState],
    subjects: set[str],
    qualifications: dict[tuple[str, str], bool],
    existing_lessons: dict[tuple[str, str], ExistingLessonState],
    issues: list[ImportIssue],
) -> None:
    for row in rows:
        student_id = _required_string(row, "student_external_id")
        subject_code = _required_string(row, "subject_code")
        lesson_key = (student_id, subject_code)
        existing_lesson = existing_lessons.get(lesson_key)

        if student_id not in students:
            issues.append(
                _error(
                    row,
                    "生徒ID",
                    "生徒シートまたは既存データに存在しない生徒IDです。",
                    "unknown_student",
                ),
            )
        if subject_code not in subjects:
            issues.append(
                _error(
                    row,
                    "科目コード",
                    "科目シートまたは既存データに存在しない科目コードです。",
                    "unknown_subject",
                ),
            )

        priority = _required_int(row, "regular_teacher_priority")
        regular_teacher = _optional_string(row, "regular_teacher_external_id")
        if priority == 5 and regular_teacher is None:
            issues.append(
                _error(
                    row,
                    "通常担当講師ID",
                    "担当講師優先度5では通常担当講師IDが必須です。",
                    "priority_five_without_regular_teacher",
                ),
            )

        for key, column_name in _TEACHER_REFERENCE_COLUMNS:
            teacher_id = _optional_string(row, key)
            if teacher_id is None:
                continue
            teacher = teachers.get(teacher_id)
            if teacher is None:
                issues.append(
                    _error(
                        row,
                        column_name,
                        "講師シートまたは既存データに存在しない講師IDです。",
                        "unknown_teacher",
                    ),
                )
                continue
            previous_teacher = (
                existing_lesson.teacher_for(key) if existing_lesson is not None else None
            )
            if not teacher.active and previous_teacher != teacher_id:
                issues.append(
                    _error(
                        row,
                        column_name,
                        "無効化済み講師は新規に選択できません。",
                        "inactive_teacher",
                    ),
                )

        _validate_teacher_qualifications(
            row,
            subject_code,
            priority,
            teachers,
            qualifications,
            issues,
        )
        _validate_preferred_teacher_duplicates(row, issues)


def _validate_teacher_qualifications(
    row: ParsedRow,
    subject_code: str,
    priority: int,
    teachers: dict[str, TeacherState],
    qualifications: dict[tuple[str, str], bool],
    issues: list[ImportIssue],
) -> None:
    regular_teacher = _optional_string(row, "regular_teacher_external_id")
    if regular_teacher in teachers and not qualifications.get(
        (regular_teacher, subject_code),
        False,
    ):
        severity = IssueSeverity.ERROR if priority == 5 else IssueSeverity.WARNING
        message = (
            "優先度5の通常担当講師が当該科目を指導不可のため反映できません。"
            if severity is IssueSeverity.ERROR
            else "通常担当講師が当該科目を指導不可です。確認後の反映は可能です。"
        )
        issues.append(
            ImportIssue(
                severity,
                message,
                sheet_name=row.sheet_name,
                row_number=row.row_number,
                column_name="通常担当講師ID",
                code="regular_teacher_not_qualified",
            ),
        )

    preferred_columns = (
        ("preferred_teacher_1_external_id", "第1希望講師ID"),
        ("preferred_teacher_2_external_id", "第2希望講師ID"),
        ("preferred_teacher_3_external_id", "第3希望講師ID"),
    )
    for key, column_name in preferred_columns:
        teacher_id = _optional_string(row, key)
        if teacher_id in teachers and not qualifications.get(
            (teacher_id, subject_code),
            False,
        ):
            issues.append(
                _warning(
                    row,
                    column_name,
                    "希望講師が当該科目を指導不可です。確認後の反映は可能です。",
                    "preferred_teacher_not_qualified",
                ),
            )


def _validate_preferred_teacher_duplicates(
    row: ParsedRow,
    issues: list[ImportIssue],
) -> None:
    preferred = [
        teacher_id
        for key in _PREFERRED_TEACHER_KEYS
        if (teacher_id := _optional_string(row, key)) is not None
    ]
    if len(preferred) != len(set(preferred)):
        issues.append(
            _warning(
                row,
                "第1～第3希望講師ID",
                "同じ講師が複数の希望順位に重複しています。",
                "duplicate_preferred_teacher",
            ),
        )


def _required_string(row: ParsedRow, key: str) -> str:
    return _string(row.values, key)


def _optional_string(row: ParsedRow, key: str) -> str | None:
    value = row.values[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise AssertionError(f"{row.sheet_name}:{row.row_number}:{key} は文字列ではありません")
    return value


def _required_bool(row: ParsedRow, key: str) -> bool:
    value = row.values[key]
    if not isinstance(value, bool):
        raise AssertionError(f"{row.sheet_name}:{row.row_number}:{key} はboolではありません")
    return value


def _required_int(row: ParsedRow, key: str) -> int:
    value = row.values[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{row.sheet_name}:{row.row_number}:{key} はintではありません")
    return value


def _string(values: dict[str, object] | object, key: str) -> str:
    if not isinstance(values, dict):
        raise AssertionError
    value = values[key]
    if not isinstance(value, str):
        raise AssertionError(f"{key} は文字列ではありません")
    return value


def _error(row: ParsedRow, column: str, message: str, code: str) -> ImportIssue:
    return ImportIssue(
        IssueSeverity.ERROR,
        message,
        sheet_name=row.sheet_name,
        row_number=row.row_number,
        column_name=column,
        code=code,
    )


def _warning(row: ParsedRow, column: str, message: str, code: str) -> ImportIssue:
    return ImportIssue(
        IssueSeverity.WARNING,
        message,
        sheet_name=row.sheet_name,
        row_number=row.row_number,
        column_name=column,
        code=code,
    )
