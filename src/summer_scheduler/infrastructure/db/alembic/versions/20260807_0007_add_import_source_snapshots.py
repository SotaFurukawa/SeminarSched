"""アンケート原本snapshotをプロジェクトへ内包する。

Revision ID: 20260807_0007
Revises: 20260729_0006
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0007"
down_revision: str | None = "20260729_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_source_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("import_type", sa.String(length=50), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(import_type)) > 0",
            name=op.f("ck_import_source_snapshots_import_type_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(source_file_name)) > 0",
            name=op.f("ck_import_source_snapshots_source_file_name_not_blank"),
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name=op.f("ck_import_source_snapshots_size_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_import_source_snapshots_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_source_snapshots")),
        sa.UniqueConstraint(
            "project_id",
            "import_type",
            name=op.f("uq_import_source_snapshots_project_type"),
        ),
    )


def downgrade() -> None:
    op.drop_table("import_source_snapshots")
