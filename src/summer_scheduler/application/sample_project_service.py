"""架空名だけを使うPhase 3の再現用サンプルプロジェクト作成。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from summer_scheduler.application.project_service import ProjectService, ProjectSummary
from summer_scheduler.application.project_validation_service import (
    ProjectValidationService,
)
from summer_scheduler.infrastructure.db.models import (
    AuditLog,
    GroupLesson,
    GroupLessonStudent,
    LessonRequest,
    Student,
    StudentAvailability,
    Subject,
    Teacher,
    TeacherAvailability,
    TeacherQualification,
    TimeSlot,
)

_SAMPLE_START = date(2026, 8, 3)
_SAMPLE_END = date(2026, 8, 7)

_STUDENTS = (
    ("S-001", "架空 青空", "中1"),
    ("S-002", "架空 若葉", "中1"),
    ("S-003", "架空 星河", "中2"),
    ("S-004", "架空 朝日", "中2"),
    ("S-005", "架空 未来", "中3"),
    ("S-006", "架空 光", "中3"),
    ("S-007", "架空 風花", "高1"),
    ("S-008", "架空 虹", "高1"),
    ("S-009", "架空 海音", "高2"),
    ("S-010", "架空 森", "高2"),
)

_TEACHERS = (
    ("T-001", "架空 講師あおい"),
    ("T-002", "架空 講師みどり"),
    ("T-003", "架空 講師ひかり"),
    ("T-004", "架空 講師つばさ"),
    ("T-005", "架空 講師かなた"),
)


class SampleProjectService:
    """UIから明示的に選んだ場所へ匿名サンプルDBを生成する。"""

    def __init__(self, projects: ProjectService) -> None:
        self._projects = projects

    def create_anonymous_sample(self, path: Path) -> ProjectSummary:
        """Phase 3までの入力一式と意図的な警告1件を持つプロジェクトを作る。"""
        summary = self._projects.create_project(
            path,
            title="匿名サンプル 2026夏期講習",
            campus_name="架空みらい校",
            start_date=_SAMPLE_START,
            end_date=_SAMPLE_END,
        )
        database = self._projects.require_database()
        try:
            with database.session_factory.begin() as session:
                subjects = {
                    row.code: row
                    for row in session.scalars(
                        select(Subject).where(
                            Subject.code.in_(("JH_ENG", "JH_MATH", "HS_ENG", "HS_MATH_GENERAL"))
                        )
                    )
                }
                slots = list(
                    session.scalars(
                        select(TimeSlot)
                        .where(TimeSlot.project_id == summary.project_id)
                        .order_by(TimeSlot.sort_order)
                    )
                )
                if len(subjects) != 4 or not slots:
                    raise RuntimeError("サンプル作成に必要な既定科目・コマがありません")

                students = [
                    Student(
                        external_id=external_id,
                        name=name,
                        grade=grade,
                        default_max_consecutive_slots=(3 if external_id == "S-005" else 2),
                        allow_gap=False,
                        note="匿名サンプル",
                        active=True,
                    )
                    for external_id, name, grade in _STUDENTS
                ]
                teachers = [
                    Teacher(
                        external_id=external_id,
                        name=name,
                        allow_gap=False,
                        note="匿名サンプル",
                        active=True,
                    )
                    for external_id, name in _TEACHERS
                ]
                session.add_all([*students, *teachers])
                session.flush()
                students_by_external = {row.external_id: row for row in students}
                teachers_by_external = {row.external_id: row for row in teachers}

                qualification_codes = {
                    "T-001": ("JH_ENG", "HS_ENG"),
                    "T-002": ("JH_MATH", "HS_MATH_GENERAL"),
                    "T-003": ("JH_ENG", "JH_MATH"),
                    "T-004": ("HS_ENG", "HS_MATH_GENERAL"),
                    # T-005はJH_MATHのみ。英語の希望講師に設定して警告を再現する。
                    "T-005": ("JH_MATH",),
                }
                session.add_all(
                    TeacherQualification(
                        teacher_id=teachers_by_external[teacher_external_id].id,
                        subject_id=subjects[subject_code].id,
                        can_teach=True,
                        note="匿名サンプル",
                    )
                    for teacher_external_id, codes in qualification_codes.items()
                    for subject_code in codes
                )

                request_specs = (
                    ("S-001", "JH_ENG", "T-001"),
                    ("S-002", "JH_MATH", "T-002"),
                    ("S-003", "JH_ENG", "T-003"),
                    ("S-004", "JH_MATH", "T-003"),
                    ("S-005", "JH_MATH", "T-002"),
                    ("S-006", "JH_ENG", "T-001"),
                    ("S-007", "HS_ENG", "T-004"),
                    ("S-008", "HS_MATH_GENERAL", "T-004"),
                    ("S-009", "HS_ENG", "T-001"),
                    ("S-010", "HS_MATH_GENERAL", "T-002"),
                )
                requests: list[LessonRequest] = []
                for index, (student_id, subject_code, teacher_id) in enumerate(
                    request_specs,
                    start=1,
                ):
                    preferred_warning_teacher = (
                        teachers_by_external["T-005"].id if student_id == "S-001" else None
                    )
                    requests.append(
                        LessonRequest(
                            project_id=summary.project_id,
                            student_id=students_by_external[student_id].id,
                            subject_id=subjects[subject_code].id,
                            required_sessions=2,
                            regular_teacher_id_optional=teachers_by_external[teacher_id].id,
                            regular_teacher_priority=(5 if student_id == "S-002" else 3),
                            preferred_teacher_1_id_optional=preferred_warning_teacher,
                            one_to_one_required=(student_id == "S-003"),
                            max_consecutive_slots_override_optional=(
                                3 if student_id == "S-005" else None
                            ),
                            allow_gap_override_optional=False,
                            note=f"匿名サンプル受講希望{index}",
                        )
                    )
                session.add_all(requests)

                for day in _date_range(_SAMPLE_START, _SAMPLE_END):
                    for student_index, student in enumerate(students):
                        session.add_all(
                            StudentAvailability(
                                project_id=summary.project_id,
                                student_id=student.id,
                                date=day,
                                time_slot_id=slot.id,
                                availability_level=(
                                    2 if (student_index + slot.sort_order + day.day) % 4 == 0 else 1
                                ),
                            )
                            for slot in slots
                        )
                    for teacher_index, teacher in enumerate(teachers):
                        session.add_all(
                            TeacherAvailability(
                                project_id=summary.project_id,
                                teacher_id=teacher.id,
                                date=day,
                                time_slot_id=slot.id,
                                availability_level=(
                                    2 if (teacher_index + slot.sort_order + day.day) % 3 == 0 else 1
                                ),
                            )
                            for slot in slots
                        )

                group = GroupLesson(
                    project_id=summary.project_id,
                    group_code="GROUP-001",
                    grade="中2",
                    subject_id=subjects["JH_MATH"].id,
                    course_name="架空 数学演習",
                    date=_SAMPLE_START,
                    start_time=slots[2].start_time,
                    end_time=slots[2].end_time,
                    teacher_id_optional=teachers_by_external["T-002"].id,
                    room_optional="架空教室A",
                    note="匿名サンプル集団授業",
                )
                session.add(group)
                session.flush()
                session.add_all(
                    GroupLessonStudent(
                        group_lesson_id=group.id,
                        student_id=students_by_external[student_external_id].id,
                    )
                    for student_external_id in ("S-003", "S-004", "S-005")
                )
                session.add(
                    AuditLog(
                        project_id=summary.project_id,
                        action="sample_project_created",
                        entity_type="course_project",
                        entity_id=str(summary.project_id),
                        before_json=None,
                        after_json=json.dumps(
                            {
                                "students": len(students),
                                "teachers": len(teachers),
                                "lesson_requests": len(requests),
                                "group_lessons": 1,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                )
        except Exception:
            self._projects.close_project()
            summary.path.unlink(missing_ok=True)
            raise

        ProjectValidationService(self._projects).run_validation()
        return self._projects.refresh_current()


def _date_range(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return tuple(days)


__all__ = ["SampleProjectService"]
