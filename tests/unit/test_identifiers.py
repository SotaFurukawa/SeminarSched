from summer_scheduler.domain.identifiers import next_person_external_id


def test_person_ids_use_hyphenated_four_digit_sequence() -> None:
    assert next_person_external_id((), prefix="S") == "S-0001"
    assert next_person_external_id(("T-0001", "T0002", "職員A"), prefix="T") == "T-0003"


def test_person_ids_fill_the_first_unused_number_without_visual_collision() -> None:
    assert next_person_external_id(("S-0001", "S-0003", "S0004"), prefix="S") == "S-0002"
