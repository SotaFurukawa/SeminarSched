"""開校日ごとの有効コマを保存する。

Revision ID: 20260904_0010
Revises: 20260822_0009
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0010"
down_revision: str | None = "20260822_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("open_dates")}
    if "enabled_time_slot_ids_json" not in columns:
        op.add_column(
            "open_dates",
            sa.Column("enabled_time_slot_ids_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("open_dates")}
    if "enabled_time_slot_ids_json" in columns:
        op.drop_column("open_dates", "enabled_time_slot_ids_json")
