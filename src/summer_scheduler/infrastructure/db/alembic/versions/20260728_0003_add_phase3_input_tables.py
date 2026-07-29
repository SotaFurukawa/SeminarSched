"""Phase 3のアンケート・集団授業・入力検証テーブルを追加する。

Revision ID: 20260728_0003
Revises: 20260728_0002
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0003"
down_revision: str | None = "20260728_0002"
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
    op.create_index(
        "ix_time_slots_project_id_id_unique",
        "time_slots",
        ["project_id", "id"],
        unique=True,
    )

    op.create_table(
        "student_availabilities",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time_slot_id", sa.Integer(), nullable=False),
        sa.Column("availability_level", sa.Integer(), nullable=False),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "availability_level BETWEEN 0 AND 2",
            name=op.f("ck_student_availabilities_availability_level_range"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_student_availabilities_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "time_slot_id"],
            ["time_slots.project_id", "time_slots.id"],
            name="fk_student_availabilities_project_slot_time_slots",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_student_availabilities_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "student_id",
            "date",
            "time_slot_id",
            name=op.f("pk_student_availabilities"),
        ),
    )
    op.create_index(
        "ix_student_availabilities_project_date_slot",
        "student_availabilities",
        ["project_id", "date", "time_slot_id"],
        unique=False,
    )
    op.create_index(
        "ix_student_availabilities_project_student_date",
        "student_availabilities",
        ["project_id", "student_id", "date"],
        unique=False,
    )

    op.create_table(
        "teacher_availabilities",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time_slot_id", sa.Integer(), nullable=False),
        sa.Column("availability_level", sa.Integer(), nullable=False),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "availability_level BETWEEN 0 AND 2",
            name=op.f("ck_teacher_availabilities_availability_level_range"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_teacher_availabilities_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "time_slot_id"],
            ["time_slots.project_id", "time_slots.id"],
            name="fk_teacher_availabilities_project_slot_time_slots",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name=op.f("fk_teacher_availabilities_teacher_id_teachers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "teacher_id",
            "date",
            "time_slot_id",
            name=op.f("pk_teacher_availabilities"),
        ),
    )
    op.create_index(
        "ix_teacher_availabilities_project_date_slot",
        "teacher_availabilities",
        ["project_id", "date", "time_slot_id"],
        unique=False,
    )
    op.create_index(
        "ix_teacher_availabilities_project_teacher_date",
        "teacher_availabilities",
        ["project_id", "teacher_id", "date"],
        unique=False,
    )

    op.create_table(
        "group_lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("group_code", sa.String(length=100), nullable=False),
        sa.Column("grade", sa.String(length=100), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("course_name", sa.String(length=200), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("teacher_id_optional", sa.Integer(), nullable=True),
        sa.Column("room_optional", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "length(trim(group_code)) > 0",
            name=op.f("ck_group_lessons_group_code_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(grade)) > 0",
            name=op.f("ck_group_lessons_grade_not_blank"),
        ),
        sa.CheckConstraint(
            "course_name IS NULL OR length(trim(course_name)) > 0",
            name=op.f("ck_group_lessons_course_name_not_blank"),
        ),
        sa.CheckConstraint(
            "start_time < end_time",
            name=op.f("ck_group_lessons_time_range"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_group_lessons_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_group_lessons_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id_optional"],
            ["teachers.id"],
            name=op.f("fk_group_lessons_teacher_id_optional_teachers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_lessons")),
        sa.UniqueConstraint(
            "project_id",
            "group_code",
            name=op.f("uq_group_lessons_project_group_code"),
        ),
    )
    op.create_index(
        "ix_group_lessons_project_date_time",
        "group_lessons",
        ["project_id", "date", "start_time", "end_time"],
        unique=False,
    )
    op.create_index(
        "ix_group_lessons_project_teacher_date",
        "group_lessons",
        ["project_id", "teacher_id_optional", "date"],
        unique=False,
    )

    op.create_table(
        "group_lesson_students",
        sa.Column("group_lesson_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["group_lesson_id"],
            ["group_lessons.id"],
            name=op.f("fk_group_lesson_students_group_lesson_id_group_lessons"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_group_lesson_students_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "group_lesson_id",
            "student_id",
            name=op.f("pk_group_lesson_students"),
        ),
    )
    op.create_index(
        "ix_group_lesson_students_student_id",
        "group_lesson_students",
        ["student_id"],
        unique=False,
    )

    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("import_type", sa.String(length=50), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column(
            "mapping_json",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(import_type)) > 0",
            name=op.f("ck_import_batches_import_type_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(source_file_name)) > 0",
            name=op.f("ck_import_batches_source_file_name_not_blank"),
        ),
        sa.CheckConstraint(
            "row_count >= 0 AND success_count >= 0 AND warning_count >= 0 AND error_count >= 0",
            name=op.f("ck_import_batches_counts_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_import_batches_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_index(
        "ix_import_batches_project_type_imported",
        "import_batches",
        ["project_id", "import_type", "imported_at"],
        unique=False,
    )

    op.create_table(
        "validation_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("issue_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id_optional", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "details_json",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "resolved",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "severity IN ('error', 'warning', 'info')",
            name=op.f("ck_validation_issues_severity_value"),
        ),
        sa.CheckConstraint(
            "length(trim(issue_type)) > 0",
            name=op.f("ck_validation_issues_issue_type_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(entity_type)) > 0",
            name=op.f("ck_validation_issues_entity_type_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(message)) > 0",
            name=op.f("ck_validation_issues_message_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_validation_issues_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_issues")),
    )
    op.create_index(
        "ix_validation_issues_project_entity",
        "validation_issues",
        ["project_id", "entity_type", "entity_id_optional"],
        unique=False,
    )
    op.create_index(
        "ix_validation_issues_project_resolved_severity",
        "validation_issues",
        ["project_id", "resolved", "severity"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(trim(action)) > 0",
            name=op.f("ck_audit_logs_action_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(entity_type)) > 0",
            name=op.f("ck_audit_logs_entity_type_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(entity_id)) > 0",
            name=op.f("ck_audit_logs_entity_id_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_audit_logs_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_project_entity",
        "audit_logs",
        ["project_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_project_timestamp",
        "audit_logs",
        ["project_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("validation_issues")
    op.drop_table("import_batches")
    op.drop_table("group_lesson_students")
    op.drop_table("group_lessons")
    op.drop_table("teacher_availabilities")
    op.drop_table("student_availabilities")
    op.drop_index(
        "ix_time_slots_project_id_id_unique",
        table_name="time_slots",
    )
