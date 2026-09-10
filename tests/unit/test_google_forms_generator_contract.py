from __future__ import annotations

import re
from pathlib import Path

from summer_scheduler.domain.defaults import DEFAULT_SUBJECTS

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "google_forms"
    / "create_student_questionnaire.gs"
)
TEACHER_SCRIPT = SCRIPT.with_name("create_teacher_questionnaire.gs")
TEACHER_SUBJECT_SCRIPT = SCRIPT.with_name("create_teacher_subject_questionnaire.gs")


def test_google_form_generator_uses_application_subject_names() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for subject in DEFAULT_SUBJECTS:
        assert source.count(f'"{subject.display_name}"') == 1
    assert "高校・日本史" in source
    assert "高校・世界史" in source
    assert "高校・地理" in source
    assert "高校・政治経済" in source


def test_google_form_generator_has_stable_response_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "setCollectEmail(true)" in source
    assert 'setTitle("個人情報の利用目的への同意（必須）")' in source
    assert 'setTitle("姓（苗字）（必須）")' in source
    assert 'setTitle("名（必須）")' in source
    assert 'setTitle("学年（必須）")' in source
    assert 'setTitle("在籍区分（必須）")' in source
    assert "for (let index = 1; index <= 4; index += 1)" in source
    assert "学校区分（${index}教科目）" in source
    assert "受講教科（${schoolLabel}${index}教科目）" in source
    assert "受講回数（${schoolLabel}${index}教科目）" in source
    assert (
        source.count(
            '.setTitle("中高一貫などで他学年の授業を受講される際はこちらにチェックを入れてください")'
        )
        == 1
    )
    assert "他学年の内容も受講しますか（必須）" not in source
    assert source.count(".addPageBreakItem()") == 6
    assert ".addCheckboxGridItem()" in source
    assert 'setTitle("受講不可日時（チェックしたコマは受講不可）")' in source
    assert "FormApp.DestinationType.SPREADSHEET" in source


def test_google_form_generator_routes_grade_to_school_specific_subjects() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "subjectsBySchoolLevel" in source
    assert 'schoolLevels: ["小学校", "中学校", "高校"]' in source
    assert "studentSubjectChoices" in source
    assert 'setTitle("受講教科・回数（小学校）")' in source
    assert 'setTitle("受講教科・回数（中学校）")' in source
    assert 'setTitle("受講教科・回数（高校）")' in source
    assert 'setTitle("受講教科・回数（他学年を含む）")' in source
    assert "gradeItem.createChoice(grade, elementaryPage)" in source
    assert "gradeItem.createChoice(grade, juniorHighPage)" in source
    assert "gradeItem.createChoice(grade, highSchoolPage)" in source
    assert 'otherGradeItem.createChoice("他学年の授業を受講する", otherGradePage)' in source
    assert "juniorHighPage.setGoToPage(availabilityPage)" in source
    assert "elementaryPage.setGoToPage(availabilityPage)" not in source
    assert "addSubjectRequestSection_(form, QUESTIONNAIRE_CONFIG.studentSubjectChoices);" in source
    assert "automaticSchoolLevel" in source
    assert "function fillAutomaticStudentSchoolLevels_(event)" in source
    assert "headers.indexOf(`学校区分（${index}教科目）`)" in source
    assert ".forSpreadsheet(spreadsheetId)" in source


def test_google_form_generator_can_safely_create_a_replacement() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "function createReplacementStudentQuestionnaire()" in source
    assert "properties.deleteProperty(FORM_ID_PROPERTY)" in source
    assert "properties.deleteProperty(SPREADSHEET_ID_PROPERTY)" in source
    assert "createStudentQuestionnaire();" in source


def test_google_form_generator_defaults_to_four_screenshot_time_slots() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for slot in (
        "Z 15:40～17:00",
        "A 17:10～18:30",
        "B 18:40～20:00",
        "C 20:10～21:30",
    ):
        assert source.count(f'"{slot}"') == 1
    assert len(re.findall(r'"2026-\d{2}-\d{2}"', source)) == 21


def test_teacher_google_form_generator_matches_unavailable_grid_contract() -> None:
    source = TEACHER_SCRIPT.read_text(encoding="utf-8")

    assert "createTeacherQuestionnaire" in source
    assert "setCollectEmail(false)" in source
    assert 'setTitle("個人情報の利用目的への同意（必須）")' in source
    assert 'setTitle("姓（苗字）（必須）")' in source
    assert 'setTitle("名（必須）")' in source
    assert source.count(".addPageBreakItem()") == 1
    assert ".addCheckboxGridItem()" in source
    assert 'setTitle("出勤不可日時（チェックしたコマは出勤不可）")' in source
    assert 'setTitle("出勤不可日時の確認（必須）")' in source
    assert "FormApp.DestinationType.SPREADSHEET" in source
    assert len(re.findall(r'"2026-\d{2}-\d{2}"', source)) == 21


def test_teacher_subject_google_form_generator_uses_all_application_subjects() -> None:
    source = TEACHER_SUBJECT_SCRIPT.read_text(encoding="utf-8")

    for subject in DEFAULT_SUBJECTS:
        assert source.count(f'"{subject.display_name}"') == 1
    assert "function createTeacherSubjectQuestionnaire()" in source
    assert "function createReplacementTeacherSubjectQuestionnaire()" in source
    assert "setCollectEmail(false)" in source
    assert source.count(".addCheckboxItem()") == 1
    assert '"指導可能科目（小学校）"' in source
    assert '"指導可能科目（中学校）"' in source
    assert '"指導可能科目（高校）"' in source
    assert 'setTitle("指導可能科目の確認（必須）")' in source
    assert "現在指導可能な科目はありません" in source
    assert "FormApp.DestinationType.SPREADSHEET" in source
