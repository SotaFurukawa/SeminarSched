"""帳票の狭いセルで使う個人名表示規則。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Protocol


class NamedPerson(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def name(self) -> str: ...


def compact_person_name_map(people: Iterable[NamedPerson]) -> dict[int, str]:
    """姓が一意なら姓のみ、同姓なら姓＋名の先頭1文字を空白なしで返す。"""
    rows = tuple(people)
    normalized = {row.id: _normalize_name(row.name) for row in rows}
    family_names = {identifier: _family_name(name) for identifier, name in normalized.items()}
    counts = Counter(family_names.values())
    return {
        identifier: (
            _family_and_given_initial(name)
            if counts[family_names[identifier]] > 1
            else family_names[identifier]
        )
        for identifier, name in normalized.items()
    }


def _normalize_name(value: str) -> str:
    return " ".join(value.split()) or value.strip()


def _family_name(value: str) -> str:
    parts = value.split(maxsplit=1)
    return parts[0] if parts else value


def _family_and_given_initial(value: str) -> str:
    parts = value.split(maxsplit=1)
    if len(parts) < 2 or not parts[1]:
        return value.replace(" ", "")
    return f"{parts[0]}{parts[1][0]}"


__all__ = ["compact_person_name_map"]
