"""学年の内部表記とExcel表記の変換テスト。"""

from summer_scheduler.domain.grades import (
    EXCEL_GRADE_OPTIONS,
    excelize_grades_in_text,
    grade_from_excel,
    grade_to_excel,
)


def test_excel_grade_options_use_school_level_prefixes() -> None:
    assert EXCEL_GRADE_OPTIONS == (
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "J1",
        "J2",
        "J3",
        "H1",
        "H2",
        "H3",
    )


def test_grade_conversion_accepts_new_and_legacy_notation() -> None:
    assert grade_from_excel("S6") == "小6"
    assert grade_from_excel("j2") == "中2"
    assert grade_from_excel("H2") == "高2"
    assert grade_from_excel("小学3年") == "小3"
    assert grade_from_excel("中学校1年") == "中1"
    assert grade_from_excel("高校3年生") == "高3"
    assert grade_to_excel("小学校2年") == "S2"
    assert grade_to_excel("中3") == "J3"
    assert grade_to_excel("高2") == "H2"


def test_unknown_grades_are_preserved_instead_of_silently_reclassified() -> None:
    assert grade_from_excel("既卒") == "既卒"
    assert grade_to_excel("H6") == "H6"


def test_excel_report_text_replaces_only_grade_notation() -> None:
    assert excelize_grades_in_text("山田 花子（高校2年）／高校・英語") == (
        "山田 花子（H2）／高校・英語"
    )
