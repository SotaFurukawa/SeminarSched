"""Phase 6のプロジェクト単位出力設定を追加する。

Revision ID: 20260729_0006
Revises: 20260729_0005
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0006"
down_revision: str | None = "20260729_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "output_settings",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("paper_size", sa.String(length=10), nullable=False),
        sa.Column("orientation", sa.String(length=20), nullable=False),
        sa.Column("visible_fields_json", sa.Text(), nullable=False),
        sa.Column("days_per_page", sa.Integer(), nullable=False),
        sa.Column("teacher_columns_per_page", sa.Integer(), nullable=False),
        sa.Column("font_size", sa.Float(), nullable=False),
        sa.Column("margin_mm", sa.Float(), nullable=False),
        sa.Column("file_name_pattern", sa.String(length=255), nullable=False),
        sa.Column("default_output_directory_optional", sa.Text(), nullable=True),
        sa.Column("student_page_mode", sa.String(length=30), nullable=False),
        sa.Column("csv_with_bom", sa.Boolean(), nullable=False),
        sa.Column("style_rules_json", sa.Text(), nullable=False),
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
            "paper_size IN ('A3', 'A4')",
            name=op.f("ck_output_settings_paper_size_value"),
        ),
        sa.CheckConstraint(
            "orientation IN ('landscape', 'portrait')",
            name=op.f("ck_output_settings_orientation_value"),
        ),
        sa.CheckConstraint(
            "length(trim(visible_fields_json)) > 0",
            name=op.f("ck_output_settings_visible_fields_json_not_blank"),
        ),
        sa.CheckConstraint(
            "days_per_page BETWEEN 1 AND 7",
            name=op.f("ck_output_settings_days_per_page_range"),
        ),
        sa.CheckConstraint(
            "teacher_columns_per_page BETWEEN 1 AND 20",
            name=op.f("ck_output_settings_teacher_columns_per_page_range"),
        ),
        sa.CheckConstraint(
            "font_size BETWEEN 5.0 AND 18.0",
            name=op.f("ck_output_settings_font_size_range"),
        ),
        sa.CheckConstraint(
            "margin_mm BETWEEN 0.0 AND 30.0",
            name=op.f("ck_output_settings_margin_mm_range"),
        ),
        sa.CheckConstraint(
            "length(trim(file_name_pattern)) > 0",
            name=op.f("ck_output_settings_file_name_pattern_not_blank"),
        ),
        sa.CheckConstraint(
            "student_page_mode IN ('one_per_page', 'combined')",
            name=op.f("ck_output_settings_student_page_mode_value"),
        ),
        sa.CheckConstraint(
            "length(trim(style_rules_json)) > 0",
            name=op.f("ck_output_settings_style_rules_json_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_output_settings_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            name=op.f("pk_output_settings"),
        ),
    )


def downgrade() -> None:
    op.drop_table("output_settings")
