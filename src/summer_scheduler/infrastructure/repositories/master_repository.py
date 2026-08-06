"""Phase 2/3のマスター・入力データを永続化するRepository。

このRepositoryは必要に応じて ``flush()`` するが、``commit()`` や
``rollback()`` は行わない。複数操作やExcel取込みを一つのtransactionに
まとめる責務はApplication Service / Unit of Work側に残す。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import TypeVar

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from summer_scheduler.infrastructure.db.base import Base
from summer_scheduler.infrastructure.db.models import (
    AuditLog,
    Campus,
    CourseProject,
    GroupLesson,
    GroupLessonStudent,
    ImportBatch,
    ImportSourceSnapshot,
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

ModelT = TypeVar("ModelT", bound=Base)


class MasterRepository:
    """プロジェクト・マスター用の型付きSQLAlchemy Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """transaction管理用に、注入されたSessionを読み取り専用で公開する。"""
        return self._session

    def _create(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        self._session.flush()
        return entity

    def _update(self, entity: ModelT, changes: Mapping[str, object]) -> ModelT:
        invalid_fields = [name for name in changes if not hasattr(type(entity), name)]
        if invalid_fields:
            invalid = ", ".join(sorted(invalid_fields))
            raise AttributeError(f"{type(entity).__name__}に存在しない項目です: {invalid}")
        for name, value in changes.items():
            setattr(entity, name, value)
        self._session.flush()
        return entity

    def _delete(self, entity: Base | None) -> bool:
        if entity is None:
            return False
        self._session.delete(entity)
        self._session.flush()
        return True

    # Campus

    def create_campus(self, campus: Campus) -> Campus:
        return self._create(campus)

    def get_campus(self, campus_id: int) -> Campus | None:
        return self._session.get(Campus, campus_id)

    def list_campuses(self) -> list[Campus]:
        return list(self._session.scalars(select(Campus).order_by(Campus.id)))

    def update_campus(self, campus: Campus, **changes: object) -> Campus:
        return self._update(campus, changes)

    def delete_campus(self, campus_id: int) -> bool:
        return self._delete(self.get_campus(campus_id))

    # CourseProject

    def create_course_project(self, project: CourseProject) -> CourseProject:
        """単一ファイルへ2件目のプロジェクトが入ることを防ぐ。"""
        existing_id = self._session.scalar(select(CourseProject.id).limit(1))
        if existing_id is not None:
            raise ValueError("1つのプロジェクトファイルには1件だけ保存できます")
        return self._create(project)

    def get_course_project(self, project_id: int) -> CourseProject | None:
        return self._session.get(CourseProject, project_id)

    def get_only_course_project(self) -> CourseProject | None:
        return self._session.scalar(select(CourseProject).limit(1))

    def list_course_projects(self) -> list[CourseProject]:
        return list(self._session.scalars(select(CourseProject).order_by(CourseProject.id)))

    def update_course_project(
        self,
        project: CourseProject,
        **changes: object,
    ) -> CourseProject:
        return self._update(project, changes)

    def delete_course_project(self, project_id: int) -> bool:
        return self._delete(self.get_course_project(project_id))

    def create_project(self, project: CourseProject) -> CourseProject:
        return self.create_course_project(project)

    def get_project(self, project_id: int) -> CourseProject | None:
        return self.get_course_project(project_id)

    def list_projects(self) -> list[CourseProject]:
        return self.list_course_projects()

    def update_project(
        self,
        project: CourseProject,
        **changes: object,
    ) -> CourseProject:
        return self.update_course_project(project, **changes)

    def delete_project(self, project_id: int) -> bool:
        return self.delete_course_project(project_id)

    # TimeSlot

    def create_time_slot(self, time_slot: TimeSlot) -> TimeSlot:
        return self._create(time_slot)

    def get_time_slot(self, time_slot_id: int) -> TimeSlot | None:
        return self._session.get(TimeSlot, time_slot_id)

    def list_time_slots(
        self,
        *,
        project_id: int | None = None,
        enabled_only: bool = False,
    ) -> list[TimeSlot]:
        statement = select(TimeSlot)
        if project_id is not None:
            statement = statement.where(TimeSlot.project_id == project_id)
        if enabled_only:
            statement = statement.where(TimeSlot.enabled.is_(True))
        statement = statement.order_by(TimeSlot.sort_order, TimeSlot.id)
        return list(self._session.scalars(statement))

    def update_time_slot(
        self,
        time_slot: TimeSlot,
        **changes: object,
    ) -> TimeSlot:
        return self._update(time_slot, changes)

    def set_time_slot_enabled(
        self,
        time_slot_id: int,
        *,
        enabled: bool,
    ) -> TimeSlot | None:
        time_slot = self.get_time_slot(time_slot_id)
        if time_slot is None:
            return None
        return self.update_time_slot(time_slot, enabled=enabled)

    def delete_time_slot(self, time_slot_id: int) -> bool:
        return self._delete(self.get_time_slot(time_slot_id))

    # OpenDate

    def create_open_date(self, open_date: OpenDate) -> OpenDate:
        return self._create(open_date)

    def get_open_date(self, open_date_id: int) -> OpenDate | None:
        return self._session.get(OpenDate, open_date_id)

    def get_open_date_by_date(
        self,
        *,
        project_id: int,
        date_value: date,
    ) -> OpenDate | None:
        return self._session.scalar(
            select(OpenDate).where(
                OpenDate.project_id == project_id,
                OpenDate.date == date_value,
            )
        )

    def list_open_dates(
        self,
        *,
        project_id: int | None = None,
    ) -> list[OpenDate]:
        statement = select(OpenDate)
        if project_id is not None:
            statement = statement.where(OpenDate.project_id == project_id)
        statement = statement.order_by(OpenDate.date, OpenDate.id)
        return list(self._session.scalars(statement))

    def update_open_date(
        self,
        open_date: OpenDate,
        **changes: object,
    ) -> OpenDate:
        return self._update(open_date, changes)

    def delete_open_date(self, open_date_id: int) -> bool:
        return self._delete(self.get_open_date(open_date_id))

    # Student

    def create_student(self, student: Student) -> Student:
        return self._create(student)

    def get_student(self, student_id: int) -> Student | None:
        return self._session.get(Student, student_id)

    def get_student_by_external_id(self, external_id: str) -> Student | None:
        return self._session.scalar(select(Student).where(Student.external_id == external_id))

    def list_students(self, *, active_only: bool = False) -> list[Student]:
        statement = select(Student)
        if active_only:
            statement = statement.where(Student.active.is_(True))
        statement = statement.order_by(Student.active.desc(), Student.external_id, Student.id)
        return list(self._session.scalars(statement))

    def update_student(self, student: Student, **changes: object) -> Student:
        return self._update(student, changes)

    def set_student_active(
        self,
        student_id: int,
        *,
        active: bool,
    ) -> Student | None:
        student = self.get_student(student_id)
        if student is None:
            return None
        return self.update_student(student, active=active)

    def deactivate_student(self, student_id: int) -> Student | None:
        return self.set_student_active(student_id, active=False)

    def activate_student(self, student_id: int) -> Student | None:
        return self.set_student_active(student_id, active=True)

    def delete_student(self, student_id: int) -> bool:
        return self._delete(self.get_student(student_id))

    # Teacher

    def create_teacher(self, teacher: Teacher) -> Teacher:
        return self._create(teacher)

    def get_teacher(self, teacher_id: int) -> Teacher | None:
        return self._session.get(Teacher, teacher_id)

    def get_teacher_by_external_id(self, external_id: str) -> Teacher | None:
        return self._session.scalar(select(Teacher).where(Teacher.external_id == external_id))

    def list_teachers(self, *, active_only: bool = False) -> list[Teacher]:
        statement = select(Teacher)
        if active_only:
            statement = statement.where(Teacher.active.is_(True))
        statement = statement.order_by(Teacher.active.desc(), Teacher.external_id, Teacher.id)
        return list(self._session.scalars(statement))

    def update_teacher(self, teacher: Teacher, **changes: object) -> Teacher:
        return self._update(teacher, changes)

    def set_teacher_active(
        self,
        teacher_id: int,
        *,
        active: bool,
    ) -> Teacher | None:
        teacher = self.get_teacher(teacher_id)
        if teacher is None:
            return None
        return self.update_teacher(teacher, active=active)

    def deactivate_teacher(self, teacher_id: int) -> Teacher | None:
        return self.set_teacher_active(teacher_id, active=False)

    def activate_teacher(self, teacher_id: int) -> Teacher | None:
        return self.set_teacher_active(teacher_id, active=True)

    def delete_teacher(self, teacher_id: int) -> bool:
        return self._delete(self.get_teacher(teacher_id))

    # Subject

    def create_subject(self, subject: Subject) -> Subject:
        return self._create(subject)

    def get_subject(self, subject_id: int) -> Subject | None:
        return self._session.get(Subject, subject_id)

    def get_subject_by_code(self, code: str) -> Subject | None:
        return self._session.scalar(select(Subject).where(Subject.code == code))

    def list_subjects(self, *, active_only: bool = False) -> list[Subject]:
        statement = select(Subject)
        if active_only:
            statement = statement.where(Subject.active.is_(True))
        statement = statement.order_by(
            Subject.school_level,
            Subject.sort_order,
            Subject.code,
        )
        return list(self._session.scalars(statement))

    def update_subject(self, subject: Subject, **changes: object) -> Subject:
        return self._update(subject, changes)

    def set_subject_active(
        self,
        subject_id: int,
        *,
        active: bool,
    ) -> Subject | None:
        subject = self.get_subject(subject_id)
        if subject is None:
            return None
        return self.update_subject(subject, active=active)

    def deactivate_subject(self, subject_id: int) -> Subject | None:
        return self.set_subject_active(subject_id, active=False)

    def activate_subject(self, subject_id: int) -> Subject | None:
        return self.set_subject_active(subject_id, active=True)

    def delete_subject(self, subject_id: int) -> bool:
        return self._delete(self.get_subject(subject_id))

    # TeacherQualification

    def create_teacher_qualification(
        self,
        qualification: TeacherQualification,
    ) -> TeacherQualification:
        return self._create(qualification)

    def get_teacher_qualification(
        self,
        teacher_id: int,
        subject_id: int,
    ) -> TeacherQualification | None:
        return self._session.get(
            TeacherQualification,
            (teacher_id, subject_id),
        )

    def list_teacher_qualifications(
        self,
        *,
        teacher_id: int | None = None,
        subject_id: int | None = None,
    ) -> list[TeacherQualification]:
        statement = select(TeacherQualification)
        if teacher_id is not None:
            statement = statement.where(TeacherQualification.teacher_id == teacher_id)
        if subject_id is not None:
            statement = statement.where(TeacherQualification.subject_id == subject_id)
        statement = statement.order_by(
            TeacherQualification.teacher_id,
            TeacherQualification.subject_id,
        )
        return list(self._session.scalars(statement))

    def update_teacher_qualification(
        self,
        qualification: TeacherQualification,
        **changes: object,
    ) -> TeacherQualification:
        return self._update(qualification, changes)

    def set_teacher_qualification(
        self,
        *,
        teacher_id: int,
        subject_id: int,
        can_teach: bool,
        note: str | None = None,
    ) -> TeacherQualification:
        qualification = self.get_teacher_qualification(teacher_id, subject_id)
        if qualification is None:
            return self.create_teacher_qualification(
                TeacherQualification(
                    teacher_id=teacher_id,
                    subject_id=subject_id,
                    can_teach=can_teach,
                    note=note,
                )
            )
        return self.update_teacher_qualification(
            qualification,
            can_teach=can_teach,
            note=note,
        )

    def replace_teacher_qualifications(
        self,
        *,
        teacher_id: int,
        qualifications: Mapping[int, bool],
    ) -> list[TeacherQualification]:
        """指定講師の資格行を、与えられた科目集合で置き換える。"""
        self._session.execute(
            delete(TeacherQualification).where(TeacherQualification.teacher_id == teacher_id)
        )
        rows = [
            TeacherQualification(
                teacher_id=teacher_id,
                subject_id=subject_id,
                can_teach=can_teach,
            )
            for subject_id, can_teach in sorted(qualifications.items())
        ]
        self._session.add_all(rows)
        self._session.flush()
        return rows

    def copy_teacher_qualifications(
        self,
        *,
        source_teacher_id: int,
        target_teacher_id: int,
    ) -> list[TeacherQualification]:
        source_rows = self.list_teacher_qualifications(teacher_id=source_teacher_id)
        self._session.execute(
            delete(TeacherQualification).where(TeacherQualification.teacher_id == target_teacher_id)
        )
        copied = [
            TeacherQualification(
                teacher_id=target_teacher_id,
                subject_id=row.subject_id,
                can_teach=row.can_teach,
                note=row.note,
            )
            for row in source_rows
        ]
        self._session.add_all(copied)
        self._session.flush()
        return copied

    def can_teacher_teach(self, teacher_id: int, subject_id: int) -> bool:
        result = self._session.scalar(
            select(TeacherQualification.can_teach).where(
                TeacherQualification.teacher_id == teacher_id,
                TeacherQualification.subject_id == subject_id,
            )
        )
        return result is True

    def delete_teacher_qualification(
        self,
        teacher_id: int,
        subject_id: int,
    ) -> bool:
        return self._delete(self.get_teacher_qualification(teacher_id, subject_id))

    # LessonRequest

    def create_lesson_request(
        self,
        lesson_request: LessonRequest,
    ) -> LessonRequest:
        return self._create(lesson_request)

    def get_lesson_request(
        self,
        lesson_request_id: int,
    ) -> LessonRequest | None:
        return self._session.get(LessonRequest, lesson_request_id)

    def get_lesson_request_by_student_subject(
        self,
        *,
        project_id: int,
        student_id: int,
        subject_id: int,
    ) -> LessonRequest | None:
        return self._session.scalar(
            select(LessonRequest).where(
                LessonRequest.project_id == project_id,
                LessonRequest.student_id == student_id,
                LessonRequest.subject_id == subject_id,
            )
        )

    def list_lesson_requests(
        self,
        *,
        project_id: int | None = None,
        student_id: int | None = None,
        subject_id: int | None = None,
    ) -> list[LessonRequest]:
        statement = select(LessonRequest)
        if project_id is not None:
            statement = statement.where(LessonRequest.project_id == project_id)
        if student_id is not None:
            statement = statement.where(LessonRequest.student_id == student_id)
        if subject_id is not None:
            statement = statement.where(LessonRequest.subject_id == subject_id)
        statement = statement.order_by(
            LessonRequest.student_id,
            LessonRequest.subject_id,
            LessonRequest.id,
        )
        return list(self._session.scalars(statement))

    def update_lesson_request(
        self,
        lesson_request: LessonRequest,
        **changes: object,
    ) -> LessonRequest:
        return self._update(lesson_request, changes)

    def delete_lesson_request(self, lesson_request_id: int) -> bool:
        return self._delete(self.get_lesson_request(lesson_request_id))

    # StudentAvailability

    def create_student_availability(
        self,
        availability: StudentAvailability,
    ) -> StudentAvailability:
        return self._create(availability)

    def get_student_availability(
        self,
        *,
        project_id: int,
        student_id: int,
        date_value: date,
        time_slot_id: int,
    ) -> StudentAvailability | None:
        return self._session.get(
            StudentAvailability,
            (project_id, student_id, date_value, time_slot_id),
        )

    def list_student_availabilities(
        self,
        *,
        project_id: int,
        student_id: int | None = None,
        date_value: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        time_slot_id: int | None = None,
    ) -> list[StudentAvailability]:
        statement = select(StudentAvailability).where(StudentAvailability.project_id == project_id)
        if student_id is not None:
            statement = statement.where(StudentAvailability.student_id == student_id)
        if date_value is not None:
            statement = statement.where(StudentAvailability.date == date_value)
        if date_from is not None:
            statement = statement.where(StudentAvailability.date >= date_from)
        if date_to is not None:
            statement = statement.where(StudentAvailability.date <= date_to)
        if time_slot_id is not None:
            statement = statement.where(StudentAvailability.time_slot_id == time_slot_id)
        statement = statement.order_by(
            StudentAvailability.student_id,
            StudentAvailability.date,
            StudentAvailability.time_slot_id,
        )
        return list(self._session.scalars(statement))

    def upsert_student_availability(
        self,
        *,
        project_id: int,
        student_id: int,
        date_value: date,
        time_slot_id: int,
        availability_level: int,
    ) -> StudentAvailability:
        availability = self.get_student_availability(
            project_id=project_id,
            student_id=student_id,
            date_value=date_value,
            time_slot_id=time_slot_id,
        )
        if availability is None:
            return self.create_student_availability(
                StudentAvailability(
                    project_id=project_id,
                    student_id=student_id,
                    date=date_value,
                    time_slot_id=time_slot_id,
                    availability_level=availability_level,
                )
            )
        return self._update(
            availability,
            {"availability_level": availability_level},
        )

    def delete_student_availability(
        self,
        *,
        project_id: int,
        student_id: int,
        date_value: date,
        time_slot_id: int,
    ) -> bool:
        return self._delete(
            self.get_student_availability(
                project_id=project_id,
                student_id=student_id,
                date_value=date_value,
                time_slot_id=time_slot_id,
            )
        )

    def delete_student_availabilities(
        self,
        *,
        project_id: int,
        student_id: int | None = None,
        date_value: date | None = None,
    ) -> int:
        rows = self.list_student_availabilities(
            project_id=project_id,
            student_id=student_id,
            date_value=date_value,
        )
        for row in rows:
            self._session.delete(row)
        self._session.flush()
        return len(rows)

    # TeacherAvailability

    def create_teacher_availability(
        self,
        availability: TeacherAvailability,
    ) -> TeacherAvailability:
        return self._create(availability)

    def get_teacher_availability(
        self,
        *,
        project_id: int,
        teacher_id: int,
        date_value: date,
        time_slot_id: int,
    ) -> TeacherAvailability | None:
        return self._session.get(
            TeacherAvailability,
            (project_id, teacher_id, date_value, time_slot_id),
        )

    def list_teacher_availabilities(
        self,
        *,
        project_id: int,
        teacher_id: int | None = None,
        date_value: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        time_slot_id: int | None = None,
    ) -> list[TeacherAvailability]:
        statement = select(TeacherAvailability).where(TeacherAvailability.project_id == project_id)
        if teacher_id is not None:
            statement = statement.where(TeacherAvailability.teacher_id == teacher_id)
        if date_value is not None:
            statement = statement.where(TeacherAvailability.date == date_value)
        if date_from is not None:
            statement = statement.where(TeacherAvailability.date >= date_from)
        if date_to is not None:
            statement = statement.where(TeacherAvailability.date <= date_to)
        if time_slot_id is not None:
            statement = statement.where(TeacherAvailability.time_slot_id == time_slot_id)
        statement = statement.order_by(
            TeacherAvailability.teacher_id,
            TeacherAvailability.date,
            TeacherAvailability.time_slot_id,
        )
        return list(self._session.scalars(statement))

    def upsert_teacher_availability(
        self,
        *,
        project_id: int,
        teacher_id: int,
        date_value: date,
        time_slot_id: int,
        availability_level: int,
    ) -> TeacherAvailability:
        availability = self.get_teacher_availability(
            project_id=project_id,
            teacher_id=teacher_id,
            date_value=date_value,
            time_slot_id=time_slot_id,
        )
        if availability is None:
            return self.create_teacher_availability(
                TeacherAvailability(
                    project_id=project_id,
                    teacher_id=teacher_id,
                    date=date_value,
                    time_slot_id=time_slot_id,
                    availability_level=availability_level,
                )
            )
        return self._update(
            availability,
            {"availability_level": availability_level},
        )

    def delete_teacher_availability(
        self,
        *,
        project_id: int,
        teacher_id: int,
        date_value: date,
        time_slot_id: int,
    ) -> bool:
        return self._delete(
            self.get_teacher_availability(
                project_id=project_id,
                teacher_id=teacher_id,
                date_value=date_value,
                time_slot_id=time_slot_id,
            )
        )

    def delete_teacher_availabilities(
        self,
        *,
        project_id: int,
        teacher_id: int | None = None,
        date_value: date | None = None,
    ) -> int:
        rows = self.list_teacher_availabilities(
            project_id=project_id,
            teacher_id=teacher_id,
            date_value=date_value,
        )
        for row in rows:
            self._session.delete(row)
        self._session.flush()
        return len(rows)

    # GroupLesson

    def create_group_lesson(self, group_lesson: GroupLesson) -> GroupLesson:
        return self._create(group_lesson)

    def get_group_lesson(self, group_lesson_id: int) -> GroupLesson | None:
        return self._session.get(GroupLesson, group_lesson_id)

    def get_group_lesson_by_code(
        self,
        *,
        project_id: int,
        group_code: str,
    ) -> GroupLesson | None:
        return self._session.scalar(
            select(GroupLesson).where(
                GroupLesson.project_id == project_id,
                GroupLesson.group_code == group_code,
            )
        )

    def list_group_lessons(
        self,
        *,
        project_id: int,
        date_value: date | None = None,
        teacher_id: int | None = None,
        subject_id: int | None = None,
    ) -> list[GroupLesson]:
        statement = select(GroupLesson).where(GroupLesson.project_id == project_id)
        if date_value is not None:
            statement = statement.where(GroupLesson.date == date_value)
        if teacher_id is not None:
            statement = statement.where(GroupLesson.teacher_id_optional == teacher_id)
        if subject_id is not None:
            statement = statement.where(GroupLesson.subject_id == subject_id)
        statement = statement.order_by(
            GroupLesson.date,
            GroupLesson.start_time,
            GroupLesson.group_code,
            GroupLesson.id,
        )
        return list(self._session.scalars(statement))

    def update_group_lesson(
        self,
        group_lesson: GroupLesson,
        **changes: object,
    ) -> GroupLesson:
        return self._update(group_lesson, changes)

    def delete_group_lesson(self, group_lesson_id: int) -> bool:
        return self._delete(self.get_group_lesson(group_lesson_id))

    # GroupLessonStudent

    def create_group_lesson_student(
        self,
        membership: GroupLessonStudent,
    ) -> GroupLessonStudent:
        return self._create(membership)

    def get_group_lesson_student(
        self,
        *,
        group_lesson_id: int,
        student_id: int,
    ) -> GroupLessonStudent | None:
        return self._session.get(
            GroupLessonStudent,
            (group_lesson_id, student_id),
        )

    def list_group_lesson_students(
        self,
        *,
        group_lesson_id: int | None = None,
        student_id: int | None = None,
    ) -> list[GroupLessonStudent]:
        statement = select(GroupLessonStudent)
        if group_lesson_id is not None:
            statement = statement.where(GroupLessonStudent.group_lesson_id == group_lesson_id)
        if student_id is not None:
            statement = statement.where(GroupLessonStudent.student_id == student_id)
        statement = statement.order_by(
            GroupLessonStudent.group_lesson_id,
            GroupLessonStudent.student_id,
        )
        return list(self._session.scalars(statement))

    def replace_group_lesson_students(
        self,
        *,
        group_lesson_id: int,
        student_ids: Iterable[int],
    ) -> list[GroupLessonStudent]:
        target_ids = set(student_ids)
        existing = {
            row.student_id: row
            for row in self.list_group_lesson_students(
                group_lesson_id=group_lesson_id,
            )
        }
        for student_id, row in existing.items():
            if student_id not in target_ids:
                self._session.delete(row)
        for student_id in sorted(target_ids - existing.keys()):
            self._session.add(
                GroupLessonStudent(
                    group_lesson_id=group_lesson_id,
                    student_id=student_id,
                )
            )
        self._session.flush()
        return self.list_group_lesson_students(group_lesson_id=group_lesson_id)

    def delete_group_lesson_student(
        self,
        *,
        group_lesson_id: int,
        student_id: int,
    ) -> bool:
        return self._delete(
            self.get_group_lesson_student(
                group_lesson_id=group_lesson_id,
                student_id=student_id,
            )
        )

    # ImportBatch

    def create_import_batch(self, import_batch: ImportBatch) -> ImportBatch:
        return self._create(import_batch)

    def get_import_batch(self, import_batch_id: int) -> ImportBatch | None:
        return self._session.get(ImportBatch, import_batch_id)

    def list_import_batches(
        self,
        *,
        project_id: int,
        import_type: str | None = None,
    ) -> list[ImportBatch]:
        statement = select(ImportBatch).where(ImportBatch.project_id == project_id)
        if import_type is not None:
            statement = statement.where(ImportBatch.import_type == import_type)
        statement = statement.order_by(
            ImportBatch.imported_at.desc(),
            ImportBatch.id.desc(),
        )
        return list(self._session.scalars(statement))

    def get_latest_import_batch(
        self,
        *,
        project_id: int,
        import_type: str,
    ) -> ImportBatch | None:
        return self._session.scalar(
            select(ImportBatch)
            .where(
                ImportBatch.project_id == project_id,
                ImportBatch.import_type == import_type,
            )
            .order_by(
                ImportBatch.imported_at.desc(),
                ImportBatch.id.desc(),
            )
            .limit(1)
        )

    def get_import_source_snapshot(
        self,
        *,
        project_id: int,
        import_type: str,
    ) -> ImportSourceSnapshot | None:
        return self._session.scalar(
            select(ImportSourceSnapshot).where(
                ImportSourceSnapshot.project_id == project_id,
                ImportSourceSnapshot.import_type == import_type,
            )
        )

    def replace_import_source_snapshot(
        self,
        snapshot: ImportSourceSnapshot,
    ) -> ImportSourceSnapshot:
        existing = self.get_import_source_snapshot(
            project_id=snapshot.project_id,
            import_type=snapshot.import_type,
        )
        if existing is None:
            return self._create(snapshot)
        return self._update(
            existing,
            {
                "source_file_name": snapshot.source_file_name,
                "content": snapshot.content,
                "sha256": snapshot.sha256,
                "size_bytes": snapshot.size_bytes,
                "imported_at": snapshot.imported_at,
            },
        )

    # ValidationIssue

    def create_validation_issue(
        self,
        issue: ValidationIssue,
    ) -> ValidationIssue:
        return self._create(issue)

    def get_validation_issue(self, issue_id: int) -> ValidationIssue | None:
        return self._session.get(ValidationIssue, issue_id)

    def list_validation_issues(
        self,
        *,
        project_id: int,
        severity: str | None = None,
        resolved: bool | None = None,
        entity_type: str | None = None,
    ) -> list[ValidationIssue]:
        statement = select(ValidationIssue).where(ValidationIssue.project_id == project_id)
        if severity is not None:
            statement = statement.where(ValidationIssue.severity == severity)
        if resolved is not None:
            statement = statement.where(ValidationIssue.resolved.is_(resolved))
        if entity_type is not None:
            statement = statement.where(ValidationIssue.entity_type == entity_type)
        statement = statement.order_by(
            ValidationIssue.resolved,
            ValidationIssue.id,
        )
        return list(self._session.scalars(statement))

    def update_validation_issue(
        self,
        issue: ValidationIssue,
        **changes: object,
    ) -> ValidationIssue:
        return self._update(issue, changes)

    def resolve_validation_issues(self, *, project_id: int) -> int:
        unresolved = self.list_validation_issues(
            project_id=project_id,
            resolved=False,
        )
        for issue in unresolved:
            issue.resolved = True
        self._session.flush()
        return len(unresolved)

    def replace_validation_issues(
        self,
        *,
        project_id: int,
        issues: Iterable[ValidationIssue],
    ) -> list[ValidationIssue]:
        new_issues = list(issues)
        invalid = [issue for issue in new_issues if issue.project_id != project_id]
        if invalid:
            raise ValueError("別プロジェクトの検証結果は保存できません")
        self.resolve_validation_issues(project_id=project_id)
        for issue in new_issues:
            issue.resolved = False
        self._session.add_all(new_issues)
        self._session.flush()
        return new_issues

    def delete_validation_issue(self, issue_id: int) -> bool:
        return self._delete(self.get_validation_issue(issue_id))

    # AuditLog

    def create_audit_log(self, audit_log: AuditLog) -> AuditLog:
        return self._create(audit_log)

    def get_audit_log(self, audit_log_id: int) -> AuditLog | None:
        return self._session.get(AuditLog, audit_log_id)

    def list_audit_logs(
        self,
        *,
        project_id: int,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        timestamp_from: datetime | None = None,
        timestamp_to: datetime | None = None,
    ) -> list[AuditLog]:
        statement = select(AuditLog).where(AuditLog.project_id == project_id)
        if entity_type is not None:
            statement = statement.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(AuditLog.entity_id == entity_id)
        if action is not None:
            statement = statement.where(AuditLog.action == action)
        if timestamp_from is not None:
            statement = statement.where(AuditLog.timestamp >= timestamp_from)
        if timestamp_to is not None:
            statement = statement.where(AuditLog.timestamp <= timestamp_to)
        statement = statement.order_by(
            AuditLog.timestamp.desc(),
            AuditLog.id.desc(),
        )
        return list(self._session.scalars(statement))


__all__ = ["MasterRepository"]
