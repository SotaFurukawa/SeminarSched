"""SQLAlchemy 2で表現するアプリケーションの永続化モデル。

ORMモデルはSQLiteの表現に限定し、QMLや最適化処理へ直接公開しない。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from summer_scheduler.infrastructure.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """編集対象レコードへ共通の作成・更新日時を付与する。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.current_timestamp(),
    )


class ApplicationMetadata(Base):
    """DB自体に付随する小さなメタデータ。"""

    __tablename__ = "application_metadata"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Campus(TimestampMixin, Base):
    """講習プロジェクトを実施する校舎。"""

    __tablename__ = "campuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address_optional: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_path_optional: Mapped[str | None] = mapped_column(Text, nullable=True)

    projects: Mapped[list[CourseProject]] = relationship(
        back_populates="campus",
        passive_deletes=True,
    )


class CourseProject(TimestampMixin, Base):
    """1つの ``.jukuschedule`` ファイルが内包する講習プロジェクト。"""

    __tablename__ = "course_projects"
    __table_args__ = (
        CheckConstraint(
            "start_date <= end_date",
            name="date_range",
        ),
        CheckConstraint(
            "file_version >= 1",
            name="file_version_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    file_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    campus: Mapped[Campus] = relationship(back_populates="projects")
    time_slots: Mapped[list[TimeSlot]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )
    open_dates: Mapped[list[OpenDate]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )
    lesson_requests: Mapped[list[LessonRequest]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="project",
        passive_deletes=True,
        overlaps="assignments,lesson_request",
    )
    optimization_runs: Mapped[list[OptimizationRun]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )
    output_setting: Mapped[OutputSetting | None] = relationship(
        back_populates="project",
        passive_deletes=True,
        uselist=False,
    )


class OutputSetting(TimestampMixin, Base):
    """プロジェクト単位のPhase 6出力設定。

    ロゴは校舎マスターと二重管理せず、``Campus.logo_path_optional`` を正本とする。
    """

    __tablename__ = "output_settings"
    __table_args__ = (
        CheckConstraint(
            "paper_size IN ('A3', 'A4')",
            name="paper_size_value",
        ),
        CheckConstraint(
            "orientation IN ('landscape', 'portrait')",
            name="orientation_value",
        ),
        CheckConstraint(
            "length(trim(visible_fields_json)) > 0",
            name="visible_fields_json_not_blank",
        ),
        CheckConstraint(
            "days_per_page BETWEEN 1 AND 7",
            name="days_per_page_range",
        ),
        CheckConstraint(
            "teacher_columns_per_page BETWEEN 1 AND 20",
            name="teacher_columns_per_page_range",
        ),
        CheckConstraint(
            "font_size BETWEEN 5.0 AND 18.0",
            name="font_size_range",
        ),
        CheckConstraint(
            "margin_mm BETWEEN 0.0 AND 30.0",
            name="margin_mm_range",
        ),
        CheckConstraint(
            "length(trim(file_name_pattern)) > 0",
            name="file_name_pattern_not_blank",
        ),
        CheckConstraint(
            "student_page_mode IN ('one_per_page', 'combined')",
            name="student_page_mode_value",
        ),
        CheckConstraint(
            "length(trim(style_rules_json)) > 0",
            name="style_rules_json_not_blank",
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    paper_size: Mapped[str] = mapped_column(String(10), nullable=False)
    orientation: Mapped[str] = mapped_column(String(20), nullable=False)
    visible_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    days_per_page: Mapped[int] = mapped_column(Integer, nullable=False)
    teacher_columns_per_page: Mapped[int] = mapped_column(Integer, nullable=False)
    font_size: Mapped[float] = mapped_column(Float, nullable=False)
    margin_mm: Mapped[float] = mapped_column(Float, nullable=False)
    file_name_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    default_output_directory_optional: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    student_page_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    csv_with_bom: Mapped[bool] = mapped_column(Boolean, nullable=False)
    style_rules_json: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped[CourseProject] = relationship(back_populates="output_setting")


class TimeSlot(TimestampMixin, Base):
    """プロジェクト内で順序付けられた授業コマ。"""

    __tablename__ = "time_slots"
    __table_args__ = (
        Index(
            "ix_time_slots_project_id_id_unique",
            "project_id",
            "id",
            unique=True,
        ),
        UniqueConstraint(
            "project_id",
            "code",
            name="uq_time_slots_project_code",
        ),
        UniqueConstraint(
            "project_id",
            "sort_order",
            name="uq_time_slots_project_sort_order",
        ),
        CheckConstraint(
            "length(trim(code)) > 0",
            name="code_not_blank",
        ),
        CheckConstraint(
            "length(trim(display_name)) > 0",
            name="display_name_not_blank",
        ),
        CheckConstraint(
            "start_time < end_time",
            name="time_range",
        ),
        CheckConstraint(
            "sort_order >= 1",
            name="sort_order_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    project: Mapped[CourseProject] = relationship(back_populates="time_slots")


class OpenDate(TimestampMixin, Base):
    """講習期間中の開校・休校設定。"""

    __tablename__ = "open_dates"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "date",
            name="uq_open_dates_project_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    is_open: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[CourseProject] = relationship(back_populates="open_dates")


class Student(TimestampMixin, Base):
    """プロジェクトファイル内で管理する生徒マスター。"""

    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("external_id"),
        CheckConstraint(
            "length(trim(external_id)) > 0",
            name="external_id_not_blank",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="name_not_blank",
        ),
        CheckConstraint(
            "default_max_consecutive_slots > 0",
            name="max_consecutive_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    grade: Mapped[str] = mapped_column(String(100), nullable=False)
    default_max_consecutive_slots: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        server_default="2",
    )
    allow_gap: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    lesson_requests: Mapped[list[LessonRequest]] = relationship(
        back_populates="student",
        passive_deletes=True,
    )


class Teacher(TimestampMixin, Base):
    """プロジェクトファイル内で管理する講師マスター。"""

    __tablename__ = "teachers"
    __table_args__ = (
        UniqueConstraint("external_id"),
        CheckConstraint(
            "length(trim(external_id)) > 0",
            name="external_id_not_blank",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="name_not_blank",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    allow_gap: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    qualifications: Mapped[list[TeacherQualification]] = relationship(
        back_populates="teacher",
        passive_deletes=True,
    )


class Subject(TimestampMixin, Base):
    """安定した英数字コードを持つ科目マスター。"""

    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("code"),
        CheckConstraint(
            "length(trim(code)) > 0",
            name="code_not_blank",
        ),
        CheckConstraint(
            "length(trim(display_name)) > 0",
            name="display_name_not_blank",
        ),
        CheckConstraint(
            "length(trim(school_level)) > 0",
            name="school_level_not_blank",
        ),
        CheckConstraint(
            "sort_order >= 1",
            name="sort_order_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    school_level: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    qualifications: Mapped[list[TeacherQualification]] = relationship(
        back_populates="subject",
        passive_deletes=True,
    )
    lesson_requests: Mapped[list[LessonRequest]] = relationship(
        back_populates="subject",
        passive_deletes=True,
    )


class TeacherQualification(TimestampMixin, Base):
    """講師と科目の組ごとに明示する指導可否。"""

    __tablename__ = "teacher_qualifications"

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    can_teach: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    teacher: Mapped[Teacher] = relationship(back_populates="qualifications")
    subject: Mapped[Subject] = relationship(back_populates="qualifications")


class LessonRequest(TimestampMixin, Base):
    """生徒と科目の組ごとに保持する受講希望。"""

    __tablename__ = "lesson_requests"
    __table_args__ = (
        Index(
            "ix_lesson_requests_project_id_id_unique",
            "project_id",
            "id",
            unique=True,
        ),
        UniqueConstraint(
            "project_id",
            "student_id",
            "subject_id",
            name="uq_lesson_requests_project_student_subject",
        ),
        CheckConstraint(
            "required_sessions >= 1",
            name="required_sessions_positive",
        ),
        CheckConstraint(
            "regular_teacher_priority BETWEEN 1 AND 5",
            name="regular_teacher_priority_range",
        ),
        CheckConstraint(
            "max_consecutive_slots_override_optional IS NULL "
            "OR max_consecutive_slots_override_optional > 0",
            name="max_consecutive_override_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    required_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    regular_teacher_id_optional: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True,
    )
    regular_teacher_priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    preferred_teacher_1_id_optional: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True,
    )
    preferred_teacher_2_id_optional: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True,
    )
    preferred_teacher_3_id_optional: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True,
    )
    one_to_one_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    max_consecutive_slots_override_optional: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    allow_gap_override_optional: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[CourseProject] = relationship(back_populates="lesson_requests")
    student: Mapped[Student] = relationship(back_populates="lesson_requests")
    subject: Mapped[Subject] = relationship(back_populates="lesson_requests")
    regular_teacher: Mapped[Teacher | None] = relationship(
        foreign_keys=[regular_teacher_id_optional],
    )
    preferred_teacher_1: Mapped[Teacher | None] = relationship(
        foreign_keys=[preferred_teacher_1_id_optional],
    )
    preferred_teacher_2: Mapped[Teacher | None] = relationship(
        foreign_keys=[preferred_teacher_2_id_optional],
    )
    preferred_teacher_3: Mapped[Teacher | None] = relationship(
        foreign_keys=[preferred_teacher_3_id_optional],
    )
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="lesson_request",
        passive_deletes=True,
        overlaps="assignments,project",
    )


class StudentAvailability(TimestampMixin, Base):
    """生徒のプロジェクト内の日付・コマ別の受講可否。"""

    __tablename__ = "student_availabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "time_slot_id"],
            ["time_slots.project_id", "time_slots.id"],
            ondelete="CASCADE",
            name="fk_student_availabilities_project_slot_time_slots",
        ),
        CheckConstraint(
            "availability_level BETWEEN 0 AND 2",
            name="availability_level_range",
        ),
        Index(
            "ix_student_availabilities_project_date_slot",
            "project_id",
            "date",
            "time_slot_id",
        ),
        Index(
            "ix_student_availabilities_project_student_date",
            "project_id",
            "student_id",
            "date",
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True,
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    time_slot_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    availability_level: Mapped[int] = mapped_column(Integer, nullable=False)


class TeacherAvailability(TimestampMixin, Base):
    """講師のプロジェクト内の日付・コマ別の出勤可否。"""

    __tablename__ = "teacher_availabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "time_slot_id"],
            ["time_slots.project_id", "time_slots.id"],
            ondelete="CASCADE",
            name="fk_teacher_availabilities_project_slot_time_slots",
        ),
        CheckConstraint(
            "availability_level BETWEEN 0 AND 2",
            name="availability_level_range",
        ),
        Index(
            "ix_teacher_availabilities_project_date_slot",
            "project_id",
            "date",
            "time_slot_id",
        ),
        Index(
            "ix_teacher_availabilities_project_teacher_date",
            "project_id",
            "teacher_id",
            "date",
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    time_slot_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    availability_level: Mapped[int] = mapped_column(Integer, nullable=False)


class GroupLesson(TimestampMixin, Base):
    """個別授業より先に固定予定として扱う集団授業。"""

    __tablename__ = "group_lessons"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "group_code",
            name="uq_group_lessons_project_group_code",
        ),
        CheckConstraint(
            "length(trim(group_code)) > 0",
            name="group_code_not_blank",
        ),
        CheckConstraint(
            "length(trim(grade)) > 0",
            name="grade_not_blank",
        ),
        CheckConstraint(
            "course_name IS NULL OR length(trim(course_name)) > 0",
            name="course_name_not_blank",
        ),
        CheckConstraint(
            "start_time < end_time",
            name="time_range",
        ),
        Index(
            "ix_group_lessons_project_date_time",
            "project_id",
            "date",
            "start_time",
            "end_time",
        ),
        Index(
            "ix_group_lessons_project_teacher_date",
            "project_id",
            "teacher_id_optional",
            "date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_code: Mapped[str] = mapped_column(String(100), nullable=False)
    grade: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    course_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    teacher_id_optional: Mapped[int | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True,
    )
    room_optional: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class GroupLessonStudent(TimestampMixin, Base):
    """集団授業と受講生を結ぶ多対多の関連。"""

    __tablename__ = "group_lesson_students"
    __table_args__ = (
        Index(
            "ix_group_lesson_students_student_id",
            "student_id",
        ),
    )

    group_lesson_id: Mapped[int] = mapped_column(
        ForeignKey("group_lessons.id", ondelete="CASCADE"),
        primary_key=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ImportBatch(Base):
    """1回のアンケートまたは集団授業取込みの監査用記録。"""

    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "length(trim(import_type)) > 0",
            name="import_type_not_blank",
        ),
        CheckConstraint(
            "length(trim(source_file_name)) > 0",
            name="source_file_name_not_blank",
        ),
        CheckConstraint(
            "row_count >= 0 AND success_count >= 0 AND warning_count >= 0 AND error_count >= 0",
            name="counts_nonnegative",
        ),
        Index(
            "ix_import_batches_project_type_imported",
            "project_id",
            "import_type",
            "imported_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    import_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.current_timestamp(),
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )


class ValidationIssue(TimestampMixin, Base):
    """最適化開始可否を判断するプロジェクト入力検証結果。"""

    __tablename__ = "validation_issues"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('error', 'warning', 'info')",
            name="severity_value",
        ),
        CheckConstraint(
            "length(trim(issue_type)) > 0",
            name="issue_type_not_blank",
        ),
        CheckConstraint(
            "length(trim(entity_type)) > 0",
            name="entity_type_not_blank",
        ),
        CheckConstraint(
            "length(trim(message)) > 0",
            name="message_not_blank",
        ),
        Index(
            "ix_validation_issues_project_resolved_severity",
            "project_id",
            "resolved",
            "severity",
        ),
        Index(
            "ix_validation_issues_project_entity",
            "project_id",
            "entity_type",
            "entity_id_optional",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id_optional: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )


class AuditLog(Base):
    """利用者操作や取込み反映を追跡する追記型の監査ログ。"""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "length(trim(action)) > 0",
            name="action_not_blank",
        ),
        CheckConstraint(
            "length(trim(entity_type)) > 0",
            name="entity_type_not_blank",
        ),
        CheckConstraint(
            "length(trim(entity_id)) > 0",
            name="entity_id_not_blank",
        ),
        CheckConstraint(
            "source IN ('system', 'manual', 'automatic', 'undo', 'redo', 'import')",
            name="source_value",
        ),
        Index(
            "ix_audit_logs_project_timestamp",
            "project_id",
            "timestamp",
        ),
        Index(
            "ix_audit_logs_project_entity",
            "project_id",
            "entity_type",
            "entity_id",
        ),
        Index(
            "ix_audit_logs_project_operation_id",
            "project_id",
            "operation_id_optional",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.current_timestamp(),
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="system",
        server_default="system",
    )
    operation_id_optional: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )


class OptimizationRun(Base):
    """1回の最適化実行と再現用スナップショット。"""

    __tablename__ = "optimization_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'cancelled', 'failed')",
            name="status_value",
        ),
        CheckConstraint(
            "solver_status IN ('OPTIMAL', 'FEASIBLE', 'INFEASIBLE', 'UNKNOWN', 'MODEL_INVALID')",
            name="solver_status_value",
        ),
        CheckConstraint(
            "time_limit_seconds > 0",
            name="time_limit_positive",
        ),
        CheckConstraint(
            "unassigned_count >= 0 AND warning_count >= 0",
            name="counts_nonnegative",
        ),
        CheckConstraint(
            "elapsed_seconds IS NULL OR elapsed_seconds >= 0",
            name="elapsed_nonnegative",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="finished_after_started",
        ),
        CheckConstraint(
            "length(trim(objective_summary_json)) > 0",
            name="objective_summary_not_blank",
        ),
        CheckConstraint(
            "length(trim(input_snapshot_json)) > 0",
            name="input_snapshot_not_blank",
        ),
        CheckConstraint(
            "length(trim(result_snapshot_json)) > 0",
            name="result_snapshot_not_blank",
        ),
        Index(
            "ix_optimization_runs_project_started",
            "project_id",
            "started_at",
        ),
        Index(
            "ix_optimization_runs_project_status",
            "project_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.current_timestamp(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    solver_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="UNKNOWN",
        server_default="UNKNOWN",
    )
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    objective_summary_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    unassigned_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    warning_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    log_path_optional: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_snapshot_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    result_snapshot_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    random_seed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped[CourseProject] = relationship(back_populates="optimization_runs")
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="optimization_run",
        passive_deletes=True,
    )


class Assignment(TimestampMixin, Base):
    """現在の個別授業時間割を1セッション1行で保持する。"""

    __tablename__ = "assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "lesson_request_id"],
            ["lesson_requests.project_id", "lesson_requests.id"],
            ondelete="RESTRICT",
            name="fk_assignments_project_request_lesson_requests",
        ),
        ForeignKeyConstraint(
            ["project_id", "time_slot_id"],
            ["time_slots.project_id", "time_slots.id"],
            ondelete="RESTRICT",
            name="fk_assignments_project_slot_time_slots",
        ),
        UniqueConstraint(
            "project_id",
            "lesson_request_id",
            "session_index",
            name="uq_assignments_project_request_session",
        ),
        CheckConstraint(
            "session_index >= 1",
            name="session_index_positive",
        ),
        CheckConstraint(
            "length(trim(created_by)) > 0",
            name="created_by_not_blank",
        ),
        Index(
            "ix_assignments_project_date_slot",
            "project_id",
            "date",
            "time_slot_id",
        ),
        Index(
            "ix_assignments_project_teacher_date_slot",
            "project_id",
            "teacher_id",
            "date",
            "time_slot_id",
        ),
        Index(
            "ix_assignments_project_locked",
            "project_id",
            "is_locked",
        ),
        Index(
            "ix_assignments_optimization_run_id",
            "optimization_run_id_optional",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("course_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    lesson_request_id: Mapped[int] = mapped_column(Integer, nullable=False)
    session_index: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    time_slot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    optimization_run_id_optional: Mapped[int | None] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    is_manual: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[CourseProject] = relationship(
        back_populates="assignments",
        overlaps="assignments,lesson_request",
    )
    lesson_request: Mapped[LessonRequest] = relationship(
        back_populates="assignments",
        overlaps="assignments,project",
    )
    teacher: Mapped[Teacher] = relationship()
    optimization_run: Mapped[OptimizationRun | None] = relationship(
        back_populates="assignments",
    )


__all__ = [
    "ApplicationMetadata",
    "Assignment",
    "AuditLog",
    "Campus",
    "CourseProject",
    "GroupLesson",
    "GroupLessonStudent",
    "ImportBatch",
    "LessonRequest",
    "OpenDate",
    "OptimizationRun",
    "OutputSetting",
    "Student",
    "StudentAvailability",
    "Subject",
    "Teacher",
    "TeacherAvailability",
    "TeacherQualification",
    "TimeSlot",
    "ValidationIssue",
]
