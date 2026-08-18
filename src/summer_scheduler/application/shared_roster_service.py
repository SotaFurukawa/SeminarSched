"""講習プロジェクトから独立した共通名簿を管理するApplication Service。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select

from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.infrastructure.db.models import (
    LessonRequest,
    RegularLessonProfile,
    Student,
    Subject,
    Teacher,
    TeacherQualification,
)
from summer_scheduler.infrastructure.excel.shared_roster import (
    SHARED_ROSTER_FILENAME,
    SharedQualification,
    SharedRegularLesson,
    SharedRosterData,
    SharedStudent,
    SharedSubject,
    SharedTeacher,
    empty_shared_roster,
    read_shared_roster,
    write_shared_roster,
)


@dataclass(frozen=True, slots=True)
class SharedRosterSyncResult:
    students: int
    teachers: int
    qualifications: int
    regular_lessons: int


class SharedRosterService:
    """共通Excelを正本とし、各 `.jukuschedule` へsnapshotを反映する。"""

    def __init__(self, projects: ProjectService) -> None:
        self._projects = projects

    @property
    def path(self) -> Path:
        return self._projects.workspace_directory / SHARED_ROSTER_FILENAME

    def ensure_workbook(self) -> Path:
        """初回だけ現プロジェクトまたは既定科目から共通名簿を作成する。"""
        if self.path.is_file():
            return self.path
        data = self._from_current_project() if self._projects.current is not None else None
        write_shared_roster(self.path, data or empty_shared_roster())
        return self.path

    def sync_to_current_project(self) -> SharedRosterSyncResult:
        """共通名簿を検証し、現在のプロジェクトへ1 transactionで反映する。"""
        source = self.ensure_workbook()
        data = read_shared_roster(source)
        project = self._projects.require_project()
        database = self._projects.require_database()
        with database.session_factory.begin() as session:
            existing_students = {row.external_id: row for row in session.scalars(select(Student))}
            student_ids: dict[str, int] = {}
            active_student_ids = {row.external_id for row in data.students}
            for student_row in data.students:
                student_entity = existing_students.get(student_row.external_id)
                if student_entity is None:
                    student_entity = Student(
                        external_id=student_row.external_id,
                        name=student_row.name,
                        grade=student_row.grade,
                    )
                    session.add(student_entity)
                student_entity.name = student_row.name
                student_entity.grade = student_row.grade
                student_entity.default_max_consecutive_slots = student_row.max_consecutive_slots
                student_entity.allow_gap = student_row.allow_gap
                student_entity.active = student_row.active
                student_entity.note = student_row.note or None
                session.flush()
                student_ids[student_row.external_id] = student_entity.id
            for external_id, existing_student in existing_students.items():
                if external_id not in active_student_ids:
                    existing_student.active = False

            existing_teachers = {row.external_id: row for row in session.scalars(select(Teacher))}
            teacher_ids: dict[str, int] = {}
            active_teacher_ids = {row.external_id for row in data.teachers}
            for teacher_row in data.teachers:
                teacher_entity = existing_teachers.get(teacher_row.external_id)
                if teacher_entity is None:
                    teacher_entity = Teacher(
                        external_id=teacher_row.external_id,
                        name=teacher_row.name,
                    )
                    session.add(teacher_entity)
                teacher_entity.name = teacher_row.name
                teacher_entity.allow_gap = teacher_row.allow_gap
                teacher_entity.active = teacher_row.active
                teacher_entity.note = teacher_row.note or None
                session.flush()
                teacher_ids[teacher_row.external_id] = teacher_entity.id
            for external_id, existing_teacher in existing_teachers.items():
                if external_id not in active_teacher_ids:
                    existing_teacher.active = False

            existing_subjects = {row.code: row for row in session.scalars(select(Subject))}
            subject_ids: dict[str, int] = {}
            for subject_row in data.subjects:
                subject_entity = existing_subjects.get(subject_row.code)
                if subject_entity is None:
                    subject_entity = Subject(
                        code=subject_row.code,
                        display_name=subject_row.display_name,
                        school_level=subject_row.school_level,
                        sort_order=subject_row.sort_order,
                    )
                    session.add(subject_entity)
                subject_entity.display_name = subject_row.display_name
                subject_entity.school_level = subject_row.school_level
                subject_entity.sort_order = subject_row.sort_order
                subject_entity.active = subject_row.active
                session.flush()
                subject_ids[subject_row.code] = subject_entity.id

            session.execute(delete(TeacherQualification))
            session.add_all(
                TeacherQualification(
                    teacher_id=teacher_ids[row.teacher_external_id],
                    subject_id=subject_ids[row.subject_code],
                    can_teach=row.can_teach,
                    note=row.note or None,
                )
                for row in data.qualifications
            )
            session.execute(
                delete(RegularLessonProfile).where(
                    RegularLessonProfile.project_id == project.project_id
                )
            )
            session.add_all(
                RegularLessonProfile(
                    project_id=project.project_id,
                    student_id=student_ids[row.student_external_id],
                    subject_id=subject_ids[row.subject_code],
                    regular_teacher_id_optional=(
                        teacher_ids.get(row.regular_teacher_external_id)
                        if row.regular_teacher_external_id
                        else None
                    ),
                    regular_teacher_priority=row.regular_teacher_priority,
                    one_to_one_required=row.one_to_one_required,
                    note=row.note or None,
                )
                for row in data.regular_lessons
            )

        # 空欄IDへ採番した結果と在籍者優先の並びを共通ファイルへ戻す。
        write_shared_roster(source, data)
        self._projects.refresh_current()
        return SharedRosterSyncResult(
            students=len(data.students),
            teachers=len(data.teachers),
            qualifications=len(data.qualifications),
            regular_lessons=len(data.regular_lessons),
        )

    def _from_current_project(self) -> SharedRosterData | None:
        current = self._projects.current
        if current is None:
            return None
        database = self._projects.require_database()
        with database.session_factory() as session:
            students = list(session.scalars(select(Student).order_by(Student.external_id)))
            teachers = list(session.scalars(select(Teacher).order_by(Teacher.external_id)))
            subjects = list(session.scalars(select(Subject).order_by(Subject.sort_order)))
            qualifications = list(session.scalars(select(TeacherQualification)))
            profiles = list(
                session.scalars(
                    select(RegularLessonProfile).where(
                        RegularLessonProfile.project_id == current.project_id
                    )
                )
            )
            if not profiles:
                profiles = [
                    RegularLessonProfile(
                        project_id=row.project_id,
                        student_id=row.student_id,
                        subject_id=row.subject_id,
                        regular_teacher_id_optional=row.regular_teacher_id_optional,
                        regular_teacher_priority=row.regular_teacher_priority,
                        one_to_one_required=row.one_to_one_required,
                        note=row.note,
                    )
                    for row in session.scalars(
                        select(LessonRequest).where(LessonRequest.project_id == current.project_id)
                    )
                ]
            student_external = {row.id: row.external_id for row in students}
            teacher_external = {row.id: row.external_id for row in teachers}
            subject_code = {row.id: row.code for row in subjects}
            return SharedRosterData(
                students=tuple(
                    SharedStudent(
                        row.external_id,
                        *_split_name(row.name),
                        row.grade,
                        row.default_max_consecutive_slots,
                        row.allow_gap,
                        row.active,
                        row.note or "",
                    )
                    for row in students
                ),
                teachers=tuple(
                    SharedTeacher(
                        row.external_id,
                        *_split_name(row.name),
                        row.allow_gap,
                        row.active,
                        row.note or "",
                    )
                    for row in teachers
                ),
                subjects=tuple(
                    SharedSubject(
                        row.code,
                        row.display_name,
                        row.school_level,
                        row.sort_order,
                        row.active,
                    )
                    for row in subjects
                ),
                qualifications=tuple(
                    SharedQualification(
                        teacher_external[row.teacher_id],
                        subject_code[row.subject_id],
                        row.can_teach,
                        row.note or "",
                    )
                    for row in qualifications
                    if row.teacher_id in teacher_external and row.subject_id in subject_code
                ),
                regular_lessons=tuple(
                    SharedRegularLesson(
                        student_external[row.student_id],
                        subject_code[row.subject_id],
                        (
                            teacher_external.get(row.regular_teacher_id_optional, "")
                            if row.regular_teacher_id_optional is not None
                            else ""
                        ),
                        row.regular_teacher_priority,
                        row.one_to_one_required,
                        row.note or "",
                    )
                    for row in profiles
                    if row.student_id in student_external and row.subject_id in subject_code
                ),
            )


def _split_name(name: str) -> tuple[str, str]:
    normalized = " ".join(name.replace("　", " ").split())
    parts = normalized.split(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


__all__ = ["SharedRosterService", "SharedRosterSyncResult"]
