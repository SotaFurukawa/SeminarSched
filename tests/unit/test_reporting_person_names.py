from __future__ import annotations

from dataclasses import dataclass

from summer_scheduler.reporting.person_names import compact_person_name_map


@dataclass(frozen=True)
class Person:
    id: int
    name: str


def test_unique_family_names_are_compact() -> None:
    names = compact_person_name_map(
        (Person(1, "山田 太郎"), Person(2, "佐藤 花子")),
    )

    assert names == {1: "山田", 2: "佐藤"}


def test_duplicate_family_names_use_full_names() -> None:
    names = compact_person_name_map(
        (Person(1, "山田 太郎"), Person(2, "山田 花子"), Person(3, "佐藤 次郎")),
    )

    assert names == {1: "山田 太郎", 2: "山田 花子", 3: "佐藤"}


def test_ideographic_spaces_are_normalized_and_unsplittable_names_remain() -> None:
    names = compact_person_name_map(
        (Person(1, "山田　太郎"), Person(2, "単名")),
    )

    assert names == {1: "山田", 2: "単名"}
