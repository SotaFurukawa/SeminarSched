"""プロジェクト設定からGoogleフォーム作成用Apps Scriptを生成する。"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from summer_scheduler.application.project_service import ProjectService
from summer_scheduler.infrastructure.repositories.master_repository import MasterRepository

_SCHOOL_LEVELS = ("elementary", "junior_high", "high_school")
_GRADE_GROUPS = {
    "elementary": ["小1", "小2", "小3", "小4", "小5", "小6"],
    "juniorHigh": ["中1", "中2", "中3"],
    "highSchool": ["高1", "高2", "高3"],
}
_SCHOOL_LEVEL_SUFFIXES = {
    "elementary": "小",
    "junior_high": "中",
    "high_school": "高",
}


@dataclass(frozen=True, slots=True)
class QuestionnaireScriptExportResult:
    """生成したGoogleフォーム作成キット。"""

    directory: Path
    student_script: Path
    teacher_script: Path
    teacher_subject_script: Path
    instructions: Path
    open_date_count: int
    time_slot_count: int


class QuestionnaireScriptService:
    """現在のプロジェクトから、外部通信なしでApps Scriptを生成する。"""

    def __init__(
        self,
        projects: ProjectService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._projects = projects
        self._clock = clock or datetime.now

    def export_scripts(
        self,
        parent_directory: Path,
        *,
        student_title: str,
        teacher_title: str,
        deadline: str,
        contact: str,
    ) -> QuestionnaireScriptExportResult:
        """生徒用・講師用スクリプトと手順書を新しいフォルダーへ保存する。"""
        project = self._projects.require_project()
        parent = parent_directory.expanduser().resolve()
        if not parent.is_dir():
            raise ValueError("Googleフォーム作成キットの保存先フォルダーを選択してください")

        cleaned_student_title = _required_text(student_title, "生徒用フォーム名")
        cleaned_teacher_title = _required_text(teacher_title, "講師用フォーム名")
        cleaned_deadline = _required_text(deadline, "回答締切")
        cleaned_contact = _required_text(contact, "問い合わせ先")

        database = self._projects.require_database()
        with database.session_factory() as session:
            repository = MasterRepository(session)
            open_dates = [
                row.date.isoformat()
                for row in repository.list_open_dates(project_id=project.project_id)
                if row.is_open
            ]
            time_slots = [
                f"{row.display_name} {row.start_time:%H:%M}～{row.end_time:%H:%M}"
                for row in repository.list_time_slots(
                    project_id=project.project_id,
                    enabled_only=True,
                )
            ]
            subjects = repository.list_subjects(active_only=True)

        if not open_dates:
            raise ValueError("開校日がありません。①の「開校日・休校日」で開校日を設定してください")
        if not time_slots:
            raise ValueError("有効なコマがありません。①の「コマ設定」を確認してください")

        subjects_by_level: dict[str, list[str]] = {level: [] for level in _SCHOOL_LEVELS}
        student_subjects_by_level: dict[str, list[str]] = {level: [] for level in _SCHOOL_LEVELS}
        cross_level_subjects: list[str] = []
        for subject in subjects:
            if subject.school_level in subjects_by_level:
                subjects_by_level[subject.school_level].append(subject.display_name)
                short_label = _student_subject_label(subject.display_name)
                student_subjects_by_level[subject.school_level].append(short_label)
                cross_level_subjects.append(
                    f"{short_label}({_SCHOOL_LEVEL_SUFFIXES[subject.school_level]})"
                )
        missing_levels = [level for level, values in subjects_by_level.items() if not values]
        if missing_levels:
            raise ValueError(
                "生徒用フォームに必要な小学校・中学校・高校の使用中科目が不足しています。"
                "①の「科目」を確認してください"
            )

        student_config: dict[str, object] = {
            "kind": "student",
            "title": cleaned_student_title,
            "deadline": cleaned_deadline,
            "contact": cleaned_contact,
            "description": (
                "個別指導コースの受講申込フォームです。メールアドレス、お子様の"
                "お名前、学年、受講教科・回数、受講できない日時をご回答ください。\n\n"
                "回答は講習の受付、時間割作成、内容確認、必要な連絡にだけ使用します。"
                "回答先スプレッドシートの閲覧者は担当者に限定してください。"
            ),
            "openDates": open_dates,
            "timeSlots": time_slots,
            "gradeGroups": _GRADE_GROUPS,
            "enrollmentTypes": ["在籍生", "体験生"],
            "subjectsBySchoolLevel": {
                "elementary": student_subjects_by_level["elementary"],
                "juniorHigh": student_subjects_by_level["junior_high"],
                "highSchool": student_subjects_by_level["high_school"],
            },
            "crossLevelSubjects": cross_level_subjects,
            "sessionCounts": [str(value) for value in range(1, 21)],
            "summerTestChoices": [
                "夏期学力テストを受験する",
                "夏期学力テストを受験しない",
                "対象外（小1～小3・高校生）",
            ],
        }
        teacher_config: dict[str, object] = {
            "kind": "teacher",
            "title": cleaned_teacher_title,
            "deadline": cleaned_deadline,
            "contact": cleaned_contact,
            "description": (
                "講習の出勤可能日時を確認するフォームです。出勤できない日時にだけ"
                "チェックを入れてください。\n\n回答は勤務希望の確認、時間割作成、"
                "内容確認、必要な連絡にだけ使用します。回答先スプレッドシートの"
                "閲覧者は担当者に限定してください。"
            ),
            "openDates": open_dates,
            "timeSlots": time_slots,
        }
        teacher_subject_config: dict[str, object] = {
            "kind": "teacher_subject",
            "title": f"{project.title} 講師 指導可能科目アンケート",
            "deadline": cleaned_deadline,
            "contact": cleaned_contact,
            "description": (
                "現在、講師本人が単独で授業を進められる指導可能科目を確認する"
                "フォームです。小学校・中学校・高校から、該当する科目をすべて"
                "選択してください。\n\n回答は講師マスターの更新、担当可能科目の確認、"
                "時間割作成にだけ使用します。回答先スプレッドシートの閲覧者は"
                "担当者に限定してください。"
            ),
            "subjectsBySchoolLevel": {
                "elementary": subjects_by_level["elementary"],
                "juniorHigh": subjects_by_level["junior_high"],
                "highSchool": subjects_by_level["high_school"],
            },
        }

        timestamp = self._clock().strftime("%Y%m%d_%H%M%S")
        base_name = f"Googleフォーム_{_safe_filename(project.title)}_{timestamp}"
        destination = _available_directory(parent, base_name)
        temporary = Path(tempfile.mkdtemp(prefix=".google-forms-", dir=parent))
        try:
            student_path = temporary / "create_student_questionnaire.gs"
            teacher_path = temporary / "create_teacher_questionnaire.gs"
            teacher_subject_path = temporary / "create_teacher_subject_questionnaire.gs"
            instructions_path = temporary / "Googleフォーム作成手順.txt"
            student_path.write_text(
                _render_script(student_config, kind="student"),
                encoding="utf-8",
                newline="\n",
            )
            teacher_path.write_text(
                _render_script(teacher_config, kind="teacher"),
                encoding="utf-8",
                newline="\n",
            )
            teacher_subject_path.write_text(
                _render_script(teacher_subject_config, kind="teacher_subject"),
                encoding="utf-8",
                newline="\n",
            )
            instructions_path.write_text(
                _instructions(project.title, len(open_dates), len(time_slots)),
                encoding="utf-8",
                newline="\n",
            )
            temporary.replace(destination)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

        return QuestionnaireScriptExportResult(
            directory=destination,
            student_script=destination / "create_student_questionnaire.gs",
            teacher_script=destination / "create_teacher_questionnaire.gs",
            teacher_subject_script=destination / "create_teacher_subject_questionnaire.gs",
            instructions=destination / "Googleフォーム作成手順.txt",
            open_date_count=len(open_dates),
            time_slot_count=len(time_slots),
        )


def _required_text(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label}を入力してください")
    return cleaned


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    cleaned = cleaned.rstrip(". ")[:60]
    return cleaned or "講習"


def _student_subject_label(display_name: str) -> str:
    """生徒フォームでは学校段階の接頭辞を省き、説明を簡潔にする。"""
    label = display_name
    for prefix in ("小学校・", "中学校・", "高校・"):
        if label.startswith(prefix):
            label = label.removeprefix(prefix)
            break
    return label.replace("（中学受験以外なら可能）", "（中学受験以外）")


def _available_directory(parent: Path, base_name: str) -> Path:
    candidate = parent / base_name
    suffix = 2
    while candidate.exists():
        candidate = parent / f"{base_name}_{suffix}"
        suffix += 1
    return candidate


def _render_script(config: dict[str, object], *, kind: str) -> str:
    if kind == "student":
        replacements = {
            "__FORM_ID_PROPERTY__": "SUMMER_SCHEDULER_STUDENT_FORM_ID",
            "__SHEET_ID_PROPERTY__": "SUMMER_SCHEDULER_STUDENT_RESPONSE_SHEET_ID",
            "__CREATE_FUNCTION__": "createStudentQuestionnaire",
            "__SHOW_FUNCTION__": "showCreatedQuestionnaireUrls",
            "__REPLACEMENT_FUNCTION__": "createReplacementStudentQuestionnaire",
            "__KIND_LABEL__": "生徒・保護者用",
        }
    elif kind == "teacher":
        replacements = {
            "__FORM_ID_PROPERTY__": "SUMMER_SCHEDULER_TEACHER_FORM_ID",
            "__SHEET_ID_PROPERTY__": "SUMMER_SCHEDULER_TEACHER_RESPONSE_SHEET_ID",
            "__CREATE_FUNCTION__": "createTeacherQuestionnaire",
            "__SHOW_FUNCTION__": "showCreatedTeacherQuestionnaireUrls",
            "__REPLACEMENT_FUNCTION__": "createReplacementTeacherQuestionnaire",
            "__KIND_LABEL__": "講師用",
        }
    elif kind == "teacher_subject":
        replacements = {
            "__FORM_ID_PROPERTY__": "SUMMER_SCHEDULER_TEACHER_SUBJECT_FORM_ID",
            "__SHEET_ID_PROPERTY__": "SUMMER_SCHEDULER_TEACHER_SUBJECT_RESPONSE_SHEET_ID",
            "__CREATE_FUNCTION__": "createTeacherSubjectQuestionnaire",
            "__SHOW_FUNCTION__": "showCreatedTeacherSubjectQuestionnaireUrls",
            "__REPLACEMENT_FUNCTION__": "createReplacementTeacherSubjectQuestionnaire",
            "__KIND_LABEL__": "講師指導可能科目用",
        }
    else:
        raise ValueError("Googleフォームの種類が不正です")

    script = _QUESTIONNAIRE_SCRIPT_TEMPLATE.replace(
        "__CONFIG_JSON__",
        json.dumps(config, ensure_ascii=False, indent=2),
    )
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    return script.rstrip() + "\n"


def _instructions(project_title: str, open_date_count: int, time_slot_count: int) -> str:
    return f"""{project_title} Googleフォーム作成手順

このフォルダーには、①で設定した開校日{open_date_count}日・有効コマ{time_slot_count}件を
反映した生徒用／講師勤務日時用／講師指導可能科目用Google Apps Scriptが入っています。

【生徒用：上から順に進めます】
1. アプリの「フォーム作成キットを保存…」から作成キットを保存します。
2. 保存後に表示される「保存先を開く」を押します。
3. create_student_questionnaire.gsを右クリックし、「プログラムから開く」から
   「メモ帳」を選び、表示されたコードを先頭から最後までコピーします。
4. https://script.google.com/home を開き、「新しいプロジェクト」を作ります。
   Code.gsに最初から入っているコードはすべて削除します。
5. メモ帳からコピーしたコードをCode.gsへ貼り付けます。
6. Ctrl+Sまたはフロッピーディスクのボタンで保存し、関数が
   createStudentQuestionnaireであることを確認して「実行」を押します。
7. 「承認が必要です」と表示されたら「権限を確認」を押します。
8. 「このアプリはGoogleで確認されていません」と表示された場合は「詳細」を押し、
   「無題のプロジェクト（安全ではないページ）に移動」を押します。
9. 権限画面で「すべて選択」にチェックを入れ、内容を確認して「続行」を押します。
10. 実行ログの回答URLからアンケートを開きます。フォーム編集URLと回答原本URLは
    担当者だけで管理し、回答URLだけを生徒へ案内します。

【講師用・講師指導可能科目用】
上記と同じ1～10の手順を、別々のApps Scriptプロジェクトで繰り返します。
- 講師勤務日時用：create_teacher_questionnaire.gs／createTeacherQuestionnaire
- 講師指導可能科目用：create_teacher_subject_questionnaire.gs／
  createTeacherSubjectQuestionnaire
講師指導可能科目用は、完成後に26科目と説明文を確認します。
講師のメールアドレスは収集しません。

Google Apps Scriptの「デプロイ」は不要です。配布前に、タイトル、締切、質問、開校日、
コマ、回答先スプレッドシートの共有範囲を必ず確認してください。

生徒・講師勤務日時の回答後はGoogleスプレッドシートからxlsxまたはCSVをダウンロードし、
アプリの③「回答取込み」で生徒回答／講師回答を選んで検証・反映します。
指導可能科目の回答は回答原本で確認し、ホームの「生徒・講師_基本情報.xlsx」の
「講師対応科目」へ、校舎側で内容を確認して反映してください。

このスクリプトはフォーム作成時だけGoogleへアクセスします。アプリ本体はGoogleへ接続せず、
回答や個人情報を外部へ送信しません。
"""


_QUESTIONNAIRE_SCRIPT_TEMPLATE = r"""/**
 * SummerCourseSchedulerが生成した__KIND_LABEL__Googleフォーム作成スクリプト。
 * Google Apps ScriptのCode.gsへ全内容を貼り付けて使用します。
 */

const QUESTIONNAIRE_CONFIG = Object.freeze(__CONFIG_JSON__);
const FORM_ID_PROPERTY = "__FORM_ID_PROPERTY__";
const SPREADSHEET_ID_PROPERTY = "__SHEET_ID_PROPERTY__";

/** フォームと回答先スプレッドシートを1組だけ作成する。 */
function __CREATE_FUNCTION__() {
  validateQuestionnaireConfig_();
  const properties = PropertiesService.getScriptProperties();
  const existingFormId = properties.getProperty(FORM_ID_PROPERTY);
  if (existingFormId) {
    try {
      const existingForm = FormApp.openById(existingFormId);
      logQuestionnaireUrls_(
        existingForm,
        properties.getProperty(SPREADSHEET_ID_PROPERTY),
      );
      throw new Error(
        "このスクリプトではフォームを作成済みです。" +
          "重複作成せず、実行ログのURLから既存フォームを開いてください。",
      );
    } catch (error) {
      if (String(error).includes("フォームを作成済みです")) throw error;
      properties.deleteProperty(FORM_ID_PROPERTY);
      properties.deleteProperty(SPREADSHEET_ID_PROPERTY);
    }
  }

  const form = FormApp.create(QUESTIONNAIRE_CONFIG.title, true)
    .setDescription(
      QUESTIONNAIRE_CONFIG.description +
        `\n\n回答締切: ${QUESTIONNAIRE_CONFIG.deadline}` +
        `\n問い合わせ先: ${QUESTIONNAIRE_CONFIG.contact}`,
    )
    .setCollectEmail(QUESTIONNAIRE_CONFIG.kind === "student")
    .setProgressBar(true)
    .setShowLinkToRespondAgain(false)
    .setAllowResponseEdits(true)
    .setConfirmationMessage(
      "回答を受け付けました。修正が必要な場合は、回答編集リンクを使用するか、" +
        QUESTIONNAIRE_CONFIG.contact + "。",
    );

  form
    .addMultipleChoiceItem()
    .setTitle("個人情報の利用目的への同意（必須）")
    .setHelpText(
      QUESTIONNAIRE_CONFIG.kind === "student"
        ? "回答を講習の受付、時間割作成、内容確認、必要な連絡に使用します。"
        : QUESTIONNAIRE_CONFIG.kind === "teacher_subject"
          ? "回答を講師マスターの更新、担当可能科目の確認、時間割作成に使用します。"
          : "回答を勤務希望の確認、時間割作成、内容確認、必要な連絡に使用します。",
    )
    .setChoiceValues(["上記の利用目的を確認し、回答します"])
    .setRequired(true);
  form
    .addTextItem()
    .setTitle("姓（苗字）（必須）")
    .setHelpText("姓（苗字）をご記入ください。例: 山田")
    .setRequired(true);
  form
    .addTextItem()
    .setTitle("名（必須）")
    .setHelpText("名をご記入ください。例: 太郎")
    .setRequired(true);

  if (QUESTIONNAIRE_CONFIG.kind === "student") {
    addStudentQuestions_(form);
  } else if (QUESTIONNAIRE_CONFIG.kind === "teacher") {
    addTeacherQuestions_(form);
  } else {
    addTeacherSubjectQuestions_(form);
  }

  const spreadsheet = SpreadsheetApp.create(`${QUESTIONNAIRE_CONFIG.title} 回答原本`);
  form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheet.getId());
  properties.setProperty(FORM_ID_PROPERTY, form.getId());
  properties.setProperty(SPREADSHEET_ID_PROPERTY, spreadsheet.getId());
  logQuestionnaireUrls_(form, spreadsheet.getId());
}

function addStudentQuestions_(form) {
  const gradeItem = form.addListItem().setTitle("学年（必須）").setRequired(true);
  form
    .addListItem()
    .setTitle("在籍区分（必須）")
    .setChoiceValues(QUESTIONNAIRE_CONFIG.enrollmentTypes)
    .setRequired(true);

  const elementaryPage = form
    .addPageBreakItem()
    .setTitle("小学生の受講教科・回数")
    .setHelpText("小学校の科目だけが表示されます。最大4教科まで回答できます。");
  addSubjectRequestSection_(
    form,
    "小学校",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.elementary,
  );
  const elementaryCrossLevelItem = form
    .addMultipleChoiceItem()
    .setTitle("他学年の内容も受講しますか（必須）")
    .setRequired(true);
  const juniorHighPage = form
    .addPageBreakItem()
    .setTitle("中学生の受講教科・回数")
    .setHelpText("中学校の科目だけが表示されます。最大4教科まで回答できます。");
  addSubjectRequestSection_(
    form,
    "中学校",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.juniorHigh,
  );
  const juniorHighCrossLevelItem = form
    .addMultipleChoiceItem()
    .setTitle("他学年の内容も受講しますか（必須）")
    .setRequired(true);
  const highSchoolPage = form
    .addPageBreakItem()
    .setTitle("高校生の受講教科・回数")
    .setHelpText("高校の科目だけが表示されます。最大4教科まで回答できます。");
  addSubjectRequestSection_(
    form,
    "高校",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.highSchool,
  );
  const highSchoolCrossLevelItem = form
    .addMultipleChoiceItem()
    .setTitle("他学年の内容も受講しますか（必須）")
    .setRequired(true);
  const crossLevelPage = form
    .addPageBreakItem()
    .setTitle("他学年の受講教科・回数")
    .setHelpText("小・中・高の科目を選択できます。科目名末尾の(小)(中)(高)で内容を区別します。");
  addSubjectRequestSection_(
    form,
    "他学年",
    QUESTIONNAIRE_CONFIG.crossLevelSubjects,
  );
  const availabilityPage = addAvailabilityPage_(form, "受講");
  [elementaryCrossLevelItem, juniorHighCrossLevelItem, highSchoolCrossLevelItem]
    .forEach((item) => item.setChoices([
      item.createChoice("受講しない", availabilityPage),
      item.createChoice("受講する", crossLevelPage),
    ]));
  crossLevelPage.setGoToPage(availabilityPage);
  gradeItem.setChoices([
    ...QUESTIONNAIRE_CONFIG.gradeGroups.elementary.map((grade) =>
      gradeItem.createChoice(grade, elementaryPage),
    ),
    ...QUESTIONNAIRE_CONFIG.gradeGroups.juniorHigh.map((grade) =>
      gradeItem.createChoice(grade, juniorHighPage),
    ),
    ...QUESTIONNAIRE_CONFIG.gradeGroups.highSchool.map((grade) =>
      gradeItem.createChoice(grade, highSchoolPage),
    ),
  ]);
  addAvailabilityGrid_(form, "受講不可日時（チェックしたコマは受講不可）");
  form.addPageBreakItem().setTitle("確認・特記事項");
  form
    .addMultipleChoiceItem()
    .setTitle("受講不可日時の確認（必須）")
    .setHelpText("上でチェックした日時が、受講できない日時で間違いないか確認してください。")
    .setChoiceValues(["間違いありません"])
    .setRequired(true);
  form
    .addParagraphTextItem()
    .setTitle("特記事項")
    .setHelpText("例: 1日に英数連続2コマで組んでほしい、送迎は20時まで、など。")
    .setRequired(false);
  form
    .addMultipleChoiceItem()
    .setTitle("夏期講習学力テスト")
    .setHelpText("個別指導生の夏期学力テストは選択制です（小4～中3対象）。")
    .setChoiceValues(QUESTIONNAIRE_CONFIG.summerTestChoices)
    .setRequired(false);
}

function addTeacherQuestions_(form) {
  addAvailabilityPage_(form, "出勤");
  addAvailabilityGrid_(form, "出勤不可日時（チェックしたコマは出勤不可）");
  form
    .addMultipleChoiceItem()
    .setTitle("出勤不可日時の確認（必須）")
    .setHelpText("上でチェックした日時が、出勤できない日時で間違いないか確認してください。")
    .setChoiceValues(["間違いありません"])
    .setRequired(true);
  form
    .addParagraphTextItem()
    .setTitle("勤務に関する特記事項")
    .setHelpText("連続勤務、到着・退出時刻など、日程について必要な事項をご記入ください。")
    .setRequired(false);
}

function addTeacherSubjectQuestions_(form) {
  form
    .addSectionHeaderItem()
    .setTitle("現在の指導可能科目")
    .setHelpText(
      "教材を使い、講師本人が単独で授業を進められる科目をすべて選択してください。" +
        "未経験、補助が必要、または現在は担当できない科目は選択しないでください。",
    );
  addTeacherSubjectCheckbox_(
    form,
    "指導可能科目（小学校）",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.elementary,
  );
  addTeacherSubjectCheckbox_(
    form,
    "指導可能科目（中学校）",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.juniorHigh,
  );
  addTeacherSubjectCheckbox_(
    form,
    "指導可能科目（高校）",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.highSchool,
  );
  form
    .addMultipleChoiceItem()
    .setTitle("指導可能科目の確認（必須）")
    .setHelpText(
      "選択した科目だけを現在の指導可能科目として回答することを確認してください。" +
        "1科目もない場合は、2つ目を選択してください。",
    )
    .setChoiceValues([
      "上記で選択した科目を現在指導できます",
      "現在指導可能な科目はありません",
    ])
    .setRequired(true);
  form
    .addParagraphTextItem()
    .setTitle("指導可能科目に関する補足")
    .setHelpText(
      "例: 高校数学は数学I・Aのみ、受験指導は要相談、研修後に追加可能、など。",
    )
    .setRequired(false);
}

function addTeacherSubjectCheckbox_(form, title, subjects) {
  form
    .addCheckboxItem()
    .setTitle(title)
    .setChoiceValues(subjects)
    .setRequired(false);
}

function addSubjectRequestSection_(form, schoolLabel, subjects) {
  for (let index = 1; index <= 4; index += 1) {
    const required = index === 1;
    form
      .addListItem()
      .setTitle(`受講教科（${schoolLabel}・${index}教科目）${required ? "（必須）" : ""}`)
      .setChoiceValues(subjects)
      .setRequired(required);
    form
      .addListItem()
      .setTitle(`受講回数（${schoolLabel}・${index}教科目）${required ? "（必須）" : ""}`)
      .setChoiceValues(QUESTIONNAIRE_CONFIG.sessionCounts)
      .setRequired(required);
  }
}

function addAvailabilityPage_(form, actionLabel) {
  return form
    .addPageBreakItem()
    .setTitle(`${actionLabel}できない日時`)
    .setHelpText(
      `チェックした日時は「${actionLabel}不可」として扱います。` +
        `${actionLabel}できる日時にはチェックを入れないでください。`,
    );
}

function addAvailabilityGrid_(form, title) {
  form
    .addCheckboxGridItem()
    .setTitle(title)
    .setRows(QUESTIONNAIRE_CONFIG.openDates.map(formatDateLabel_))
    .setColumns(QUESTIONNAIRE_CONFIG.timeSlots)
    .setRequired(false);
}

/** 作成済みフォームのURLをもう一度表示する。 */
function __SHOW_FUNCTION__() {
  const properties = PropertiesService.getScriptProperties();
  const formId = properties.getProperty(FORM_ID_PROPERTY);
  if (!formId) throw new Error("フォームはまだ作成されていません。");
  logQuestionnaireUrls_(
    FormApp.openById(formId),
    properties.getProperty(SPREADSHEET_ID_PROPERTY),
  );
}

/** 既存フォームを残し、現在のコードで置換用フォームを新規作成する。 */
function __REPLACEMENT_FUNCTION__() {
  const properties = PropertiesService.getScriptProperties();
  properties.deleteProperty(FORM_ID_PROPERTY);
  properties.deleteProperty(SPREADSHEET_ID_PROPERTY);
  __CREATE_FUNCTION__();
}

function formatDateLabel_(isoDate) {
  const parts = isoDate.split("-").map(Number);
  const date = new Date(parts[0], parts[1] - 1, parts[2]);
  const weekdays = ["日", "月", "火", "水", "木", "金", "土"];
  return `${isoDate}（${weekdays[date.getDay()]}）`;
}

function validateQuestionnaireConfig_() {
  if (QUESTIONNAIRE_CONFIG.kind !== "teacher_subject") {
    const dates = QUESTIONNAIRE_CONFIG.openDates;
    if (dates.length === 0) throw new Error("開校日を1日以上設定してください。");
    if (new Set(dates).size !== dates.length) throw new Error("開校日が重複しています。");
    dates.forEach((value) => {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        throw new Error(`開校日はYYYY-MM-DD形式にしてください: ${value}`);
      }
    });
    if (QUESTIONNAIRE_CONFIG.timeSlots.length === 0) {
      throw new Error("時間帯を1件以上設定してください。");
    }
  }
  if (
    QUESTIONNAIRE_CONFIG.kind === "student" ||
    QUESTIONNAIRE_CONFIG.kind === "teacher_subject"
  ) {
    const subjects = Object.values(QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel).flat();
    if (subjects.length === 0 || new Set(subjects).size !== subjects.length) {
      throw new Error("科目選択肢が未設定または重複しています。");
    }
  }
}

function logQuestionnaireUrls_(form, spreadsheetId) {
  console.log(`フォーム編集URL: ${form.getEditUrl()}`);
  console.log(`回答用URL: ${form.getPublishedUrl()}`);
  if (spreadsheetId) {
    console.log(`回答原本URL: https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit`);
  }
}
"""


__all__ = ["QuestionnaireScriptExportResult", "QuestionnaireScriptService"]
