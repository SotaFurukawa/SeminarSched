"""プロジェクト設定を反映するGoogleフォーム作成キットの統合テスト。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pytest

from summer_scheduler.application.master_data_service import MasterDataService
from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.application.questionnaire_script_service import (
    QuestionnaireScriptService,
)
from summer_scheduler.domain.defaults import DEFAULT_SUBJECTS
from summer_scheduler.infrastructure.db import create_database, upgrade_database


@pytest.fixture
def project_services(tmp_path: Path) -> Iterator[tuple[ProjectService, MasterDataService]]:
    registry = create_database(tmp_path / "registry.db")
    upgrade_database(registry.engine)
    projects = ProjectService(registry, tmp_path / "バックアップ")
    projects.create_project(
        tmp_path / "2026年 夏期講習.jukuschedule",
        title="2026年 夏期講習",
        campus_name="既定校舎",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
    )
    yield projects, MasterDataService(projects)
    projects.close_project()
    registry.dispose()


def test_scripts_use_current_open_dates_slots_and_subjects(
    project_services: tuple[ProjectService, MasterDataService],
    tmp_path: Path,
) -> None:
    projects, master = project_services
    master.set_open_date(date(2026, 8, 2), is_open=False, note="休校")
    first_slot = master.list_time_slots()[0]
    master.save_time_slot(
        record_id=first_slot.id,
        code=first_slot.code,
        display_name=first_slot.display_name,
        start_time=first_slot.start_time,
        end_time=first_slot.end_time,
        sort_order=first_slot.sort_order,
        enabled=False,
    )
    output_parent = tmp_path / "フォーム出力"
    output_parent.mkdir()
    service = QuestionnaireScriptService(
        projects,
        clock=lambda: datetime(2026, 6, 1, 12, 30, 0),
    )

    result = service.export_scripts(
        output_parent,
        student_title="2026夏期講習 個別指導受講申込",
        teacher_title="2026夏期講習 非常勤勤務アンケート",
        deadline="2026年6月25日（木）",
        contact="校舎へお問い合わせください",
    )

    assert result.open_date_count == 2
    assert result.time_slot_count == 4
    assert result.directory.name == "Googleフォーム_2026年 夏期講習_20260601_123000"
    assert result.student_script.is_file()
    assert result.teacher_script.is_file()
    assert result.teacher_subject_script.is_file()
    assert result.instructions.is_file()

    student_source = result.student_script.read_text(encoding="utf-8")
    teacher_source = result.teacher_script.read_text(encoding="utf-8")
    teacher_subject_source = result.teacher_subject_script.read_text(encoding="utf-8")
    student_config = _script_config(student_source)
    teacher_config = _script_config(teacher_source)
    teacher_subject_config = _script_config(teacher_subject_source)

    assert student_config["openDates"] == ["2026-08-01", "2026-08-03"]
    assert teacher_config["openDates"] == student_config["openDates"]
    assert student_config["timeSlots"] == [
        "Z 15:40～17:00",
        "A 17:10～18:30",
        "B 18:40～20:00",
        "C 20:10～21:30",
    ]
    assert teacher_config["timeSlots"] == student_config["timeSlots"]
    subject_groups = cast(dict[str, list[str]], student_config["subjectsBySchoolLevel"])
    generated_subjects = [
        *subject_groups["elementary"],
        *subject_groups["juniorHigh"],
        *subject_groups["highSchool"],
    ]
    assert "日本史" in generated_subjects
    assert "高校・日本史" not in generated_subjects
    assert "算数（中学受験以外）" in generated_subjects
    assert "算数（中学受験以外なら可能）" not in generated_subjects
    cross_level_subjects = cast(list[str], student_config["crossLevelSubjects"])
    assert "日本史(高)" in cross_level_subjects
    assert "理科(中)" in cross_level_subjects
    teacher_subject_groups = cast(
        dict[str, list[str]], teacher_subject_config["subjectsBySchoolLevel"]
    )
    assert [
        *teacher_subject_groups["elementary"],
        *teacher_subject_groups["juniorHigh"],
        *teacher_subject_groups["highSchool"],
    ] == [subject.display_name for subject in DEFAULT_SUBJECTS]
    assert "function createStudentQuestionnaire()" in student_source
    assert 'item.createChoice("受講する", crossLevelPage)' in student_source
    assert "crossLevelPage.setGoToPage(availabilityPage)" in student_source
    assert "function createReplacementStudentQuestionnaire()" in student_source
    assert "function createTeacherQuestionnaire()" in teacher_source
    assert "function createReplacementTeacherQuestionnaire()" in teacher_source
    assert "function createTeacherSubjectQuestionnaire()" in teacher_subject_source
    assert "function createReplacementTeacherSubjectQuestionnaire()" in teacher_subject_source
    assert '"指導可能科目（小学校）"' in teacher_subject_source
    assert '"指導可能科目（中学校）"' in teacher_subject_source
    assert '"指導可能科目（高校）"' in teacher_subject_source
    assert 'setCollectEmail(QUESTIONNAIRE_CONFIG.kind === "student")' in teacher_subject_source
    assert "__CONFIG_JSON__" not in student_source
    assert "__CREATE_FUNCTION__" not in teacher_source
    instructions = result.instructions.read_text(encoding="utf-8")
    assert "Google Apps Scriptの「デプロイ」は不要" in instructions
    assert "create_teacher_subject_questionnaire.gs" in instructions
    assert "createTeacherSubjectQuestionnaire" in instructions
    assert "講師のメールアドレスは収集しません" in instructions
    ordered_steps = (
        "1. アプリの「フォーム作成キットを保存…」",
        "2. 保存後に表示される「保存先を開く」",
        "3. create_student_questionnaire.gsを右クリック",
        "4. https://script.google.com/home",
        "5. メモ帳からコピーしたコードをCode.gsへ貼り付け",
        "6. Ctrl+Sまたはフロッピーディスクのボタンで保存",
        "7. 「承認が必要です」と表示されたら「権限を確認」",
        "8. 「このアプリはGoogleで確認されていません」",
        "9. 権限画面で「すべて選択」",
        "10. 実行ログの回答URLからアンケートを開きます",
    )
    positions = [instructions.index(step) for step in ordered_steps]
    assert positions == sorted(positions)


def test_export_uses_a_new_directory_instead_of_overwriting(
    project_services: tuple[ProjectService, MasterDataService],
    tmp_path: Path,
) -> None:
    projects, _master = project_services
    output_parent = tmp_path / "フォーム出力"
    output_parent.mkdir()
    service = QuestionnaireScriptService(
        projects,
        clock=lambda: datetime(2026, 6, 1, 12, 30, 0),
    )
    arguments = {
        "student_title": "生徒フォーム",
        "teacher_title": "講師フォーム",
        "deadline": "6月25日",
        "contact": "担当者",
    }

    first = service.export_scripts(output_parent, **arguments)
    second = service.export_scripts(output_parent, **arguments)

    assert first.directory != second.directory
    assert second.directory.name.endswith("_2")
    assert first.student_script.read_text(encoding="utf-8") == second.student_script.read_text(
        encoding="utf-8"
    )
    assert first.teacher_subject_script.read_text(
        encoding="utf-8"
    ) == second.teacher_subject_script.read_text(encoding="utf-8")


def test_export_requires_open_dates_and_required_form_settings(
    project_services: tuple[ProjectService, MasterDataService],
    tmp_path: Path,
) -> None:
    projects, master = project_services
    output_parent = tmp_path / "フォーム出力"
    output_parent.mkdir()
    service = QuestionnaireScriptService(projects)

    with pytest.raises(ValueError, match="生徒用フォーム名"):
        service.export_scripts(
            output_parent,
            student_title="",
            teacher_title="講師",
            deadline="6月25日",
            contact="担当者",
        )

    master.set_open_dates_state(
        (date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)),
        is_open=False,
    )
    with pytest.raises(ValueError, match="開校日がありません"):
        service.export_scripts(
            output_parent,
            student_title="生徒",
            teacher_title="講師",
            deadline="6月25日",
            contact="担当者",
        )
    assert list(output_parent.iterdir()) == []


def _script_config(source: str) -> dict[str, object]:
    prefix = "const QUESTIONNAIRE_CONFIG = Object.freeze("
    start = source.index(prefix) + len(prefix)
    end = source.index(");\nconst FORM_ID_PROPERTY", start)
    parsed = json.loads(source[start:end])
    assert isinstance(parsed, dict)
    return parsed
