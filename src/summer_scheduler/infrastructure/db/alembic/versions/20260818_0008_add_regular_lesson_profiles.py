"""通常授業の担当情報を講習受講希望から分離する。

Revision ID: 20260818_0008
Revises: 20260807_0007
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0008"
down_revision: str | None = "20260807_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regular_lesson_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("regular_teacher_id_optional", sa.Integer(), nullable=True),
        sa.Column(
            "regular_teacher_priority",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "one_to_one_required",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "regular_teacher_priority BETWEEN 1 AND 5",
            name=op.f("ck_regular_lesson_profiles_regular_teacher_priority_range"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_regular_lesson_profiles_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_regular_lesson_profiles_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_regular_lesson_profiles_subject_id_subjects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["regular_teacher_id_optional"],
            ["teachers.id"],
            name=op.f("fk_regular_lesson_profiles_regular_teacher_id_optional_teachers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regular_lesson_profiles")),
        sa.UniqueConstraint(
            "project_id",
            "student_id",
            "subject_id",
            name="uq_regular_lesson_profiles_project_student_subject",
        ),
    )


def downgrade() -> None:
    op.drop_table("regular_lesson_profiles")
