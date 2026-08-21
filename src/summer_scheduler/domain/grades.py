"""学年表記の業務上の正規化とExcel表示変換。"""

from __future__ import annotations

import re
from typing import Final

INTERNAL_GRADE_OPTIONS: Final = (
    *(f"小{year}" for year in range(1, 7)),
    *(f"中{year}" for year in range(1, 4)),
    *(f"高{year}" for year in range(1, 4)),
)
EXCEL_GRADE_OPTIONS: Final = (
    *(f"S{year}" for year in range(1, 7)),
    *(f"J{year}" for year in range(1, 4)),
    *(f"H{year}" for year in range(1, 4)),
)

_INTERNAL_TO_EXCEL: Final = {
    **{f"小{year}": f"S{year}" for year in range(1, 7)},
    **{f"中{year}": f"J{year}" for year in range(1, 4)},
    **{f"高{year}": f"H{year}" for year in range(1, 4)},
}
_EXCEL_TO_INTERNAL: Final = {value: key for key, value in _INTERNAL_TO_EXCEL.items()}
_GRADE_IN_TEXT: Final = re.compile(
    r"(?P<japanese>(?:小学校|小学|小)[1-6](?:年生|年)?|"
    r"(?:中学校|中学|中)[1-3](?:年生|年)?|"
    r"(?:高等学校|高校|高)[1-3](?:年生|年)?)|"
    r"(?P<code>(?<![A-Za-z0-9])[SJHsjh][1-6](?![A-Za-z0-9]))"
)


def grade_from_excel(value: str) -> str:
    """ExcelのS/J/H表記または従来の日本語表記を内部の短縮表記へ変換する。"""
    stripped = value.strip()
    code = stripped.upper()
    if code in _EXCEL_TO_INTERNAL:
        return _EXCEL_TO_INTERNAL[code]

    normalized = (
        stripped.replace("高等学校", "高")
        .replace("小学校", "小")
        .replace("中学校", "中")
        .replace("高校", "高")
        .replace("小学", "小")
        .replace("中学", "中")
        .replace("年生", "")
        .replace("年", "")
    )
    return normalized if normalized in _INTERNAL_TO_EXCEL else stripped


def grade_to_excel(value: str) -> str:
    """内部または従来表記の学年をExcel用のS/J/H表記へ変換する。"""
    normalized = grade_from_excel(value)
    return _INTERNAL_TO_EXCEL.get(normalized, value.strip())


def excelize_grades_in_text(value: str) -> str:
    """Excel帳票内の文章に含まれる既知の学年表記だけをS/J/H表記へ変換する。"""

    def replace(match: re.Match[str]) -> str:
        return grade_to_excel(match.group(0))

    return _GRADE_IN_TEXT.sub(replace, value)
