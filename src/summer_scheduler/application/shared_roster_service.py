"""講習プロジェクトから独立した共通名簿を管理するApplication Service。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from shutil import copy2

from sqlalchemy import delete, select

from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.domain.defaults import DEFAULT_SUBJECTS
from summer_scheduler.domain.identifiers import next_person_external_id
from summer_scheduler.domain.validation import raise_for_errors, validate_student, validate_teacher
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

    def export_new_template(self, destination: Path) -> Path:
        """既定科目入りの空テンプレートを、共通正本を変えずに保存する。"""
        target = destination.expanduser().resolve()
        write_shared_roster(target, empty_shared_roster())
        return target

    def import_workbook(self, source: Path) -> SharedRosterSyncResult | None:
        """外部ブックを検証・バックアップして共通正本へ取り込む。"""
        incoming = source.expanduser().resolve()
        if incoming == self.path.resolve():
            return self.sync_to_current_project() if self._projects.current is not None else None

        data = _merge_default_subjects(self._read_with_reserved_ids(incoming))
        existing = self.path.is_file()
        backup: Path | None = None
        if existing:
            backup_directory = self._projects.workspace_directory / "基本情報バックアップ"
            backup_directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup = backup_directory / f"生徒・講師_基本情報(by{stamp}).xlsx"
            copy2(self.path, backup)
        try:
            reserved_students, reserved_teachers = self._reserved_external_ids()
            write_shared_roster(
                self.path,
                data,
                reserved_student_ids=reserved_students,
                reserved_teacher_ids=reserved_teachers,
            )
            if self._projects.current is not None:
                return self.sync_to_current_project(write_back=False)
        except Exception:
            if backup is not None:
                copy2(backup, self.path)
            elif not existing:
                self.path.unlink(missing_ok=True)
            raise
        return None

    def sync_to_current_project(self, *, write_back: bool = True) -> SharedRosterSyncResult:
        """共通名簿を検証し、現在のプロジェクトへ1 transactionで反映する。"""
        source = self.ensure_workbook()
        project = self._projects.require_project()
        database = self._projects.require_database()
        reserved_students, reserved_teachers = self._reserved_external_ids()
        data = read_shared_roster(
            source,
            reserved_student_ids=reserved_students,
            reserved_teacher_ids=reserved_teachers,
        )
        data = _merge_default_subjects(data)
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
        if write_back:
            write_shared_roster(
                source,
                data,
                reserved_student_ids=reserved_students,
                reserved_teacher_ids=reserved_teachers,
            )
        self._projects.refresh_current()
        return SharedRosterSyncResult(
            students=len(data.students),
            teachers=len(data.teachers),
            qualifications=len(data.qualifications),
            regular_lessons=len(data.regular_lessons),
        )

    def sync_from_current_project(self) -> Path:
        """現在の生徒・講師基本情報を共通Excelへ書き戻す。"""
        data = self._from_current_project()
        if data is None:
            raise ValueError("プロジェクトが開かれていません")
        reserved_students, reserved_teachers = self._reserved_external_ids()
        write_shared_roster(
            self.path,
            _merge_default_subjects(data),
            reserved_student_ids=reserved_students,
            reserved_teacher_ids=reserved_teachers,
        )
        return self.path

    def read_roster(self) -> SharedRosterData:
        """プロジェクトの有無にかかわらず共通基本情報を読み込む。"""
        self.ensure_workbook()
        return _merge_default_subjects(self._read_with_reserved_ids(self.path))

    def save_shared_student(
        self,
        *,
        record_external_id: str | None,
        external_id: str,
        name: str,
        grade: str,
        max_consecutive_slots: int,
        allow_gap: bool,
        note: str,
        active: bool,
    ) -> tuple[str, tuple[str, ...]]:
        data = self.read_roster()
        normalized_id = (
            external_id.strip()
            or record_external_id
            or next_person_external_id((row.external_id for row in data.students), prefix="S")
        )
        normalized_name = name.strip()
        raise_for_errors(
            validate_student(
                external_id=normalized_id,
                name=normalized_name,
                grade=grade,
                max_consecutive_slots=max_consecutive_slots,
            )
        )
        if any(
            row.external_id == normalized_id and row.external_id != record_external_id
            for row in data.students
        ):
            raise ValueError("生徒IDが重複しています")
        warnings = tuple(
            f"同姓同名の生徒「{normalized_name}」が登録されています"
            for row in data.students
            if row.external_id != record_external_id and row.name == normalized_name
        )[:1]
        surname, given_name = _split_name(normalized_name)
        saved = SharedStudent(
            normalized_id,
            surname,
            given_name,
            grade.strip(),
            max_consecutive_slots,
            allow_gap,
            active,
            note.strip(),
        )
        students = list(data.students)
        index = next(
            (index for index, row in enumerate(students) if row.external_id == record_external_id),
            None,
        )
        if record_external_id is not None and index is None:
            raise ValueError("生徒が見つかりません")
        if index is None:
            students.append(saved)
        else:
            students[index] = saved
        self._write_roster(replace(data, students=tuple(students)))
        return normalized_id, warnings

    def deactivate_shared_student(self, external_id: str) -> None:
        data = self.read_roster()
        if not any(row.external_id == external_id for row in data.students):
            raise ValueError("生徒が見つかりません")
        students = tuple(
            replace(row, active=False) if row.external_id == external_id else row
            for row in data.students
        )
        self._write_roster(replace(data, students=students))

    def delete_shared_student(self, external_id: str) -> None:
        data = self.read_roster()
        students = tuple(row for row in data.students if row.external_id != external_id)
        if len(students) == len(data.students):
            raise ValueError("生徒が見つかりません")
        regular_lessons = tuple(
            row for row in data.regular_lessons if row.student_external_id != external_id
        )
        self._write_roster(replace(data, students=students, regular_lessons=regular_lessons))

    def save_shared_teacher(
        self,
        *,
        record_external_id: str | None,
        external_id: str,
        name: str,
        allow_gap: bool,
        note: str,
        active: bool,
    ) -> tuple[str, tuple[str, ...]]:
        data = self.read_roster()
        normalized_id = (
            external_id.strip()
            or record_external_id
            or next_person_external_id((row.external_id for row in data.teachers), prefix="T")
        )
        normalized_name = name.strip()
        raise_for_errors(validate_teacher(external_id=normalized_id, name=normalized_name))
        if any(
            row.external_id == normalized_id and row.external_id != record_external_id
            for row in data.teachers
        ):
            raise ValueError("講師IDが重複しています")
        warnings = tuple(
            f"同姓同名の講師「{normalized_name}」が登録されています"
            for row in data.teachers
            if row.external_id != record_external_id and row.name == normalized_name
        )[:1]
        surname, given_name = _split_name(normalized_name)
        saved = SharedTeacher(
            normalized_id,
            surname,
            given_name,
            allow_gap,
            active,
            note.strip(),
        )
        teachers = list(data.teachers)
        index = next(
            (index for index, row in enumerate(teachers) if row.external_id == record_external_id),
            None,
        )
        if record_external_id is not None and index is None:
            raise ValueError("講師が見つかりません")
        if index is None:
            teachers.append(saved)
        else:
            teachers[index] = saved
        self._write_roster(replace(data, teachers=tuple(teachers)))
        return normalized_id, warnings

    def deactivate_shared_teacher(self, external_id: str) -> None:
        data = self.read_roster()
        if not any(row.external_id == external_id for row in data.teachers):
            raise ValueError("講師が見つかりません")
        teachers = tuple(
            replace(row, active=False) if row.external_id == external_id else row
            for row in data.teachers
        )
        self._write_roster(replace(data, teachers=teachers))

    def delete_shared_teacher(self, external_id: str) -> None:
        data = self.read_roster()
        teachers = tuple(row for row in data.teachers if row.external_id != external_id)
        if len(teachers) == len(data.teachers):
            raise ValueError("講師が見つかりません")
        qualifications = tuple(
            row for row in data.qualifications if row.teacher_external_id != external_id
        )
        regular_lessons = tuple(
            replace(row, regular_teacher_external_id="")
            if row.regular_teacher_external_id == external_id
            else row
            for row in data.regular_lessons
        )
        self._write_roster(
            replace(
                data,
                teachers=teachers,
                qualifications=qualifications,
                regular_lessons=regular_lessons,
            )
        )

    def replace_shared_qualifications(
        self,
        teacher_external_id: str,
        values: dict[str, bool],
    ) -> None:
        data = self.read_roster()
        if not any(row.external_id == teacher_external_id for row in data.teachers):
            raise ValueError("講師が見つかりません")
        valid_codes = {row.code for row in data.subjects}
        if not set(values).issubset(valid_codes):
            raise ValueError("指導可能科目に不正な科目が含まれています")
        existing_notes = {
            row.subject_code: row.note
            for row in data.qualifications
            if row.teacher_external_id == teacher_external_id
        }
        qualifications = tuple(
            row for row in data.qualifications if row.teacher_external_id != teacher_external_id
        ) + tuple(
            SharedQualification(
                teacher_external_id,
                subject_code,
                can_teach,
                existing_notes.get(subject_code, ""),
            )
            for subject_code, can_teach in values.items()
        )
        self._write_roster(replace(data, qualifications=qualifications))

    def copy_shared_qualifications(
        self,
        *,
        source_teacher_external_id: str,
        target_teacher_external_id: str,
    ) -> None:
        data = self.read_roster()
        copied = {
            row.subject_code: row.can_teach
            for row in data.qualifications
            if row.teacher_external_id == source_teacher_external_id
        }
        self.replace_shared_qualifications(target_teacher_external_id, copied)

    def _write_roster(self, data: SharedRosterData) -> None:
        reserved_students, reserved_teachers = self._reserved_external_ids()
        write_shared_roster(
            self.path,
            _merge_default_subjects(data),
            reserved_student_ids=reserved_students,
            reserved_teacher_ids=reserved_teachers,
        )

    def _read_with_reserved_ids(self, source: Path) -> SharedRosterData:
        reserved_student_ids, reserved_teacher_ids = self._reserved_external_ids()
        return read_shared_roster(
            source,
            reserved_student_ids=reserved_student_ids,
            reserved_teacher_ids=reserved_teacher_ids,
        )

    def _reserved_external_ids(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """現在DBに残る退籍者を含め、再利用してはいけない人物IDを返す。"""
        if self._projects.current is None:
            return (), ()
        database = self._projects.require_database()
        with database.session_factory() as session:
            reserved_student_ids = tuple(
                row.external_id for row in session.scalars(select(Student))
            )
            reserved_teacher_ids = tuple(
                row.external_id for row in session.scalars(select(Teacher))
            )
        return reserved_student_ids, reserved_teacher_ids

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


def _merge_default_subjects(data: SharedRosterData) -> SharedRosterData:
    """既定科目を安全に改称・追加し、既存資格から新資格を推定しない。"""
    existing_by_code = {row.code: row for row in data.subjects}
    defaults = tuple(
        SharedSubject(
            item.code,
            item.display_name,
            item.school_level,
            item.sort_order,
            existing_by_code[item.code].active if item.code in existing_by_code else True,
        )
        for item in DEFAULT_SUBJECTS
    )
    default_codes = {row.code for row in defaults}
    custom = tuple(row for row in data.subjects if row.code not in default_codes)
    return SharedRosterData(
        students=data.students,
        teachers=data.teachers,
        subjects=defaults + custom,
        qualifications=data.qualifications,
        regular_lessons=data.regular_lessons,
    )


__all__ = ["SharedRosterService", "SharedRosterSyncResult"]
