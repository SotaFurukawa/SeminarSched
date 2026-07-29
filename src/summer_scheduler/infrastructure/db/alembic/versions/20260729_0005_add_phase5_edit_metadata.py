"""Phase 5の手動編集メタデータと監査項目を追加する。

Revision ID: 20260729_0005
Revises: 20260728_0004
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("assignments") as batch_op:
        batch_op.add_column(sa.Column("note", sa.Text(), nullable=True))

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("reason", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(length=20),
                server_default=sa.text("'system'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "operation_id_optional",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.create_check_constraint(
            "ck_audit_logs_source_value",
            "source IN ('system', 'manual', 'automatic', 'undo', 'redo', 'import')",
        )
        batch_op.create_index(
            "ix_audit_logs_project_operation_id",
            ["project_id", "operation_id_optional"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_index("ix_audit_logs_project_operation_id")
        batch_op.drop_constraint(
            "ck_audit_logs_source_value",
            type_="check",
        )
        batch_op.drop_column("operation_id_optional")
        batch_op.drop_column("source")
        batch_op.drop_column("reason")

    with op.batch_alter_table("assignments") as batch_op:
        batch_op.drop_column("note")
