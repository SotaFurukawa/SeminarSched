"""Phase 2のプロジェクト・マスター管理用テーブルを追加する。

Revision ID: 20260728_0002
Revises: 20260728_0001
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0002"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> tuple[sa.Column[sa.DateTime], sa.Column[sa.DateTime]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "campuses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address_optional", sa.Text(), nullable=True),
        sa.Column("logo_path_optional", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campuses")),
    )
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("grade", sa.String(length=100), nullable=False),
        sa.Column(
            "default_max_consecutive_slots",
            sa.Integer(),
            server_default=sa.text("2"),
            nullable=False,
        ),
        sa.Column(
            "allow_gap",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(external_id)) > 0",
            name=op.f("ck_students_external_id_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name=op.f("ck_students_name_not_blank"),
        ),
        sa.CheckConstraint(
            "default_max_consecutive_slots > 0",
            name=op.f("ck_students_max_consecutive_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_students")),
        sa.UniqueConstraint("external_id", name=op.f("uq_students_external_id")),
    )
    op.create_table(
        "teachers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "allow_gap",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(external_id)) > 0",
            name=op.f("ck_teachers_external_id_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name=op.f("ck_teachers_name_not_blank"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teachers")),
        sa.UniqueConstraint("external_id", name=op.f("uq_teachers_external_id")),
    )
    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("school_level", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(code)) > 0",
            name=op.f("ck_subjects_code_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0",
            name=op.f("ck_subjects_display_name_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(school_level)) > 0",
            name=op.f("ck_subjects_school_level_not_blank"),
        ),
        sa.CheckConstraint(
            "sort_order >= 1",
            name=op.f("ck_subjects_sort_order_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subjects")),
        sa.UniqueConstraint("code", name=op.f("uq_subjects_code")),
    )
    op.create_table(
        "course_projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "file_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "start_date <= end_date",
            name=op.f("ck_course_projects_date_range"),
        ),
        sa.CheckConstraint(
            "file_version >= 1",
            name=op.f("ck_course_projects_file_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["campus_id"],
            ["campuses.id"],
            name=op.f("fk_course_projects_campus_id_campuses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_projects")),
    )
    op.create_table(
        "time_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(code)) > 0",
            name=op.f("ck_time_slots_code_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0",
            name=op.f("ck_time_slots_display_name_not_blank"),
        ),
        sa.CheckConstraint(
            "start_time < end_time",
            name=op.f("ck_time_slots_time_range"),
        ),
        sa.CheckConstraint(
            "sort_order >= 1",
            name=op.f("ck_time_slots_sort_order_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_time_slots_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_time_slots")),
        sa.UniqueConstraint(
            "project_id",
            "code",
            name=op.f("uq_time_slots_project_code"),
        ),
        sa.UniqueConstraint(
            "project_id",
            "sort_order",
            name=op.f("uq_time_slots_project_sort_order"),
        ),
    )
    op.create_table(
        "open_dates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "is_open",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_open_dates_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_open_dates")),
        sa.UniqueConstraint(
            "project_id",
            "date",
            name=op.f("uq_open_dates_project_date"),
        ),
    )
    op.create_table(
        "teacher_qualifications",
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column(
            "can_teach",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_teacher_qualifications_subject_id_subjects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name=op.f("fk_teacher_qualifications_teacher_id_teachers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "teacher_id",
            "subject_id",
            name=op.f("pk_teacher_qualifications"),
        ),
    )
    op.create_table(
        "lesson_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("required_sessions", sa.Integer(), nullable=False),
        sa.Column("regular_teacher_id_optional", sa.Integer(), nullable=True),
        sa.Column(
            "regular_teacher_priority",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("preferred_teacher_1_id_optional", sa.Integer(), nullable=True),
        sa.Column("preferred_teacher_2_id_optional", sa.Integer(), nullable=True),
        sa.Column("preferred_teacher_3_id_optional", sa.Integer(), nullable=True),
        sa.Column(
            "one_to_one_required",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_consecutive_slots_override_optional",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("allow_gap_override_optional", sa.Boolean(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "required_sessions >= 1",
            name=op.f("ck_lesson_requests_required_sessions_positive"),
        ),
        sa.CheckConstraint(
            "regular_teacher_priority BETWEEN 1 AND 5",
            name=op.f("ck_lesson_requests_regular_teacher_priority_range"),
        ),
        sa.CheckConstraint(
            "max_consecutive_slots_override_optional IS NULL "
            "OR max_consecutive_slots_override_optional > 0",
            name=op.f("ck_lesson_requests_max_consecutive_override_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["preferred_teacher_1_id_optional"],
            ["teachers.id"],
            name=op.f("fk_lesson_requests_preferred_teacher_1_id_optional_teachers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["preferred_teacher_2_id_optional"],
            ["teachers.id"],
            name=op.f("fk_lesson_requests_preferred_teacher_2_id_optional_teachers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["preferred_teacher_3_id_optional"],
            ["teachers.id"],
            name=op.f("fk_lesson_requests_preferred_teacher_3_id_optional_teachers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_lesson_requests_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["regular_teacher_id_optional"],
            ["teachers.id"],
            name=op.f("fk_lesson_requests_regular_teacher_id_optional_teachers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_lesson_requests_student_id_students"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_lesson_requests_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_requests")),
        sa.UniqueConstraint(
            "project_id",
            "student_id",
            "subject_id",
            name=op.f("uq_lesson_requests_project_student_subject"),
        ),
    )


def downgrade() -> None:
    op.drop_table("lesson_requests")
    op.drop_table("teacher_qualifications")
    op.drop_table("open_dates")
    op.drop_table("time_slots")
    op.drop_table("course_projects")
    op.drop_table("subjects")
    op.drop_table("teachers")
    op.drop_table("students")
    op.drop_table("campuses")
