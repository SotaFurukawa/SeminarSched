"""小学校の中学受験科目と高校数学区分を追加する。

Revision ID: 20260822_0009
Revises: 20260818_0008
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0009"
down_revision: str | None = "20260818_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADED_SUBJECTS = (
    ("ES_ENG", "小学校・英語", "elementary", 1),
    ("ES_MATH_ENTRANCE", "小学校・算数（中学受験）", "elementary", 2),
    ("ES_MATH", "小学校・算数（中学受験以外なら可能）", "elementary", 3),
    ("ES_JPN_ENTRANCE", "小学校・国語（中学受験）", "elementary", 4),
    ("ES_JPN", "小学校・国語（中学受験以外なら可能）", "elementary", 5),
    ("ES_SCI", "小学校・理科", "elementary", 6),
    ("ES_SOC", "小学校・社会", "elementary", 7),
    ("JH_ENG", "中学校・英語", "junior_high", 8),
    ("JH_MATH", "中学校・数学", "junior_high", 9),
    ("JH_JPN", "中学校・国語", "junior_high", 10),
    ("JH_SCI", "中学校・理科", "junior_high", 11),
    ("JH_SOC", "中学校・社会", "junior_high", 12),
    ("HS_ENG", "高校・英語", "high_school", 13),
    ("HS_MODERN_JPN", "高校・現代文", "high_school", 14),
    ("HS_CLASSICAL_JPN", "高校・古文", "high_school", 15),
    ("HS_MATH_GENERAL", "高校・数学IA", "high_school", 16),
    ("HS_MATH_IIBC", "高校・数学IIBC", "high_school", 17),
    ("HS_MATH_III", "高校・数学III", "high_school", 18),
    ("HS_PHYSICS", "高校・物理", "high_school", 19),
    ("HS_CHEMISTRY", "高校・化学", "high_school", 20),
    ("HS_BIOLOGY", "高校・生物", "high_school", 21),
    ("HS_JAPANESE_HISTORY", "高校・日本史", "high_school", 22),
    ("HS_WORLD_HISTORY", "高校・世界史", "high_school", 23),
    ("HS_GEOGRAPHY", "高校・地理", "high_school", 24),
    ("HS_POLITICS_ECONOMICS", "高校・政治経済", "high_school", 25),
    ("HS_INFORMATICS", "高校・情報", "high_school", 26),
)
_NEW_CODES = ("ES_MATH_ENTRANCE", "ES_JPN_ENTRANCE", "HS_MATH_IIBC")
_LEGACY_SUBJECTS = (
    ("ES_ENG", "小学校・英語", 1),
    ("ES_MATH", "小学校・算数", 2),
    ("ES_JPN", "小学校・国語", 3),
    ("ES_SCI", "小学校・理科", 4),
    ("ES_SOC", "小学校・社会", 5),
    ("JH_ENG", "中学校・英語", 6),
    ("JH_MATH", "中学校・数学", 7),
    ("JH_JPN", "中学校・国語", 8),
    ("JH_SCI", "中学校・理科", 9),
    ("JH_SOC", "中学校・社会", 10),
    ("HS_ENG", "高校・英語", 11),
    ("HS_MODERN_JPN", "高校・現代文", 12),
    ("HS_CLASSICAL_JPN", "高校・古文", 13),
    ("HS_MATH_GENERAL", "高校・数学一般", 14),
    ("HS_MATH_III", "高校・数学III", 15),
    ("HS_PHYSICS", "高校・物理", 16),
    ("HS_CHEMISTRY", "高校・化学", 17),
    ("HS_BIOLOGY", "高校・生物", 18),
    ("HS_JAPANESE_HISTORY", "高校・日本史", 19),
    ("HS_WORLD_HISTORY", "高校・世界史", 20),
    ("HS_GEOGRAPHY", "高校・地理", 21),
    ("HS_POLITICS_ECONOMICS", "高校・政治経済", 22),
    ("HS_INFORMATICS", "高校・情報", 23),
)


def upgrade() -> None:
    connection = op.get_bind()
    has_default_subjects = connection.execute(
        sa.text("SELECT 1 FROM subjects WHERE code = 'ES_MATH' LIMIT 1")
    ).scalar_one_or_none()
    if has_default_subjects is None:
        return

    for code, display_name, school_level, sort_order in _UPGRADED_SUBJECTS:
        if code in _NEW_CODES:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO subjects
                        (code, display_name, school_level, sort_order, active)
                    SELECT :code, :display_name, :school_level, :sort_order, 1
                    WHERE NOT EXISTS (SELECT 1 FROM subjects WHERE code = :code)
                    """
                ),
                {
                    "code": code,
                    "display_name": display_name,
                    "school_level": school_level,
                    "sort_order": sort_order,
                },
            )
        else:
            connection.execute(
                sa.text(
                    """
                    UPDATE subjects
                    SET display_name = :display_name,
                        school_level = :school_level,
                        sort_order = :sort_order
                    WHERE code = :code
                    """
                ),
                {
                    "code": code,
                    "display_name": display_name,
                    "school_level": school_level,
                    "sort_order": sort_order,
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    for code in _NEW_CODES:
        connection.execute(
            sa.text(
                """
                DELETE FROM subjects
                WHERE code = :code
                  AND NOT EXISTS (
                    SELECT 1 FROM teacher_qualifications WHERE subject_id = subjects.id
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM lesson_requests WHERE subject_id = subjects.id
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM group_lessons WHERE subject_id = subjects.id
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM regular_lesson_profiles WHERE subject_id = subjects.id
                  )
                """
            ),
            {"code": code},
        )
        connection.execute(
            sa.text("UPDATE subjects SET active = 0 WHERE code = :code"),
            {"code": code},
        )

    for code, display_name, sort_order in _LEGACY_SUBJECTS:
        connection.execute(
            sa.text(
                """
                UPDATE subjects
                SET display_name = :display_name, sort_order = :sort_order
                WHERE code = :code
                """
            ),
            {"code": code, "display_name": display_name, "sort_order": sort_order},
        )
