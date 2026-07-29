"""Phase 2で新規プロジェクトへ登録する既定マスター。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Final


@dataclass(frozen=True, slots=True)
class DefaultTimeSlot:
    """既定コマの不変データ。"""

    code: str
    display_name: str
    start_time: time
    end_time: time
    sort_order: int


@dataclass(frozen=True, slots=True)
class DefaultSubject:
    """既定科目の不変データ。"""

    code: str
    display_name: str
    school_level: str
    sort_order: int


DEFAULT_TIME_SLOTS: Final = (
    DefaultTimeSlot("Y", "Y", time(14, 10), time(15, 30), 1),
    DefaultTimeSlot("Z", "Z", time(15, 40), time(17, 0), 2),
    DefaultTimeSlot("A", "A", time(17, 10), time(18, 30), 3),
    DefaultTimeSlot("B", "B", time(18, 40), time(20, 0), 4),
    DefaultTimeSlot("C", "C", time(20, 10), time(21, 30), 5),
)

DEFAULT_SUBJECTS: Final = (
    DefaultSubject("ES_ENG", "小学校・英語", "elementary", 1),
    DefaultSubject("ES_MATH", "小学校・算数", "elementary", 2),
    DefaultSubject("ES_JPN", "小学校・国語", "elementary", 3),
    DefaultSubject("ES_SCI", "小学校・理科", "elementary", 4),
    DefaultSubject("ES_SOC", "小学校・社会", "elementary", 5),
    DefaultSubject("JH_ENG", "中学校・英語", "junior_high", 6),
    DefaultSubject("JH_MATH", "中学校・数学", "junior_high", 7),
    DefaultSubject("JH_JPN", "中学校・国語", "junior_high", 8),
    DefaultSubject("JH_SCI", "中学校・理科", "junior_high", 9),
    DefaultSubject("JH_SOC", "中学校・社会", "junior_high", 10),
    DefaultSubject("HS_ENG", "高校・英語", "high_school", 11),
    DefaultSubject("HS_MODERN_JPN", "高校・現代文", "high_school", 12),
    DefaultSubject("HS_CLASSICAL_JPN", "高校・古文", "high_school", 13),
    DefaultSubject("HS_MATH_GENERAL", "高校・数学一般", "high_school", 14),
    DefaultSubject("HS_MATH_III", "高校・数学III", "high_school", 15),
    DefaultSubject("HS_PHYSICS", "高校・物理", "high_school", 16),
    DefaultSubject("HS_CHEMISTRY", "高校・化学", "high_school", 17),
    DefaultSubject("HS_BIOLOGY", "高校・生物", "high_school", 18),
    DefaultSubject("HS_JAPANESE_HISTORY", "高校・日本史", "high_school", 19),
    DefaultSubject("HS_WORLD_HISTORY", "高校・世界史", "high_school", 20),
    DefaultSubject("HS_GEOGRAPHY", "高校・地理", "high_school", 21),
    DefaultSubject("HS_POLITICS_ECONOMICS", "高校・政治経済", "high_school", 22),
    DefaultSubject("HS_INFORMATICS", "高校・情報", "high_school", 23),
)

SCHOOL_LEVEL_LABELS: Final = {
    "elementary": "小学校",
    "junior_high": "中学校",
    "high_school": "高校",
}
