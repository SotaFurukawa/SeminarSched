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

    @property
    def short_name(self) -> str:
        return default_subject_short_name(self.code, self.display_name)


_SUBJECT_SHORT_NAMES: Final = {
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


def default_subject_short_name(code: str, display_name: str) -> str:
    """Return the one-character timetable label for a subject."""
    configured = _SUBJECT_SHORT_NAMES.get(code.strip().upper())
    if configured:
        return configured
    compact_name = display_name.strip().replace("・", "")
    return compact_name[-1:] or code.strip()[:1] or "科"


DEFAULT_TIME_SLOTS: Final = (
    DefaultTimeSlot("Y", "Y", time(14, 10), time(15, 30), 1),
    DefaultTimeSlot("Z", "Z", time(15, 40), time(17, 0), 2),
    DefaultTimeSlot("A", "A", time(17, 10), time(18, 30), 3),
    DefaultTimeSlot("B", "B", time(18, 40), time(20, 0), 4),
    DefaultTimeSlot("C", "C", time(20, 10), time(21, 30), 5),
)

DEFAULT_SUBJECTS: Final = (
    DefaultSubject("ES_ENG", "小学校・英語", "elementary", 1),
    DefaultSubject("ES_MATH_ENTRANCE", "小学校・算数（中学受験）", "elementary", 2),
    DefaultSubject("ES_MATH", "小学校・算数（中学受験以外なら可能）", "elementary", 3),
    DefaultSubject("ES_JPN_ENTRANCE", "小学校・国語（中学受験）", "elementary", 4),
    DefaultSubject("ES_JPN", "小学校・国語（中学受験以外なら可能）", "elementary", 5),
    DefaultSubject("ES_SCI", "小学校・理科", "elementary", 6),
    DefaultSubject("ES_SOC", "小学校・社会", "elementary", 7),
    DefaultSubject("JH_ENG", "中学校・英語", "junior_high", 8),
    DefaultSubject("JH_MATH", "中学校・数学", "junior_high", 9),
    DefaultSubject("JH_JPN", "中学校・国語", "junior_high", 10),
    DefaultSubject("JH_SCI", "中学校・理科", "junior_high", 11),
    DefaultSubject("JH_SOC", "中学校・社会", "junior_high", 12),
    DefaultSubject("HS_ENG", "高校・英語", "high_school", 13),
    DefaultSubject("HS_MODERN_JPN", "高校・現代文", "high_school", 14),
    DefaultSubject("HS_CLASSICAL_JPN", "高校・古文", "high_school", 15),
    DefaultSubject("HS_MATH_GENERAL", "高校・数学IA", "high_school", 16),
    DefaultSubject("HS_MATH_IIBC", "高校・数学IIBC", "high_school", 17),
    DefaultSubject("HS_MATH_III", "高校・数学III", "high_school", 18),
    DefaultSubject("HS_PHYSICS", "高校・物理", "high_school", 19),
    DefaultSubject("HS_CHEMISTRY", "高校・化学", "high_school", 20),
    DefaultSubject("HS_BIOLOGY", "高校・生物", "high_school", 21),
    DefaultSubject("HS_JAPANESE_HISTORY", "高校・日本史", "high_school", 22),
    DefaultSubject("HS_WORLD_HISTORY", "高校・世界史", "high_school", 23),
    DefaultSubject("HS_GEOGRAPHY", "高校・地理", "high_school", 24),
    DefaultSubject("HS_POLITICS_ECONOMICS", "高校・政治経済", "high_school", 25),
    DefaultSubject("HS_INFORMATICS", "高校・情報", "high_school", 26),
)

SCHOOL_LEVEL_LABELS: Final = {
    "elementary": "小学校",
    "junior_high": "中学校",
    "high_school": "高校",
}
