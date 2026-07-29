"""Phase 3のプロジェクト全体入力検証。

取込み固有の行・列検証とは分離し、DBに保存済みの入力が最適化へ渡せる状態かを
再現可能な規則で検査する。Phase 4以降はAssignment等の検査をこのサービスへ追加する。
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from summer_scheduler.application.phase3_dto import (
    IssueSeverity,
    ValidationIssueDto,
)
from summer_scheduler.application.project_service import ProjectFileError, ProjectService
from summer_scheduler.domain.time_ranges import time_ranges_overlap
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    CourseProject,
    GroupLesson,
    GroupLessonStudent,
    LessonRequest,
    OpenDate,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TeacherQualification,
    TimeSlot,
    ValidationIssue,
)


@dataclass(frozen=True, slots=True)
class _Issue:
    severity: IssueSeverity
    issue_type: str
    entity_type: str
    entity_id: str | None
    message: str
    details: dict[str, object]


@dataclass(frozen=True, slots=True)
class _FixedInterval:
    group_id: int
    group_code: str
    day: date
    start: time
    end: time


class ProjectValidationService:
    """現在のプロジェクトを検査し、結果をValidationIssueへ永続化する。"""

    def __init__(self, projects: ProjectService) -> None:
        self._projects = projects

    def run_validation(self) -> tuple[ValidationIssueDto, ...]:
        """検証結果を再計算し、前回の未解決結果を解決済みにして保存する。"""
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            project = session.get(CourseProject, project_id)
            if project is None:
                raise ProjectFileError("プロジェクト情報が見つかりません")

            issues = _collect_issues(session, project)
            session.execute(
                update(ValidationIssue)
                .where(
                    ValidationIssue.project_id == project_id,
                    ValidationIssue.resolved.is_(False),
                )
                .values(resolved=True)
            )
            rows = [
                ValidationIssue(
                    project_id=project_id,
                    severity=issue.severity,
                    issue_type=issue.issue_type,
                    entity_type=issue.entity_type,
                    entity_id_optional=issue.entity_id,
                    message=issue.message,
                    details_json=json.dumps(
                        issue.details,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    resolved=False,
                )
                for issue in issues
            ]
            session.add_all(rows)
            session.flush()
            return tuple(_issue_dto(row) for row in rows)

    def list_issues(
        self,
        *,
        include_resolved: bool = False,
    ) -> tuple[ValidationIssueDto, ...]:
        """保存済み検証結果を重要度・ID順で返す。"""
        project_id = self._projects.require_project().project_id
        database = self._projects.require_database()
        with database.session_factory() as session:
            statement = select(ValidationIssue).where(ValidationIssue.project_id == project_id)
            if not include_resolved:
                statement = statement.where(ValidationIssue.resolved.is_(False))
            rows = list(session.scalars(statement.order_by(ValidationIssue.id)))
            rows.sort(
                key=lambda row: (
                    {"error": 0, "warning": 1, "info": 2}.get(row.severity, 9),
                    row.id,
                )
            )
            return tuple(_issue_dto(row) for row in rows)


def _collect_issues(session: Session, project: CourseProject) -> list[_Issue]:
    students = list(session.scalars(select(Student).order_by(Student.id)))
    teachers = list(session.scalars(select(Teacher).order_by(Teacher.id)))
    subjects = list(session.scalars(select(Subject).order_by(Subject.id)))
    requests = list(
        session.scalars(
            select(LessonRequest)
            .where(LessonRequest.project_id == project.id)
            .order_by(LessonRequest.id)
        )
    )
    slots = list(
        session.scalars(
            select(TimeSlot)
            .where(TimeSlot.project_id == project.id)
            .order_by(TimeSlot.sort_order, TimeSlot.id)
        )
    )
    open_dates = list(
        session.scalars(
            select(OpenDate).where(OpenDate.project_id == project.id).order_by(OpenDate.date)
        )
    )
    student_availability = list(
        session.scalars(
            select(StudentAvailability).where(StudentAvailability.project_id == project.id)
        )
    )
    teacher_availability = list(
        session.scalars(
            select(TeacherAvailability).where(TeacherAvailability.project_id == project.id)
        )
    )
    group_lessons = list(
        session.scalars(
            select(GroupLesson)
            .where(GroupLesson.project_id == project.id)
            .order_by(GroupLesson.date, GroupLesson.start_time, GroupLesson.id)
        )
    )
    group_members = list(session.scalars(select(GroupLessonStudent)))
    qualifications = list(session.scalars(select(TeacherQualification)))
    assignments = list(
        session.scalars(
            select(Assignment)
            .where(Assignment.project_id == project.id)
            .order_by(
                Assignment.date,
                Assignment.time_slot_id,
                Assignment.id,
            )
        )
    )

    students_by_id = {row.id: row for row in students}
    teachers_by_id = {row.id: row for row in teachers}
    subjects_by_id = {row.id: row for row in subjects}
    slots_by_id = {row.id: row for row in slots}
    open_by_day = {row.date: row.is_open for row in open_dates}
    qualification_map = {(row.teacher_id, row.subject_id): row.can_teach for row in qualifications}
    members_by_group: dict[int, set[int]] = defaultdict(set)
    for row in group_members:
        members_by_group[row.group_lesson_id].add(row.student_id)

    issues: list[_Issue] = []
    issues.extend(_duplicate_name_issues(students, teachers))
    issues.extend(_time_slot_issues(slots))
    issues.extend(
        _availability_issues(
            project,
            student_availability,
            teacher_availability,
            students_by_id,
            teachers_by_id,
            slots_by_id,
            open_by_day,
        )
    )
    issues.extend(
        _group_lesson_issues(
            project,
            group_lessons,
            members_by_group,
            students_by_id,
            teachers_by_id,
            subjects_by_id,
            qualification_map,
            open_by_day,
        )
    )
    issues.extend(
        _lesson_request_issues(
            requests,
            students_by_id,
            teachers_by_id,
            subjects_by_id,
            qualification_map,
        )
    )
    issues.extend(
        _capacity_issues(
            requests,
            student_availability,
            teacher_availability,
            slots_by_id,
            group_lessons,
            members_by_group,
            students_by_id,
            teachers_by_id,
        )
    )
    issues.extend(
        _assignment_issues(
            assignments,
            requests_by_id={row.id: row for row in requests},
            slots=slots_by_id,
            groups=group_lessons,
            members_by_group=members_by_group,
        )
    )
    return issues


def _duplicate_name_issues(
    students: list[Student],
    teachers: list[Teacher],
) -> list[_Issue]:
    issues: list[_Issue] = []
    for entity_type, rows in (("student", students), ("teacher", teachers)):
        ids_by_name: dict[str, list[int]] = defaultdict(list)
        for row in rows:
            ids_by_name[row.name.strip()].append(row.id)
        for name, ids in sorted(ids_by_name.items()):
            if name and len(ids) > 1:
                issues.append(
                    _Issue(
                        "warning",
                        "duplicate_name",
                        entity_type,
                        None,
                        f"{name}という同姓同名の{_entity_label(entity_type)}が複数います",
                        {"name": name, "ids": ids},
                    )
                )
    return issues


def _time_slot_issues(slots: list[TimeSlot]) -> list[_Issue]:
    issues: list[_Issue] = []
    enabled = [slot for slot in slots if slot.enabled]
    for index, left in enumerate(enabled):
        for right in enabled[index + 1 :]:
            if time_ranges_overlap(
                left.start_time,
                left.end_time,
                right.start_time,
                right.end_time,
            ):
                issues.append(
                    _Issue(
                        "error",
                        "time_slot_overlap",
                        "time_slot",
                        str(left.id),
                        f"コマ{left.code}と{right.code}の時刻が重複しています",
                        {
                            "left_slot_id": left.id,
                            "right_slot_id": right.id,
                            "left_code": left.code,
                            "right_code": right.code,
                        },
                    )
                )
    return issues


def _availability_issues(
    project: CourseProject,
    student_rows: list[StudentAvailability],
    teacher_rows: list[TeacherAvailability],
    students: dict[int, Student],
    teachers: dict[int, Teacher],
    slots: dict[int, TimeSlot],
    open_by_day: dict[date, bool],
) -> list[_Issue]:
    issues: list[_Issue] = []
    for entity_type, rows, entities, id_attribute in (
        ("student", student_rows, students, "student_id"),
        ("teacher", teacher_rows, teachers, "teacher_id"),
    ):
        for row in rows:
            entity_id = int(getattr(row, id_attribute))
            entity = entities.get(entity_id)
            if entity is not None and not entity.active:
                issues.append(
                    _Issue(
                        "warning",
                        "inactive_master_reference",
                        entity_type,
                        str(entity_id),
                        f"無効化済み{_entity_label(entity_type)}の希望データがあります",
                        {"date": row.date.isoformat(), "time_slot_id": row.time_slot_id},
                    )
                )
            if row.date < project.start_date or row.date > project.end_date:
                issues.append(
                    _Issue(
                        "error",
                        "availability_outside_project",
                        entity_type,
                        str(entity_id),
                        f"{row.date.isoformat()}は講習期間外です",
                        {"date": row.date.isoformat(), "time_slot_id": row.time_slot_id},
                    )
                )
            elif not open_by_day.get(row.date, False):
                issues.append(
                    _Issue(
                        "error",
                        "availability_on_closed_date",
                        entity_type,
                        str(entity_id),
                        f"{row.date.isoformat()}の休校日に希望データがあります",
                        {"date": row.date.isoformat(), "time_slot_id": row.time_slot_id},
                    )
                )
            slot = slots.get(row.time_slot_id)
            if slot is not None and not slot.enabled:
                issues.append(
                    _Issue(
                        "warning",
                        "inactive_master_reference",
                        "time_slot",
                        str(slot.id),
                        f"無効化済みコマ{slot.code}の希望データがあります",
                        {"date": row.date.isoformat(), "entity_type": entity_type},
                    )
                )
    return issues


def _group_lesson_issues(
    project: CourseProject,
    groups: list[GroupLesson],
    members_by_group: dict[int, set[int]],
    students: dict[int, Student],
    teachers: dict[int, Teacher],
    subjects: dict[int, Subject],
    qualifications: dict[tuple[int, int], bool],
    open_by_day: dict[date, bool],
) -> list[_Issue]:
    issues: list[_Issue] = []
    for group in groups:
        if group.date < project.start_date or group.date > project.end_date:
            issues.append(
                _group_issue(
                    group,
                    "group_outside_project",
                    f"集団授業{group.group_code}は講習期間外です",
                )
            )
        elif not open_by_day.get(group.date, False):
            issues.append(
                _group_issue(
                    group,
                    "group_on_closed_date",
                    f"集団授業{group.group_code}が休校日に設定されています",
                )
            )
        subject = subjects.get(group.subject_id)
        if subject is not None and not subject.active:
            issues.append(
                _group_issue(
                    group,
                    "inactive_master_reference",
                    f"集団授業{group.group_code}が無効化済み科目を参照しています",
                    severity="warning",
                )
            )
        if group.teacher_id_optional is not None:
            teacher = teachers.get(group.teacher_id_optional)
            if teacher is not None and not teacher.active:
                issues.append(
                    _group_issue(
                        group,
                        "inactive_master_reference",
                        f"集団授業{group.group_code}が無効化済み講師を参照しています",
                        severity="warning",
                    )
                )
            if not qualifications.get(
                (group.teacher_id_optional, group.subject_id),
                False,
            ):
                issues.append(
                    _group_issue(
                        group,
                        "group_teacher_unqualified",
                        f"集団授業{group.group_code}の担当講師は科目資格がありません",
                    )
                )
        for student_id in sorted(members_by_group.get(group.id, set())):
            student = students.get(student_id)
            if student is not None and not student.active:
                issues.append(
                    _group_issue(
                        group,
                        "inactive_master_reference",
                        f"集団授業{group.group_code}が無効化済み生徒を参照しています",
                        severity="warning",
                        details={"student_id": student_id},
                    )
                )

    for index, left in enumerate(groups):
        for right in groups[index + 1 :]:
            if left.date != right.date or not time_ranges_overlap(
                left.start_time,
                left.end_time,
                right.start_time,
                right.end_time,
            ):
                continue
            if (
                left.teacher_id_optional is not None
                and left.teacher_id_optional == right.teacher_id_optional
            ):
                issues.append(
                    _Issue(
                        "error",
                        "group_teacher_overlap",
                        "teacher",
                        str(left.teacher_id_optional),
                        (
                            f"集団授業{left.group_code}と{right.group_code}で"
                            "同じ講師の時刻が重複しています"
                        ),
                        {"left_group_id": left.id, "right_group_id": right.id},
                    )
                )
            common_students = members_by_group.get(left.id, set()) & members_by_group.get(
                right.id, set()
            )
            for student_id in sorted(common_students):
                issues.append(
                    _Issue(
                        "error",
                        "group_student_overlap",
                        "student",
                        str(student_id),
                        (
                            f"集団授業{left.group_code}と{right.group_code}で"
                            "同じ生徒の時刻が重複しています"
                        ),
                        {"left_group_id": left.id, "right_group_id": right.id},
                    )
                )
    return issues


def _lesson_request_issues(
    requests: list[LessonRequest],
    students: dict[int, Student],
    teachers: dict[int, Teacher],
    subjects: dict[int, Subject],
    qualifications: dict[tuple[int, int], bool],
) -> list[_Issue]:
    issues: list[_Issue] = []
    for request in requests:
        if request.required_sessions <= 0:
            issues.append(
                _request_issue(
                    request,
                    "invalid_required_sessions",
                    "必要回数は1以上で設定してください",
                )
            )
        if request.regular_teacher_priority not in {1, 2, 3, 4, 5}:
            issues.append(
                _request_issue(
                    request,
                    "invalid_teacher_priority",
                    "通常担当講師の優先度は1～5で設定してください",
                )
            )
        student = students.get(request.student_id)
        subject = subjects.get(request.subject_id)
        if student is not None and not student.active:
            issues.append(
                _request_issue(
                    request,
                    "inactive_master_reference",
                    "無効化済み生徒の受講希望があります",
                    severity="warning",
                )
            )
        if subject is not None and not subject.active:
            issues.append(
                _request_issue(
                    request,
                    "inactive_master_reference",
                    "無効化済み科目の受講希望があります",
                    severity="warning",
                )
            )
        regular_teacher_id = request.regular_teacher_id_optional
        if request.regular_teacher_priority == 5 and regular_teacher_id is None:
            issues.append(
                _request_issue(
                    request,
                    "priority5_teacher_missing",
                    "優先度5ですが通常担当講師が設定されていません",
                )
            )
        if regular_teacher_id is not None:
            regular_teacher = teachers.get(regular_teacher_id)
            if regular_teacher is not None and not regular_teacher.active:
                issues.append(
                    _request_issue(
                        request,
                        "inactive_master_reference",
                        "無効化済み講師が通常担当に設定されています",
                        severity="warning",
                    )
                )
            if not qualifications.get((regular_teacher_id, request.subject_id), False):
                issues.append(
                    _request_issue(
                        request,
                        "regular_teacher_unqualified",
                        "通常担当講師はこの科目の資格がありません",
                    )
                )
        for rank, teacher_id in enumerate(
            (
                request.preferred_teacher_1_id_optional,
                request.preferred_teacher_2_id_optional,
                request.preferred_teacher_3_id_optional,
            ),
            start=1,
        ):
            if teacher_id is None:
                continue
            teacher = teachers.get(teacher_id)
            if teacher is not None and not teacher.active:
                issues.append(
                    _request_issue(
                        request,
                        "inactive_master_reference",
                        f"第{rank}希望講師が無効化済みです",
                        severity="warning",
                    )
                )
            if not qualifications.get((teacher_id, request.subject_id), False):
                issues.append(
                    _request_issue(
                        request,
                        "preferred_teacher_unqualified",
                        f"第{rank}希望講師はこの科目の資格がありません",
                        severity="warning",
                    )
                )
    return issues


def _capacity_issues(
    requests: list[LessonRequest],
    student_rows: list[StudentAvailability],
    teacher_rows: list[TeacherAvailability],
    slots: dict[int, TimeSlot],
    groups: list[GroupLesson],
    members_by_group: dict[int, set[int]],
    students: dict[int, Student],
    teachers: dict[int, Teacher],
) -> list[_Issue]:
    student_possible = {
        (row.student_id, row.date, row.time_slot_id)
        for row in student_rows
        if row.availability_level > 0
        and _slot_is_usable_for_student(
            row.student_id,
            row.date,
            row.time_slot_id,
            slots,
            groups,
            members_by_group,
        )
    }
    teacher_possible = {
        (row.teacher_id, row.date, row.time_slot_id)
        for row in teacher_rows
        if row.availability_level > 0
        and _slot_is_usable_for_teacher(
            row.teacher_id,
            row.date,
            row.time_slot_id,
            slots,
            groups,
        )
    }
    required_by_student: dict[int, int] = defaultdict(int)
    for request in requests:
        required_by_student[request.student_id] += request.required_sessions

    issues: list[_Issue] = []
    for student_id, required in sorted(required_by_student.items()):
        possible = sum(1 for key in student_possible if key[0] == student_id)
        if possible < required:
            student = students.get(student_id)
            name = student.name if student is not None else str(student_id)
            issues.append(
                _Issue(
                    "error",
                    "student_availability_shortage",
                    "student",
                    str(student_id),
                    f"{name}の可能枠{possible}件は必要授業数{required}件より少ないです",
                    {"possible_slots": possible, "required_sessions": required},
                )
            )

    for request in requests:
        teacher_id = request.regular_teacher_id_optional
        if request.regular_teacher_priority != 5 or teacher_id is None:
            continue
        student_keys = {
            (day, slot_id)
            for student_id, day, slot_id in student_possible
            if student_id == request.student_id
        }
        teacher_keys = {
            (day, slot_id)
            for candidate_teacher_id, day, slot_id in teacher_possible
            if candidate_teacher_id == teacher_id
        }
        common = len(student_keys & teacher_keys)
        if common < request.required_sessions:
            student = students.get(request.student_id)
            teacher = teachers.get(teacher_id)
            student_name = student.name if student is not None else str(request.student_id)
            teacher_name = teacher.name if teacher is not None else str(teacher_id)
            issues.append(
                _request_issue(
                    request,
                    "priority5_common_availability_shortage",
                    (
                        f"{student_name}と優先度5担当の{teacher_name}の共通可能枠"
                        f"{common}件は必要回数{request.required_sessions}件より少ないです"
                    ),
                    details={
                        "common_slots": common,
                        "required_sessions": request.required_sessions,
                        "teacher_id": teacher_id,
                    },
                )
            )
    return issues


def _assignment_issues(
    assignments: list[Assignment],
    *,
    requests_by_id: dict[int, LessonRequest],
    slots: dict[int, TimeSlot],
    groups: list[GroupLesson],
    members_by_group: dict[int, set[int]],
) -> list[_Issue]:
    """現在割当とロック済み入力の明白な矛盾を最適化前に検出する。"""
    issues: list[_Issue] = []
    by_teacher_slot: dict[tuple[int, date, int], list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        by_teacher_slot[(assignment.teacher_id, assignment.date, assignment.time_slot_id)].append(
            assignment
        )

    for (_teacher_id, _day, _slot_id), rows in sorted(by_teacher_slot.items()):
        if len(rows) <= 1:
            continue
        one_to_one_rows = [
            row
            for row in rows
            if (request := requests_by_id.get(row.lesson_request_id)) is not None
            and request.one_to_one_required
        ]
        for row in one_to_one_rows:
            request = requests_by_id[row.lesson_request_id]
            conflicting_rows = [
                candidate
                for candidate in rows
                if candidate.id != row.id
                and (candidate_request := requests_by_id.get(candidate.lesson_request_id))
                is not None
                and candidate_request.student_id != request.student_id
            ]
            if not conflicting_rows:
                continue
            issues.append(
                _assignment_issue(
                    row,
                    "one_to_one_assignment_conflict",
                    "1対1必須の授業と同じ講師・同じ日時に別の生徒が配置されています",
                    details={
                        "conflicting_assignment_ids": [
                            candidate.id for candidate in conflicting_rows
                        ]
                    },
                )
            )

    locked = [row for row in assignments if row.is_locked]
    locked_by_teacher_slot: dict[tuple[int, date, int], list[Assignment]] = defaultdict(list)
    for assignment in locked:
        locked_by_teacher_slot[
            (assignment.teacher_id, assignment.date, assignment.time_slot_id)
        ].append(assignment)
    for (teacher_id, day, slot_id), rows in sorted(locked_by_teacher_slot.items()):
        student_ids = {
            request.student_id
            for row in rows
            if (request := requests_by_id.get(row.lesson_request_id)) is not None
        }
        if len(student_ids) > 2:
            issues.append(
                _Issue(
                    "error",
                    "fixed_teacher_capacity_conflict",
                    "teacher",
                    str(teacher_id),
                    "ロック済み授業が同じ講師・同じ日時に3件以上あります",
                    {
                        "date": day.isoformat(),
                        "time_slot_id": slot_id,
                        "assignment_ids": [row.id for row in rows],
                    },
                )
            )

    locked_by_day: dict[date, list[Assignment]] = defaultdict(list)
    for assignment in locked:
        locked_by_day[assignment.date].append(assignment)
    for day, day_rows in sorted(locked_by_day.items()):
        for index, left in enumerate(day_rows):
            left_slot = slots.get(left.time_slot_id)
            left_request = requests_by_id.get(left.lesson_request_id)
            if left_slot is None or left_request is None:
                continue
            for right in day_rows[index + 1 :]:
                right_slot = slots.get(right.time_slot_id)
                right_request = requests_by_id.get(right.lesson_request_id)
                if right_slot is None or right_request is None:
                    continue
                if not time_ranges_overlap(
                    left_slot.start_time,
                    left_slot.end_time,
                    right_slot.start_time,
                    right_slot.end_time,
                ):
                    continue
                if left_request.student_id == right_request.student_id:
                    issues.append(
                        _Issue(
                            "error",
                            "fixed_student_time_conflict",
                            "student",
                            str(left_request.student_id),
                            "同じ生徒のロック済み授業の時刻が重複しています",
                            {
                                "date": day.isoformat(),
                                "left_assignment_id": left.id,
                                "right_assignment_id": right.id,
                            },
                        )
                    )
                if left.teacher_id == right.teacher_id and left.time_slot_id != right.time_slot_id:
                    issues.append(
                        _Issue(
                            "error",
                            "fixed_teacher_time_conflict",
                            "teacher",
                            str(left.teacher_id),
                            "同じ講師の別コマにあるロック済み授業の時刻が重複しています",
                            {
                                "date": day.isoformat(),
                                "left_assignment_id": left.id,
                                "right_assignment_id": right.id,
                            },
                        )
                    )

    for assignment in locked:
        slot = slots.get(assignment.time_slot_id)
        request = requests_by_id.get(assignment.lesson_request_id)
        if slot is None or request is None:
            continue
        for group in groups:
            if group.date != assignment.date or not time_ranges_overlap(
                slot.start_time,
                slot.end_time,
                group.start_time,
                group.end_time,
            ):
                continue
            if request.student_id in members_by_group.get(group.id, set()):
                issues.append(
                    _assignment_issue(
                        assignment,
                        "fixed_assignment_group_student_conflict",
                        "ロック済み個別授業が生徒の集団授業と重複しています",
                        details={"group_lesson_id": group.id},
                    )
                )
            if (
                group.teacher_id_optional is not None
                and assignment.teacher_id == group.teacher_id_optional
            ):
                issues.append(
                    _assignment_issue(
                        assignment,
                        "fixed_assignment_group_teacher_conflict",
                        "ロック済み個別授業が講師の集団授業と重複しています",
                        details={"group_lesson_id": group.id},
                    )
                )
    return issues


def _slot_is_usable_for_student(
    student_id: int,
    day: date,
    slot_id: int,
    slots: dict[int, TimeSlot],
    groups: list[GroupLesson],
    members_by_group: dict[int, set[int]],
) -> bool:
    slot = slots.get(slot_id)
    if slot is None or not slot.enabled:
        return False
    return not any(
        group.date == day
        and student_id in members_by_group.get(group.id, set())
        and time_ranges_overlap(
            slot.start_time,
            slot.end_time,
            group.start_time,
            group.end_time,
        )
        for group in groups
    )


def _slot_is_usable_for_teacher(
    teacher_id: int,
    day: date,
    slot_id: int,
    slots: dict[int, TimeSlot],
    groups: list[GroupLesson],
) -> bool:
    slot = slots.get(slot_id)
    if slot is None or not slot.enabled:
        return False
    return not any(
        group.date == day
        and group.teacher_id_optional == teacher_id
        and time_ranges_overlap(
            slot.start_time,
            slot.end_time,
            group.start_time,
            group.end_time,
        )
        for group in groups
    )


def _group_issue(
    group: GroupLesson,
    issue_type: str,
    message: str,
    *,
    severity: IssueSeverity = "error",
    details: dict[str, object] | None = None,
) -> _Issue:
    payload: dict[str, object] = {
        "group_code": group.group_code,
        "date": group.date.isoformat(),
    }
    if details is not None:
        payload.update(details)
    return _Issue(
        severity,
        issue_type,
        "group_lesson",
        str(group.id),
        message,
        payload,
    )


def _assignment_issue(
    assignment: Assignment,
    issue_type: str,
    message: str,
    *,
    details: dict[str, object] | None = None,
) -> _Issue:
    payload: dict[str, object] = {
        "lesson_request_id": assignment.lesson_request_id,
        "date": assignment.date.isoformat(),
        "time_slot_id": assignment.time_slot_id,
        "teacher_id": assignment.teacher_id,
    }
    if details is not None:
        payload.update(details)
    return _Issue(
        "error",
        issue_type,
        "assignment",
        str(assignment.id),
        message,
        payload,
    )


def _request_issue(
    request: LessonRequest,
    issue_type: str,
    message: str,
    *,
    severity: IssueSeverity = "error",
    details: dict[str, object] | None = None,
) -> _Issue:
    payload: dict[str, object] = {
        "student_id": request.student_id,
        "subject_id": request.subject_id,
    }
    if details is not None:
        payload.update(details)
    return _Issue(
        severity,
        issue_type,
        "lesson_request",
        str(request.id),
        message,
        payload,
    )


def _issue_dto(row: ValidationIssue) -> ValidationIssueDto:
    try:
        details = json.loads(row.details_json)
    except json.JSONDecodeError:
        details = {"raw": row.details_json}
    if not isinstance(details, dict):
        details = {"value": details}
    return ValidationIssueDto(
        id=row.id,
        severity=_severity(row.severity),
        issue_type=row.issue_type,
        entity_type=row.entity_type,
        entity_id=row.entity_id_optional,
        message=row.message,
        details=details,
        resolved=row.resolved,
    )


def _severity(value: str) -> IssueSeverity:
    if value == "error":
        return "error"
    if value == "warning":
        return "warning"
    return "info"


def _entity_label(entity_type: str) -> str:
    return {"student": "生徒", "teacher": "講師"}.get(entity_type, entity_type)


__all__ = ["ProjectValidationService"]
