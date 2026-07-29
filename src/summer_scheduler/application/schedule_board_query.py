"""Phase 5時間割ボードの読み取りモデル構築。"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from summer_scheduler.application.phase5_dto import (
    AuditLogDto,
    GroupBlockDto,
    ScheduleBoardDto,
    ScheduleCardDto,
    ScheduleCellDto,
    ScheduleDateDto,
    ScheduleDiffDto,
    ScheduleSlotDto,
    ScheduleTeacherDto,
    SessionKeyDto,
    UnassignedSessionDto,
)
from summer_scheduler.infrastructure.db.models import (
    Assignment,
    AuditLog,
    GroupLesson,
    LessonRequest,
    OpenDate,
    Student,
    Subject,
    Teacher,
    TimeSlot,
)
from summer_scheduler.optimization.dto import CandidateData, CandidateGenerationResult


def build_schedule_board(
    *,
    session: Session,
    project_id: int,
    generation: CandidateGenerationResult,
    fingerprint: str,
    audit_logs: Sequence[AuditLog],
    diff: tuple[ScheduleDiffDto, ...],
    can_undo: bool,
    can_redo: bool,
) -> ScheduleBoardDto:
    """ORMを保持しない、一括読取り用の不変DTOを返す。"""
    open_dates = list(
        session.scalars(
            select(OpenDate)
            .where(OpenDate.project_id == project_id)
            .order_by(OpenDate.date, OpenDate.id)
        )
    )
    slots = list(
        session.scalars(
            select(TimeSlot)
            .where(TimeSlot.project_id == project_id)
            .order_by(TimeSlot.sort_order, TimeSlot.id)
        )
    )
    teachers = list(session.scalars(select(Teacher).order_by(Teacher.external_id, Teacher.id)))
    teachers_by_id = {row.id: row for row in teachers}
    students = {row.id: row for row in session.scalars(select(Student).order_by(Student.id))}
    subjects = {row.id: row for row in session.scalars(select(Subject).order_by(Subject.id))}
    requests = {
        row.id: row
        for row in session.scalars(
            select(LessonRequest)
            .where(LessonRequest.project_id == project_id)
            .order_by(LessonRequest.id)
        )
    }
    assignments = list(
        session.scalars(
            select(Assignment)
            .where(Assignment.project_id == project_id)
            .order_by(
                Assignment.date,
                Assignment.time_slot_id,
                Assignment.teacher_id,
                Assignment.lesson_request_id,
                Assignment.session_index,
            )
        )
    )
    groups = list(
        session.scalars(
            select(GroupLesson)
            .where(GroupLesson.project_id == project_id)
            .order_by(
                GroupLesson.date,
                GroupLesson.start_time,
                GroupLesson.id,
            )
        )
    )

    audit_by_entity: dict[str, list[AuditLog]] = defaultdict(list)
    for audit in audit_logs:
        audit_by_entity[audit.entity_id].append(audit)
    candidate_by_placement = {
        (
            row.lesson_request_id,
            row.session_index,
            row.day,
            row.time_slot_id,
            row.teacher_id,
        ): row
        for row in generation.candidates
    }
    cards = tuple(
        _card(
            row,
            requests=requests,
            students=students,
            subjects=subjects,
            teachers=teachers_by_id,
            candidate_by_placement=candidate_by_placement,
            history=audit_by_entity.get(
                f"{row.lesson_request_id}:{row.session_index}",
                [],
            ),
        )
        for row in assignments
    )
    group_blocks = tuple(
        GroupBlockDto(
            id=row.id,
            group_code=row.group_code,
            course_name=row.course_name or "",
            grade=row.grade,
            subject_name=subjects[row.subject_id].display_name,
            day=row.date,
            start_time=row.start_time,
            end_time=row.end_time,
            teacher_id=row.teacher_id_optional,
        )
        for row in groups
    )
    cells = _cells(assignments, groups, slots)
    unassigned = _unassigned(
        generation=generation,
        assignments=assignments,
        requests=requests,
        students=students,
        subjects=subjects,
    )
    return ScheduleBoardDto(
        project_id=project_id,
        dates=tuple(
            ScheduleDateDto(
                day=row.date,
                is_open=row.is_open,
                note=row.note or "",
            )
            for row in open_dates
        ),
        slots=tuple(
            ScheduleSlotDto(
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
        teachers=tuple(
            ScheduleTeacherDto(
                id=row.id,
                name=row.name,
                active=row.active,
            )
            for row in teachers
        ),
        cells=cells,
        cards=cards,
        group_blocks=group_blocks,
        unassigned=unassigned,
        audit_logs=tuple(audit_log_to_dto(row) for row in audit_logs),
        diff=diff,
        lock_count=sum(row.is_locked for row in assignments),
        unassigned_count=len(unassigned),
        fingerprint=fingerprint,
        can_undo=can_undo,
        can_redo=can_redo,
    )


def audit_log_to_dto(row: AuditLog) -> AuditLogDto:
    return AuditLogDto(
        id=row.id,
        timestamp=row.timestamp,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        before_json=row.before_json,
        after_json=row.after_json,
        reason=row.reason or "",
        source=row.source,
        operation_id=row.operation_id_optional,
    )


def _card(
    row: Assignment,
    *,
    requests: dict[int, LessonRequest],
    students: dict[int, Student],
    subjects: dict[int, Subject],
    teachers: dict[int, Teacher],
    candidate_by_placement: dict[tuple[int, int, date, int, int], CandidateData],
    history: Sequence[AuditLog],
) -> ScheduleCardDto:
    request = requests[row.lesson_request_id]
    student = students[request.student_id]
    subject = subjects[request.subject_id]
    preferred_ids = (
        request.preferred_teacher_1_id_optional,
        request.preferred_teacher_2_id_optional,
        request.preferred_teacher_3_id_optional,
    )
    candidate = candidate_by_placement.get(
        (
            row.lesson_request_id,
            row.session_index,
            row.date,
            row.time_slot_id,
            row.teacher_id,
        )
    )
    availability_text = "候補外（要確認）"
    warnings: tuple[str, ...] = ("現在の配置が候補集合にありません",)
    if candidate is not None:
        student_level = candidate.student_availability_level
        teacher_level = candidate.teacher_availability_level
        availability_text = (
            f"生徒:{_availability_label(student_level)} / 講師:{_availability_label(teacher_level)}"
        )
        warnings = ()
    max_consecutive = (
        request.max_consecutive_slots_override_optional or student.default_max_consecutive_slots
    )
    student_allow_gap = (
        request.allow_gap_override_optional
        if request.allow_gap_override_optional is not None
        else student.allow_gap
    )
    teacher = teachers[row.teacher_id]
    return ScheduleCardDto(
        assignment_id=row.id,
        lesson_request_id=row.lesson_request_id,
        session_index=row.session_index,
        student_id=student.id,
        student_name=student.name,
        grade=student.grade,
        subject_id=subject.id,
        subject_code=subject.code,
        subject_name=subject.display_name,
        day=row.date,
        time_slot_id=row.time_slot_id,
        teacher_id=row.teacher_id,
        one_to_one_required=request.one_to_one_required,
        priority_five=request.regular_teacher_priority == 5,
        is_locked=row.is_locked,
        is_manual=row.is_manual,
        note=row.note or "",
        regular_teacher_name=(
            teachers[request.regular_teacher_id_optional].name
            if request.regular_teacher_id_optional in teachers
            else ""
        ),
        preferred_teacher_names=tuple(
            teachers[teacher_id].name for teacher_id in preferred_ids if teacher_id in teachers
        ),
        availability_text=availability_text,
        consecutive_text=f"最大{max_consecutive}コマ",
        gap_text=(
            f"生徒:{'許可' if student_allow_gap else '禁止'} / "
            f"講師:{'許可' if teacher.allow_gap else '禁止'}"
        ),
        warning_messages=warnings,
        change_history=tuple(
            f"{audit.timestamp.isoformat()} {audit.action} {audit.reason or ''}".strip()
            for audit in history[:10]
        ),
        warning_count=len(warnings),
    )


def _cells(
    assignments: Sequence[Assignment],
    groups: Sequence[GroupLesson],
    slots: Sequence[TimeSlot],
) -> tuple[ScheduleCellDto, ...]:
    assignment_keys: dict[tuple[date, int, int], list[SessionKeyDto]] = defaultdict(list)
    group_ids: dict[tuple[date, int, int], list[int]] = defaultdict(list)
    for row in assignments:
        assignment_keys[(row.date, row.time_slot_id, row.teacher_id)].append(
            SessionKeyDto(
                lesson_request_id=row.lesson_request_id,
                session_index=row.session_index,
            )
        )
    for group in groups:
        if group.teacher_id_optional is None:
            continue
        for slot in slots:
            if slot.start_time < group.end_time and group.start_time < slot.end_time:
                group_ids[(group.date, slot.id, group.teacher_id_optional)].append(group.id)
    keys = sorted(
        assignment_keys.keys() | group_ids.keys(),
        key=lambda value: (value[0], value[1], value[2]),
    )
    return tuple(
        ScheduleCellDto(
            day=key[0],
            time_slot_id=key[1],
            teacher_id=key[2],
            assignment_keys=tuple(assignment_keys[key]),
            group_lesson_ids=tuple(group_ids[key]),
        )
        for key in keys
    )


def _unassigned(
    *,
    generation: CandidateGenerationResult,
    assignments: Sequence[Assignment],
    requests: dict[int, LessonRequest],
    students: dict[int, Student],
    subjects: dict[int, Subject],
) -> tuple[UnassignedSessionDto, ...]:
    assigned_keys = {(row.lesson_request_id, row.session_index) for row in assignments}
    missing_sessions = tuple(row for row in generation.sessions if row.key not in assigned_keys)
    remaining_by_request = Counter(row.lesson_request_id for row in missing_sessions)
    result: list[UnassignedSessionDto] = []
    for session_row in missing_sessions:
        request = requests[session_row.lesson_request_id]
        student = students[request.student_id]
        subject = subjects[request.subject_id]
        diagnostic = generation.diagnostics_for(
            session_row.lesson_request_id,
            session_row.session_index,
        )
        candidate_count = (
            diagnostic.candidate_count
            if diagnostic is not None
            else len(
                generation.candidates_for(
                    session_row.lesson_request_id,
                    session_row.session_index,
                )
            )
        )
        primary_reason = (
            diagnostic.reasons[0].message
            if diagnostic is not None and diagnostic.reasons
            else "現在の時間割では未配置です"
        )
        result.append(
            UnassignedSessionDto(
                lesson_request_id=request.id,
                session_index=session_row.session_index,
                student_id=student.id,
                student_name=student.name,
                grade=student.grade,
                subject_id=subject.id,
                subject_code=subject.code,
                subject_name=subject.display_name,
                remaining_count=remaining_by_request[request.id],
                primary_reason=primary_reason,
                candidate_count=candidate_count,
                priority_five=request.regular_teacher_priority == 5,
                one_to_one_required=request.one_to_one_required,
            )
        )
    return tuple(result)


def _availability_label(level: int) -> str:
    return {0: "不可", 1: "可能", 2: "希望"}.get(level, "不明")


__all__ = ["audit_log_to_dto", "build_schedule_board"]
