"""利用者に入力させない外部人物IDの採番規則。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

PersonIdPrefix = Literal["S", "T"]
_MAX_PERSON_NUMBER = 9_999


def next_person_external_id(
    existing_ids: Iterable[str],
    *,
    prefix: PersonIdPrefix,
) -> str:
    """既存IDと人が見て紛らわしくない、最小の4桁連番を返す。"""
    pattern = re.compile(rf"^{prefix}-?(\d+)$", re.IGNORECASE)
    used_numbers = {
        int(match.group(1))
        for value in existing_ids
        if (match := pattern.fullmatch(value.strip())) is not None
    }
    for number in range(1, _MAX_PERSON_NUMBER + 1):
        if number not in used_numbers:
            return f"{prefix}-{number:04d}"
    raise ValueError(f"{prefix}-0001～{prefix}-9999のIDをすべて使用しています")


__all__ = ["PersonIdPrefix", "next_person_external_id"]
