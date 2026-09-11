"""Add the one-character subject label used by timetable exports.

Revision ID: 20260912_0011
Revises: 20260904_0010
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260912_0011"
down_revision: str | None = "20260904_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_KNOWN_SHORT_NAMES = {
    "ES_ENG": "英",
    "ES_MATH_ENTRANCE": "算",
    "ES_MATH": "算",
    "ES_JPN_ENTRANCE": "国",
    "ES_JPN": "国",
    "ES_SCI": "理",
    "ES_SOC": "社",
    "JH_ENG": "英",
    "JH_MATH": "数",
    "JH_JPN": "国",
    "JH_SCI": "理",
    "JH_SOC": "社",
    "HS_ENG": "英",
    "HS_MODERN_JPN": "現",
    "HS_CLASSICAL_JPN": "古",
    "HS_MATH_GENERAL": "数",
    "HS_MATH_IIBC": "数",
    "HS_MATH_III": "数",
    "HS_PHYSICS": "物",
    "HS_CHEMISTRY": "化",
    "HS_BIOLOGY": "生",
    "HS_JAPANESE_HISTORY": "日",
    "HS_WORLD_HISTORY": "世",
    "HS_GEOGRAPHY": "地",
    "HS_POLITICS_ECONOMICS": "政",
    "HS_INFORMATICS": "情",
}


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("subjects")}
    if "short_name" in columns:
        return
    op.add_column(
        "subjects",
        sa.Column("short_name", sa.String(length=10), nullable=False, server_default=""),
    )
    connection = op.get_bind()
    for code, short_name in _KNOWN_SHORT_NAMES.items():
        connection.execute(
            sa.text("UPDATE subjects SET short_name = :short_name WHERE code = :code"),
            {"short_name": short_name, "code": code},
        )
    connection.execute(
        sa.text(
            "UPDATE subjects SET short_name = substr(display_name, length(display_name), 1) "
            "WHERE trim(short_name) = ''"
        )
    )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("subjects")}
    if "short_name" in columns:
        op.drop_column("subjects", "short_name")
