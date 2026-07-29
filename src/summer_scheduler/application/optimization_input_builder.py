"""保存済みプロジェクトを純粋な最適化入力DTOへ変換する境界。"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

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
)
from summer_scheduler.optimization.dto import (
    AvailabilityData,
    ExistingAssignmentData,
    GroupBlockData,
    LessonRequestData,
    OptimizationInput,
    OptimizationSettings,
    StudentData,
    SubjectData,
    TeacherData,
    TimeSlotData,
)


class OptimizationInputBuildError(LookupError):
    """指定プロジェクトから最適化入力を構築できない場合のエラー。"""


def build_optimization_input(
    *,
    session: Session,
    project_id: int,
    settings: OptimizationSettings,
) -> OptimizationInput:
    """DB行をsession非依存かつ不変なOptimizationInputへコピーする。

    表示名は説明表示用データとして保持するだけで、安定IDからの変数名生成等は
    solver側の責務とする。この関数はSessionやORMインスタンスを返り値に保持しない。
    """
    if session.get(CourseProject, project_id) is None:
        raise OptimizationInputBuildError(
            f"最適化対象プロジェクトが見つかりません: project_id={project_id}"
        )

    slots = list(
        session.scalars(
            select(TimeSlot)
            .where(TimeSlot.project_id == project_id)
            .order_by(TimeSlot.sort_order, TimeSlot.id)
        )
    )
    students = list(session.scalars(select(Student).order_by(Student.id)))
    teachers = list(session.scalars(select(Teacher).order_by(Teacher.id)))
    subjects = list(session.scalars(select(Subject).order_by(Subject.id)))
    requests = list(
        session.scalars(
            select(LessonRequest)
            .where(LessonRequest.project_id == project_id)
            .order_by(LessonRequest.id)
        )
    )
    student_availabilities = list(
        session.scalars(
            select(StudentAvailability)
            .where(StudentAvailability.project_id == project_id)
            .order_by(
                StudentAvailability.student_id,
                StudentAvailability.date,
                StudentAvailability.time_slot_id,
            )
        )
    )
    teacher_availabilities = list(
        session.scalars(
            select(TeacherAvailability)
            .where(TeacherAvailability.project_id == project_id)
            .order_by(
                TeacherAvailability.teacher_id,
                TeacherAvailability.date,
                TeacherAvailability.time_slot_id,
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
                GroupLesson.end_time,
                GroupLesson.id,
            )
        )
    )
    assignments = list(
        session.scalars(
            select(Assignment)
            .where(Assignment.project_id == project_id)
            .order_by(
                Assignment.lesson_request_id,
                Assignment.session_index,
                Assignment.id,
            )
        )
    )

    qualified_subjects_by_teacher: dict[int, set[int]] = defaultdict(set)
    for qualification in session.scalars(
        select(TeacherQualification)
        .where(TeacherQualification.can_teach.is_(True))
        .order_by(
            TeacherQualification.teacher_id,
            TeacherQualification.subject_id,
        )
    ):
        qualified_subjects_by_teacher[qualification.teacher_id].add(qualification.subject_id)

    members_by_group: dict[int, set[int]] = defaultdict(set)
    for membership in session.scalars(
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
        members_by_group[membership.group_lesson_id].add(membership.student_id)

    open_dates = tuple(
        session.scalars(
            select(OpenDate.date)
            .where(
                OpenDate.project_id == project_id,
                OpenDate.is_open.is_(True),
            )
            .order_by(OpenDate.date)
        )
    )
    availability_rows = [
        *(
            AvailabilityData(
                owner_type="student",
                owner_id=row.student_id,
                day=row.date,
                time_slot_id=row.time_slot_id,
                level=row.availability_level,
            )
            for row in student_availabilities
        ),
        *(
            AvailabilityData(
                owner_type="teacher",
                owner_id=row.teacher_id,
                day=row.date,
                time_slot_id=row.time_slot_id,
                level=row.availability_level,
            )
            for row in teacher_availabilities
        ),
    ]

    return OptimizationInput(
        project_id=project_id,
        open_dates=open_dates,
        time_slots=tuple(
            TimeSlotData(
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
            StudentData(
                id=row.id,
                display_name=row.name,
                default_max_consecutive_slots=row.default_max_consecutive_slots,
                allow_gap=row.allow_gap,
                active=row.active,
            )
            for row in students
        ),
        teachers=tuple(
            TeacherData(
                id=row.id,
                display_name=row.name,
                qualified_subject_ids=frozenset(qualified_subjects_by_teacher.get(row.id, set())),
                allow_gap=row.allow_gap,
                active=row.active,
            )
            for row in teachers
        ),
        subjects=tuple(
            SubjectData(
                id=row.id,
                code=row.code,
                display_name=row.display_name,
                active=row.active,
            )
            for row in subjects
        ),
        lesson_requests=tuple(_request_data(row) for row in requests),
        availabilities=tuple(availability_rows),
        group_blocks=tuple(
            GroupBlockData(
                id=row.id,
                day=row.date,
                start_time=row.start_time,
                end_time=row.end_time,
                teacher_id=row.teacher_id_optional,
                student_ids=frozenset(members_by_group.get(row.id, set())),
            )
            for row in groups
        ),
        existing_assignments=tuple(
            ExistingAssignmentData(
                id=row.id,
                lesson_request_id=row.lesson_request_id,
                session_index=row.session_index,
                day=row.date,
                time_slot_id=row.time_slot_id,
                teacher_id=row.teacher_id,
                is_locked=row.is_locked,
                is_manual=row.is_manual,
            )
            for row in assignments
        ),
        settings=settings,
    )


def _request_data(row: LessonRequest) -> LessonRequestData:
    preferred_teacher_ids = (
        row.preferred_teacher_1_id_optional,
        row.preferred_teacher_2_id_optional,
        row.preferred_teacher_3_id_optional,
    )
    return LessonRequestData(
        id=row.id,
        student_id=row.student_id,
        subject_id=row.subject_id,
        required_sessions=row.required_sessions,
        regular_teacher_id=row.regular_teacher_id_optional,
        regular_teacher_priority=row.regular_teacher_priority,
        preferred_teacher_ids=preferred_teacher_ids,
        one_to_one_required=row.one_to_one_required,
        max_consecutive_slots_override=(row.max_consecutive_slots_override_optional),
        allow_gap_override=row.allow_gap_override_optional,
    )


__all__ = [
    "OptimizationInputBuildError",
    "build_optimization_input",
]
