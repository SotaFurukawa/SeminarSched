"""Phase 2マスター管理ユースケース。"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import date, time, timedelta
from typing import Final, NoReturn

from summer_scheduler.application.dto import (
    DashboardSummary,
    LessonRequestDto,
    OpenDateDto,
    ProjectDetails,
    QualificationDto,
    SaveResult,
    StudentDto,
    SubjectDto,
    TeacherDto,
    TimeSlotDto,
)
from summer_scheduler.application.project_service import (
    ProjectFileError,
    ProjectService,
)
from summer_scheduler.domain.defaults import SCHOOL_LEVEL_LABELS
from summer_scheduler.domain.grades import grade_from_excel
from summer_scheduler.domain.identifiers import next_person_external_id
from summer_scheduler.domain.validation import (
    DomainValidationError,
    TimeSlotInput,
    ValidationIssue,
    raise_for_errors,
    validate_lesson_request,
    validate_project,
    validate_student,
    validate_subject,
    validate_teacher,
    validate_time_slots,
)
from summer_scheduler.infrastructure.db.models import (
    LessonRequest,
    OpenDate,
    Student,
    Subject,
    Teacher,
    TimeSlot,
)
from summer_scheduler.infrastructure.repositories.master_repository import (
    MasterRepository,
)

_SCHOOL_LEVEL_ORDER: Final = {
    "elementary": 0,
    "junior_high": 1,
    "high_school": 2,
}


def _resolve_open_date_time_slots(
    raw_value: str | None,
    default_ids: tuple[int, ...],
    enabled_ids: set[int],
) -> tuple[int, ...]:
    if not raw_value:
        return default_ids
    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return default_ids
    if not isinstance(parsed, list):
        return default_ids
    requested = {value for value in parsed if isinstance(value, int)}
    return tuple(value for value in default_ids if value in requested and value in enabled_ids)


class MasterDataService:
    """UIからtransactionとORMを隠してマスター操作を提供する。"""

    def __init__(self, projects: ProjectService) -> None:
        self._projects = projects

    def project_details(self) -> ProjectDetails:
        current = self._projects.require_project()
        return ProjectDetails(
            id=current.project_id,
            path=current.path,
            title=current.title,
            campus_name=current.campus_name,
            start_date=current.start_date,
            end_date=current.end_date,
        )

    def update_project(
        self,
        *,
        title: str,
        campus_name: str,
        start_date: date,
        end_date: date,
    ) -> ProjectDetails:
        raise_for_errors(
            validate_project(
                title=title,
                campus_name=campus_name,
                start_date=start_date,
                end_date=end_date,
            )
        )
        current = self._projects.require_project()
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            project = repository.get_project(current.project_id)
            if project is None:
                _raise_missing("project", "プロジェクト")
            campus = repository.get_campus(project.campus_id)
            if campus is None:
                _raise_missing("campus_name", "校舎")

            repository.update_campus(campus, name=campus_name.strip())
            repository.update_project(
                project,
                title=title.strip(),
                start_date=start_date,
                end_date=end_date,
            )
            self._synchronize_open_dates(
                repository,
                project_id=project.id,
                start_date=start_date,
                end_date=end_date,
            )

        summary = self._projects.refresh_current()
        return ProjectDetails(
            id=summary.project_id,
            path=summary.path,
            title=summary.title,
            campus_name=summary.campus_name,
            start_date=summary.start_date,
            end_date=summary.end_date,
        )

    def dashboard_summary(self) -> DashboardSummary:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            return DashboardSummary(
                student_count=len(repository.list_students(active_only=True)),
                teacher_count=len(repository.list_teachers(active_only=True)),
                lesson_request_count=len(repository.list_lesson_requests(project_id=project_id)),
            )

    # Time slots

    def list_time_slots(self) -> tuple[TimeSlotDto, ...]:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            rows = MasterRepository(session).list_time_slots(project_id=project_id)
            return tuple(_time_slot_dto(row) for row in rows)

    def save_time_slot(
        self,
        *,
        record_id: int | None,
        code: str,
        display_name: str,
        start_time: time,
        end_time: time,
        sort_order: int,
        enabled: bool,
    ) -> SaveResult:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        normalized_code = code.strip().upper()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            existing_rows = repository.list_time_slots(project_id=project_id)
            candidate = TimeSlotInput(
                normalized_code,
                display_name.strip(),
                start_time,
                end_time,
                sort_order,
                record_id,
            )
            values = [
                candidate
                if row.id == record_id
                else TimeSlotInput(
                    row.code,
                    row.display_name,
                    row.start_time,
                    row.end_time,
                    row.sort_order,
                    row.id,
                )
                for row in existing_rows
            ]
            if record_id is None:
                values.append(candidate)
            elif not any(row.id == record_id for row in existing_rows):
                _raise_missing("time_slot", "コマ")
            raise_for_errors(validate_time_slots(values))

            if record_id is None:
                row = repository.create_time_slot(
                    TimeSlot(
                        project_id=project_id,
                        code=normalized_code,
                        display_name=display_name.strip(),
                        start_time=start_time,
                        end_time=end_time,
                        sort_order=sort_order,
                        enabled=enabled,
                    )
                )
            else:
                existing_row = repository.get_time_slot(record_id)
                if existing_row is None:
                    _raise_missing("time_slot", "コマ")
                row = repository.update_time_slot(
                    existing_row,
                    code=normalized_code,
                    display_name=display_name.strip(),
                    start_time=start_time,
                    end_time=end_time,
                    sort_order=sort_order,
                    enabled=enabled,
                )
            return SaveResult(row.id)

    def delete_time_slot(self, record_id: int) -> None:
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            if not MasterRepository(session).delete_time_slot(record_id):
                _raise_missing("time_slot", "コマ")

    def reorder_time_slots(self, ordered_ids: Iterable[int]) -> None:
        """ドラッグ操作で指定された順にコマを並べ替える。"""
        project_id = self._projects.require_project().project_id
        requested = tuple(int(value) for value in ordered_ids)
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            rows = repository.list_time_slots(project_id=project_id)
            existing_ids = {row.id for row in rows}
            if len(requested) != len(existing_ids) or set(requested) != existing_ids:
                raise DomainValidationError(
                    [
                        ValidationIssue(
                            "time_slots",
                            "コマ一覧が更新されています。再読み込みしてから並べ替えてください。",
                        )
                    ]
                )
            rows_by_id = {row.id: row for row in rows}
            temporary_base = max((row.sort_order for row in rows), default=0) + len(rows) + 1
            for offset, row in enumerate(rows, start=1):
                row.sort_order = temporary_base + offset
            session.flush()
            for sort_order, record_id in enumerate(requested, start=1):
                rows_by_id[record_id].sort_order = sort_order

    # Open dates

    def list_open_dates(self) -> tuple[OpenDateDto, ...]:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            rows = repository.list_open_dates(project_id=project_id)
            enabled_ids = tuple(
                row.id for row in repository.list_time_slots(project_id=project_id) if row.enabled
            )
            enabled_set = set(enabled_ids)
            return tuple(
                OpenDateDto(
                    row.id,
                    row.date,
                    row.is_open,
                    row.note or "",
                    _resolve_open_date_time_slots(
                        row.enabled_time_slot_ids_json,
                        enabled_ids,
                        enabled_set,
                    ),
                )
                for row in rows
            )

    def set_open_dates_time_slots(
        self,
        days: Iterable[date],
        time_slot_ids: Iterable[int],
    ) -> None:
        """選択した開校日に、その日に使用できるコマをまとめて設定する。"""
        project = self._projects.require_project()
        selected_days = tuple(sorted(set(days)))
        selected_ids = tuple(dict.fromkeys(int(value) for value in time_slot_ids))
        issues: list[ValidationIssue] = []
        if not selected_days:
            issues.append(ValidationIssue("dates", "日付を1日以上選択してください。"))
        if not selected_ids:
            issues.append(ValidationIssue("time_slots", "使用するコマを1つ以上選択してください。"))
        for day in selected_days:
            if not project.start_date <= day <= project.end_date:
                issues.append(ValidationIssue("dates", f"講習期間外の日付です: {day.isoformat()}"))
        if issues:
            raise DomainValidationError(issues)

        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            valid_ids = {
                row.id
                for row in repository.list_time_slots(project_id=project.project_id)
                if row.enabled
            }
            if not set(selected_ids).issubset(valid_ids):
                raise DomainValidationError(
                    [
                        ValidationIssue(
                            "time_slots", "選択したコマが更新または使用停止されています。"
                        )
                    ]
                )
            encoded = json.dumps(list(selected_ids), ensure_ascii=False)
            for day in selected_days:
                row = repository.get_open_date_by_date(
                    project_id=project.project_id,
                    date_value=day,
                )
                if row is None:
                    repository.create_open_date(
                        OpenDate(
                            project_id=project.project_id,
                            date=day,
                            is_open=True,
                            note="",
                            enabled_time_slot_ids_json=encoded,
                        )
                    )
                else:
                    repository.update_open_date(
                        row,
                        enabled_time_slot_ids_json=encoded,
                    )

    def save_open_date_schedule(
        self,
        entries: Iterable[tuple[date, bool, Iterable[int]]],
    ) -> None:
        """画面上で編集した全日程を検証し、1トランザクションで保存する。"""
        project = self._projects.require_project()
        normalized: list[tuple[date, bool, tuple[int, ...]]] = []
        seen_days: set[date] = set()
        issues: list[ValidationIssue] = []
        for day, is_open, time_slot_ids in entries:
            slot_ids = tuple(dict.fromkeys(int(value) for value in time_slot_ids))
            if day in seen_days:
                issues.append(ValidationIssue("dates", f"日付が重複しています: {day.isoformat()}"))
            seen_days.add(day)
            if not project.start_date <= day <= project.end_date:
                issues.append(ValidationIssue("dates", f"講習期間外の日付です: {day.isoformat()}"))
            if is_open and not slot_ids:
                issues.append(
                    ValidationIssue(
                        "time_slots",
                        f"開校日には使用するコマを1つ以上選択してください: {day.isoformat()}",
                    )
                )
            normalized.append((day, is_open, slot_ids))
        if not normalized:
            issues.append(ValidationIssue("dates", "保存する日程がありません"))
        if issues:
            raise DomainValidationError(issues)

        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            valid_ids = {
                row.id
                for row in repository.list_time_slots(project_id=project.project_id)
                if row.enabled
            }
            selected_ids = {slot_id for _, _, slot_ids in normalized for slot_id in slot_ids}
            if not selected_ids.issubset(valid_ids):
                raise DomainValidationError(
                    [
                        ValidationIssue(
                            "time_slots", "選択したコマが更新または使用停止されています。"
                        )
                    ]
                )
            for day, is_open, slot_ids in normalized:
                row = repository.get_open_date_by_date(
                    project_id=project.project_id,
                    date_value=day,
                )
                values = {
                    "is_open": is_open,
                    "enabled_time_slot_ids_json": json.dumps(list(slot_ids), ensure_ascii=False),
                }
                if row is None:
                    repository.create_open_date(
                        OpenDate(
                            project_id=project.project_id,
                            date=day,
                            note="",
                            **values,
                        )
                    )
                else:
                    repository.update_open_date(row, **values)

    def set_open_date(self, day: date, *, is_open: bool, note: str) -> None:
        project = self._projects.require_project()
        if not project.start_date <= day <= project.end_date:
            raise DomainValidationError(
                [ValidationIssue("date", "講習期間外の日付は設定できません")]
            )
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            row = repository.get_open_date_by_date(
                project_id=project.project_id,
                date_value=day,
            )
            if row is None:
                repository.create_open_date(
                    OpenDate(
                        project_id=project.project_id,
                        date=day,
                        is_open=is_open,
                        note=note.strip(),
                    )
                )
            else:
                repository.update_open_date(
                    row,
                    is_open=is_open,
                    note=note.strip(),
                )

    def set_all_dates_open(self) -> None:
        self._set_dates(lambda _day: True)

    def set_open_dates_state(self, days: Iterable[date], *, is_open: bool) -> None:
        """選択された複数日を、1トランザクションで開校または休校にする。"""
        project = self._projects.require_project()
        selected_days = tuple(sorted(set(days)))
        issues: list[ValidationIssue] = []
        if not selected_days:
            issues.append(ValidationIssue("dates", "日付を1日以上選択してください"))
        for day in selected_days:
            if not project.start_date <= day <= project.end_date:
                issues.append(
                    ValidationIssue(
                        "dates",
                        f"講習期間外の日付は設定できません: {day.isoformat()}",
                    )
                )
        if issues:
            raise DomainValidationError(issues)

        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            for day in selected_days:
                row = repository.get_open_date_by_date(
                    project_id=project.project_id,
                    date_value=day,
                )
                if row is None:
                    repository.create_open_date(
                        OpenDate(
                            project_id=project.project_id,
                            date=day,
                            is_open=is_open,
                            note="",
                        )
                    )
                else:
                    repository.update_open_date(row, is_open=is_open)

    def set_weekday_closed(self, weekday: int) -> None:
        if weekday not in range(7):
            raise DomainValidationError([ValidationIssue("weekday", "曜日指定が不正です")])
        self._set_dates(lambda day: day.weekday() != weekday)

    def _set_dates(self, open_rule: Callable[[date], bool]) -> None:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            for row in repository.list_open_dates(project_id=project_id):
                is_open = open_rule(row.date)
                repository.update_open_date(row, is_open=is_open)

    # Students

    def list_students(
        self,
        *,
        search: str = "",
        grade: str = "",
        sort_by: str = "external_id",
        descending: bool = False,
    ) -> tuple[StudentDto, ...]:
        database = self._projects.require_database()
        with database.session_factory() as session:
            rows = MasterRepository(session).list_students()
            query = search.strip().casefold()
            filtered = [
                row
                for row in rows
                if (
                    not query or query in row.external_id.casefold() or query in row.name.casefold()
                )
                and _grade_matches(row.grade, grade)
            ]
            allowed_sort = {
                "external_id": lambda item: item.external_id.casefold(),
                "name": lambda item: item.name.casefold(),
                "grade": lambda item: item.grade.casefold(),
            }
            filtered.sort(
                key=allowed_sort.get(sort_by, allowed_sort["external_id"]),
                reverse=descending,
            )
            return tuple(_student_dto(row) for row in filtered)

    def save_student(
        self,
        *,
        record_id: int | None,
        external_id: str,
        name: str,
        grade: str,
        default_max_consecutive_slots: int,
        allow_gap: bool,
        note: str,
        active: bool,
    ) -> SaveResult:
        normalized_id = external_id.strip()
        normalized_name = name.strip()
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            if not normalized_id:
                if record_id is None:
                    normalized_id = next_person_external_id(
                        (row.external_id for row in repository.list_students()),
                        prefix="S",
                    )
                else:
                    existing_row = repository.get_student(record_id)
                    if existing_row is None:
                        _raise_missing("student", "生徒")
                    normalized_id = existing_row.external_id
            raise_for_errors(
                validate_student(
                    external_id=normalized_id,
                    name=name,
                    grade=grade,
                    max_consecutive_slots=default_max_consecutive_slots,
                )
            )
            duplicate = repository.get_student_by_external_id(normalized_id)
            if duplicate is not None and duplicate.id != record_id:
                _raise_duplicate("external_id", "生徒ID")
            warnings = tuple(
                f"同姓同名の生徒「{normalized_name}」が登録されています"
                for row in repository.list_students()
                if row.id != record_id and row.name == normalized_name
            )[:1]
            values = {
                "external_id": normalized_id,
                "name": normalized_name,
                "grade": grade.strip(),
                "default_max_consecutive_slots": default_max_consecutive_slots,
                "allow_gap": allow_gap,
                "note": note.strip(),
                "active": active,
            }
            if record_id is None:
                row = repository.create_student(Student(**values))
            else:
                existing_row = repository.get_student(record_id)
                if existing_row is None:
                    _raise_missing("student", "生徒")
                row = repository.update_student(existing_row, **values)
            return SaveResult(row.id, warnings)

    def deactivate_student(self, record_id: int) -> None:
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            if MasterRepository(session).deactivate_student(record_id) is None:
                _raise_missing("student", "生徒")

    def delete_student(self, record_id: int) -> None:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            if repository.get_student(record_id) is None:
                _raise_missing("student", "生徒")
            for lesson_request in repository.list_lesson_requests(
                project_id=project_id,
                student_id=record_id,
            ):
                repository.delete_lesson_request(lesson_request.id)
            repository.delete_student(record_id)

    # Teachers

    def list_teachers(
        self,
        *,
        search: str = "",
        sort_by: str = "external_id",
        descending: bool = False,
    ) -> tuple[TeacherDto, ...]:
        database = self._projects.require_database()
        with database.session_factory() as session:
            rows = MasterRepository(session).list_teachers()
            query = search.strip().casefold()
            filtered = [
                row
                for row in rows
                if not query or query in row.external_id.casefold() or query in row.name.casefold()
            ]
            key = (
                (lambda item: item.name.casefold())
                if sort_by == "name"
                else (lambda item: item.external_id.casefold())
            )
            filtered.sort(key=key, reverse=descending)
            return tuple(_teacher_dto(row) for row in filtered)

    def save_teacher(
        self,
        *,
        record_id: int | None,
        external_id: str,
        name: str,
        allow_gap: bool,
        note: str,
        active: bool,
    ) -> SaveResult:
        normalized_id = external_id.strip()
        normalized_name = name.strip()
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            if not normalized_id:
                if record_id is None:
                    normalized_id = next_person_external_id(
                        (row.external_id for row in repository.list_teachers()),
                        prefix="T",
                    )
                else:
                    existing_row = repository.get_teacher(record_id)
                    if existing_row is None:
                        _raise_missing("teacher", "講師")
                    normalized_id = existing_row.external_id
            raise_for_errors(validate_teacher(external_id=normalized_id, name=name))
            duplicate = repository.get_teacher_by_external_id(normalized_id)
            if duplicate is not None and duplicate.id != record_id:
                _raise_duplicate("external_id", "講師ID")
            warnings = tuple(
                f"同姓同名の講師「{normalized_name}」が登録されています"
                for row in repository.list_teachers()
                if row.id != record_id and row.name == normalized_name
            )[:1]
            values = {
                "external_id": normalized_id,
                "name": normalized_name,
                "allow_gap": allow_gap,
                "note": note.strip(),
                "active": active,
            }
            if record_id is None:
                row = repository.create_teacher(Teacher(**values))
            else:
                existing_row = repository.get_teacher(record_id)
                if existing_row is None:
                    _raise_missing("teacher", "講師")
                row = repository.update_teacher(existing_row, **values)
            return SaveResult(row.id, warnings)

    def deactivate_teacher(self, record_id: int) -> None:
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            if MasterRepository(session).deactivate_teacher(record_id) is None:
                _raise_missing("teacher", "講師")

    def delete_teacher(self, record_id: int) -> None:
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            if not MasterRepository(session).delete_teacher(record_id):
                _raise_missing("teacher", "講師")

    # Subjects

    def list_subjects(self, *, active_only: bool = False) -> tuple[SubjectDto, ...]:
        database = self._projects.require_database()
        with database.session_factory() as session:
            rows = MasterRepository(session).list_subjects(active_only=active_only)
            rows.sort(
                key=lambda row: (
                    _SCHOOL_LEVEL_ORDER.get(row.school_level, 99),
                    row.sort_order,
                    row.code,
                )
            )
            return tuple(_subject_dto(row) for row in rows)

    def save_subject(
        self,
        *,
        record_id: int | None,
        code: str,
        display_name: str,
        school_level: str,
        sort_order: int,
        active: bool,
    ) -> SaveResult:
        raise_for_errors(
            validate_subject(
                code=code,
                display_name=display_name,
                school_level=school_level,
                sort_order=sort_order,
            )
        )
        normalized_code = code.strip().upper()
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            duplicate = repository.get_subject_by_code(normalized_code)
            if duplicate is not None and duplicate.id != record_id:
                _raise_duplicate("code", "科目コード")
            values = {
                "code": normalized_code,
                "display_name": display_name.strip(),
                "school_level": school_level,
                "sort_order": sort_order,
                "active": active,
            }
            if record_id is None:
                row = repository.create_subject(Subject(**values))
            else:
                existing_row = repository.get_subject(record_id)
                if existing_row is None:
                    _raise_missing("subject", "科目")
                row = repository.update_subject(existing_row, **values)
            return SaveResult(row.id)

    def deactivate_subject(self, record_id: int) -> None:
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            if MasterRepository(session).deactivate_subject(record_id) is None:
                _raise_missing("subject", "科目")

    # Qualifications

    def list_qualifications(self, teacher_id: int) -> tuple[QualificationDto, ...]:
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            if repository.get_teacher(teacher_id) is None:
                _raise_missing("teacher", "講師")
            existing = {
                row.subject_id: row
                for row in repository.list_teacher_qualifications(teacher_id=teacher_id)
            }
            subjects = repository.list_subjects()
            subjects.sort(
                key=lambda row: (
                    _SCHOOL_LEVEL_ORDER.get(row.school_level, 99),
                    row.sort_order,
                )
            )
            return tuple(
                QualificationDto(
                    teacher_id=teacher_id,
                    subject_id=subject.id,
                    subject_code=subject.code,
                    subject_name=subject.display_name,
                    school_level=subject.school_level,
                    can_teach=(existing[subject.id].can_teach if subject.id in existing else False),
                    note=existing[subject.id].note or "" if subject.id in existing else "",
                )
                for subject in subjects
            )

    def set_qualification(
        self,
        teacher_id: int,
        subject_id: int,
        *,
        can_teach: bool,
    ) -> None:
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            _require_teacher_subject(repository, teacher_id, subject_id)
            repository.set_teacher_qualification(
                teacher_id=teacher_id,
                subject_id=subject_id,
                can_teach=can_teach,
            )

    def set_all_qualifications(
        self,
        teacher_id: int,
        school_level: str,
        *,
        can_teach: bool,
    ) -> None:
        if school_level not in SCHOOL_LEVEL_LABELS:
            raise DomainValidationError([ValidationIssue("school_level", "学校段階が不正です")])
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            if repository.get_teacher(teacher_id) is None:
                _raise_missing("teacher", "講師")
            for subject in repository.list_subjects():
                if subject.school_level == school_level:
                    repository.set_teacher_qualification(
                        teacher_id=teacher_id,
                        subject_id=subject.id,
                        can_teach=can_teach,
                    )

    def replace_qualifications(
        self,
        teacher_id: int,
        qualifications: dict[int, bool],
    ) -> None:
        """講師の資格マトリクスを1トランザクションで保存する。"""
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            if repository.get_teacher(teacher_id) is None:
                _raise_missing("teacher", "講師")
            subject_ids = {subject.id for subject in repository.list_subjects()}
            unknown_ids = set(qualifications) - subject_ids
            if unknown_ids:
                _raise_missing("subject", "科目")
            repository.replace_teacher_qualifications(
                teacher_id=teacher_id,
                qualifications=qualifications,
            )

    def copy_qualifications(
        self,
        *,
        source_teacher_id: int,
        target_teacher_id: int,
    ) -> None:
        if source_teacher_id == target_teacher_id:
            raise DomainValidationError(
                [ValidationIssue("source_teacher", "コピー元には別の講師を選択してください")]
            )
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            if repository.get_teacher(source_teacher_id) is None:
                _raise_missing("source_teacher", "コピー元講師")
            if repository.get_teacher(target_teacher_id) is None:
                _raise_missing("teacher", "コピー先講師")
            repository.copy_teacher_qualifications(
                source_teacher_id=source_teacher_id,
                target_teacher_id=target_teacher_id,
            )

    # Lesson requests

    def list_lesson_requests(
        self,
        *,
        student_id: int | None = None,
    ) -> tuple[LessonRequestDto, ...]:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            rows = repository.list_lesson_requests(
                project_id=project_id,
                student_id=student_id,
            )
            return tuple(_lesson_request_dto(repository, row) for row in rows)

    def save_lesson_request(
        self,
        *,
        record_id: int | None,
        student_id: int,
        subject_id: int,
        required_sessions: int,
        regular_teacher_id: int | None,
        regular_teacher_priority: int,
        preferred_teacher_1_id: int | None,
        preferred_teacher_2_id: int | None,
        preferred_teacher_3_id: int | None,
        one_to_one_required: bool,
        max_consecutive_slots_override: int | None,
        allow_gap_override: bool | None,
        note: str,
    ) -> SaveResult:
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            repository = MasterRepository(session)
            student = repository.get_student(student_id)
            subject = repository.get_subject(subject_id)
            if student is None:
                _raise_missing("student_id", "生徒")
            if subject is None:
                _raise_missing("subject_id", "科目")
            if (record_id is None and not student.active) or (
                record_id is None and not subject.active
            ):
                raise DomainValidationError(
                    [ValidationIssue("student_id", "無効な生徒・科目は新規選択できません")]
                )

            existing = repository.get_lesson_request(record_id) if record_id is not None else None
            if record_id is not None and existing is None:
                _raise_missing("lesson_request", "受講希望")
            duplicate = repository.get_lesson_request_by_student_subject(
                project_id=project_id,
                student_id=student_id,
                subject_id=subject_id,
            )
            if duplicate is not None and duplicate.id != record_id:
                _raise_duplicate("subject_id", "同一生徒・同一科目の受講希望")

            teacher_ids = (
                regular_teacher_id,
                preferred_teacher_1_id,
                preferred_teacher_2_id,
                preferred_teacher_3_id,
            )
            previous_teacher_ids = _lesson_teacher_ids(existing)
            for teacher_id in (value for value in teacher_ids if value is not None):
                teacher = repository.get_teacher(teacher_id)
                if teacher is None:
                    _raise_missing("teacher_id", "講師")
                if not teacher.active and teacher_id not in previous_teacher_ids:
                    raise DomainValidationError(
                        [ValidationIssue("teacher_id", "無効な講師は新規選択できません")]
                    )

            can_teach = (
                repository.can_teacher_teach(regular_teacher_id, subject_id)
                if regular_teacher_id is not None
                else None
            )
            issues = validate_lesson_request(
                required_sessions=required_sessions,
                regular_teacher_priority=regular_teacher_priority,
                regular_teacher_id=regular_teacher_id,
                preferred_teacher_ids=teacher_ids[1:],
                max_consecutive_slots_override=max_consecutive_slots_override,
                regular_teacher_can_teach=can_teach,
            )
            raise_for_errors(issues)
            values = {
                "project_id": project_id,
                "student_id": student_id,
                "subject_id": subject_id,
                "required_sessions": required_sessions,
                "regular_teacher_id_optional": regular_teacher_id,
                "regular_teacher_priority": regular_teacher_priority,
                "preferred_teacher_1_id_optional": preferred_teacher_1_id,
                "preferred_teacher_2_id_optional": preferred_teacher_2_id,
                "preferred_teacher_3_id_optional": preferred_teacher_3_id,
                "one_to_one_required": one_to_one_required,
                "max_consecutive_slots_override_optional": (max_consecutive_slots_override),
                "allow_gap_override_optional": allow_gap_override,
                "note": note.strip(),
            }
            if existing is None:
                row = repository.create_lesson_request(LessonRequest(**values))
            else:
                row = repository.update_lesson_request(existing, **values)
            warnings = tuple(issue.message for issue in issues if issue.severity == "warning")
            return SaveResult(row.id, warnings)

    def delete_lesson_request(self, record_id: int) -> None:
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            if not MasterRepository(session).delete_lesson_request(record_id):
                _raise_missing("lesson_request", "受講希望")

    @staticmethod
    def _synchronize_open_dates(
        repository: MasterRepository,
        *,
        project_id: int,
        start_date: date,
        end_date: date,
    ) -> None:
        existing = {row.date: row for row in repository.list_open_dates(project_id=project_id)}
        desired: set[date] = set()
        current = start_date
        while current <= end_date:
            desired.add(current)
            if current not in existing:
                repository.create_open_date(
                    OpenDate(
                        project_id=project_id,
                        date=current,
                        is_open=True,
                        note="",
                    )
                )
            current += timedelta(days=1)
        for day, row in existing.items():
            if day not in desired:
                repository.delete_open_date(row.id)


def _student_dto(row: Student) -> StudentDto:
    return StudentDto(
        row.id,
        row.external_id,
        row.name,
        row.grade,
        row.default_max_consecutive_slots,
        row.allow_gap,
        row.note or "",
        row.active,
    )


def _teacher_dto(row: Teacher) -> TeacherDto:
    return TeacherDto(
        row.id,
        row.external_id,
        row.name,
        row.allow_gap,
        row.note or "",
        row.active,
    )


def _subject_dto(row: Subject) -> SubjectDto:
    return SubjectDto(
        row.id,
        row.code,
        row.display_name,
        row.school_level,
        row.sort_order,
        row.active,
    )


def _time_slot_dto(row: TimeSlot) -> TimeSlotDto:
    return TimeSlotDto(
        row.id,
        row.code,
        row.display_name,
        row.start_time,
        row.end_time,
        row.sort_order,
        row.enabled,
    )


def _lesson_request_dto(
    repository: MasterRepository,
    row: LessonRequest,
) -> LessonRequestDto:
    student = repository.get_student(row.student_id)
    subject = repository.get_subject(row.subject_id)
    if student is None or subject is None:
        raise ProjectFileError("受講希望の参照先が見つかりません")
    teacher_name = ""
    if row.regular_teacher_id_optional is not None:
        teacher = repository.get_teacher(row.regular_teacher_id_optional)
        teacher_name = teacher.name if teacher is not None else ""
    return LessonRequestDto(
        id=row.id,
        project_id=row.project_id,
        student_id=row.student_id,
        student_name=student.name,
        subject_id=row.subject_id,
        subject_name=subject.display_name,
        required_sessions=row.required_sessions,
        regular_teacher_id=row.regular_teacher_id_optional,
        regular_teacher_name=teacher_name,
        regular_teacher_priority=row.regular_teacher_priority,
        preferred_teacher_1_id=row.preferred_teacher_1_id_optional,
        preferred_teacher_2_id=row.preferred_teacher_2_id_optional,
        preferred_teacher_3_id=row.preferred_teacher_3_id_optional,
        one_to_one_required=row.one_to_one_required,
        max_consecutive_slots_override=row.max_consecutive_slots_override_optional,
        allow_gap_override=row.allow_gap_override_optional,
        note=row.note or "",
    )


def _lesson_teacher_ids(row: LessonRequest | None) -> set[int]:
    if row is None:
        return set()
    return {
        value
        for value in (
            row.regular_teacher_id_optional,
            row.preferred_teacher_1_id_optional,
            row.preferred_teacher_2_id_optional,
            row.preferred_teacher_3_id_optional,
        )
        if value is not None
    }


def _require_teacher_subject(
    repository: MasterRepository,
    teacher_id: int,
    subject_id: int,
) -> None:
    if repository.get_teacher(teacher_id) is None:
        _raise_missing("teacher", "講師")
    if repository.get_subject(subject_id) is None:
        _raise_missing("subject", "科目")


def _raise_missing(field: str, label: str) -> NoReturn:
    raise DomainValidationError(
        [ValidationIssue(field, f"{label}が見つかりません", code="not_found")]
    )


def _raise_duplicate(field: str, label: str) -> NoReturn:
    raise DomainValidationError(
        [ValidationIssue(field, f"{label}が重複しています", code="duplicate")]
    )


def _grade_matches(value: str, selected: str) -> bool:
    if not selected:
        return True
    normalized_value = _normalize_grade(value)
    normalized_selected = _normalize_grade(selected)
    known_grades = {
        *(f"小{year}" for year in range(1, 7)),
        *(f"中{year}" for year in range(1, 4)),
        *(f"高{year}" for year in range(1, 4)),
    }
    if normalized_selected == "その他":
        return normalized_value not in known_grades
    return normalized_value == normalized_selected


def _normalize_grade(value: str) -> str:
    return grade_from_excel(value)
