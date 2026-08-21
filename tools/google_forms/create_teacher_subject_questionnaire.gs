/**
 * SummerCourseScheduler用の講師・指導可能科目アンケートを作るGoogle Apps Script。
 * 実行方法は同じディレクトリのREADME.mdを参照してください。
 */

const TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG = Object.freeze({
  title: "講師 指導可能科目アンケート",
  deadline: "校舎で設定してください",
  contact: "校舎へお問い合わせください",
  description:
    "現在、講師本人が単独で授業を進められる指導可能科目を確認するフォームです。" +
    "小学校・中学校・高校から、該当する科目をすべて選択してください。\n\n" +
    "回答は講師情報の更新、担当可能科目の確認、時間割作成にだけ使用します。" +
    "回答先スプレッドシートの閲覧者は担当者に限定してください。",
  subjectsBySchoolLevel: {
    elementary: [
      "小学校・英語",
      "小学校・算数（中学受験）",
      "小学校・算数（中学受験以外なら可能）",
      "小学校・国語（中学受験）",
      "小学校・国語（中学受験以外なら可能）",
      "小学校・理科",
      "小学校・社会",
    ],
    juniorHigh: [
      "中学校・英語",
      "中学校・数学",
      "中学校・国語",
      "中学校・理科",
      "中学校・社会",
    ],
    highSchool: [
      "高校・英語",
      "高校・現代文",
      "高校・古文",
      "高校・数学IA",
      "高校・数学IIBC",
      "高校・数学III",
      "高校・物理",
      "高校・化学",
      "高校・生物",
      "高校・日本史",
      "高校・世界史",
      "高校・地理",
      "高校・政治経済",
      "高校・情報",
    ],
  },
});

const TEACHER_SUBJECT_FORM_ID_PROPERTY =
  "SUMMER_SCHEDULER_TEACHER_SUBJECT_FORM_ID";
const TEACHER_SUBJECT_SHEET_ID_PROPERTY =
  "SUMMER_SCHEDULER_TEACHER_SUBJECT_RESPONSE_SHEET_ID";

/** フォームと回答先スプレッドシートを1組だけ作成する。 */
function createTeacherSubjectQuestionnaire() {
  validateTeacherSubjectQuestionnaireConfig_();

  const properties = PropertiesService.getScriptProperties();
  const existingFormId = properties.getProperty(
    TEACHER_SUBJECT_FORM_ID_PROPERTY,
  );
  if (existingFormId) {
    try {
      const existingForm = FormApp.openById(existingFormId);
      logTeacherSubjectQuestionnaireUrls_(
        existingForm,
        properties.getProperty(TEACHER_SUBJECT_SHEET_ID_PROPERTY),
      );
      throw new Error(
        "このスクリプトではフォームを作成済みです。" +
          "重複作成せず、実行ログのURLから既存フォームを開いてください。",
      );
    } catch (error) {
      if (String(error).includes("フォームを作成済みです")) throw error;
      properties.deleteProperty(TEACHER_SUBJECT_FORM_ID_PROPERTY);
      properties.deleteProperty(TEACHER_SUBJECT_SHEET_ID_PROPERTY);
    }
  }

  const form = FormApp.create(TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.title, true)
    .setDescription(
      TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.description +
        `\n\n回答締切: ${TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.deadline}` +
        `\n問い合わせ先: ${TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.contact}`,
    )
    .setCollectEmail(false)
    .setProgressBar(true)
    .setShowLinkToRespondAgain(false)
    .setAllowResponseEdits(true)
    .setConfirmationMessage(
      "回答を受け付けました。修正が必要な場合は、回答編集リンクを使用するか、" +
        TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.contact + "。",
    );

  form
    .addMultipleChoiceItem()
    .setTitle("個人情報の利用目的への同意（必須）")
    .setHelpText(
      "回答を講師情報の更新、担当可能科目の確認、時間割作成に使用します。",
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
    TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.elementary,
  );
  addTeacherSubjectCheckbox_(
    form,
    "指導可能科目（中学校）",
    TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.juniorHigh,
  );
  addTeacherSubjectCheckbox_(
    form,
    "指導可能科目（高校）",
    TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.highSchool,
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

  const spreadsheet = SpreadsheetApp.create(
    `${TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.title} 回答原本`,
  );
  form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheet.getId());

  properties.setProperty(TEACHER_SUBJECT_FORM_ID_PROPERTY, form.getId());
  properties.setProperty(
    TEACHER_SUBJECT_SHEET_ID_PROPERTY,
    spreadsheet.getId(),
  );
  logTeacherSubjectQuestionnaireUrls_(form, spreadsheet.getId());
}

function addTeacherSubjectCheckbox_(form, title, subjects) {
  form
    .addCheckboxItem()
    .setTitle(title)
    .setChoiceValues(subjects)
    .setRequired(false);
}

/** 作成済みフォームのURLをもう一度表示する。 */
function showCreatedTeacherSubjectQuestionnaireUrls() {
  const properties = PropertiesService.getScriptProperties();
  const formId = properties.getProperty(TEACHER_SUBJECT_FORM_ID_PROPERTY);
  if (!formId) {
    throw new Error("講師・指導可能科目フォームはまだ作成されていません。");
  }
  logTeacherSubjectQuestionnaireUrls_(
    FormApp.openById(formId),
    properties.getProperty(TEACHER_SUBJECT_SHEET_ID_PROPERTY),
  );
}

/** 既存フォームを残し、現在のコードで置換用フォームを新規作成する。 */
function createReplacementTeacherSubjectQuestionnaire() {
  const properties = PropertiesService.getScriptProperties();
  properties.deleteProperty(TEACHER_SUBJECT_FORM_ID_PROPERTY);
  properties.deleteProperty(TEACHER_SUBJECT_SHEET_ID_PROPERTY);
  createTeacherSubjectQuestionnaire();
}

function validateTeacherSubjectQuestionnaireConfig_() {
  const subjects = Object.values(
    TEACHER_SUBJECT_QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel,
  ).flat();
  if (subjects.length !== 26 || new Set(subjects).size !== subjects.length) {
    throw new Error("科目選択肢はアプリ既定の重複しない26科目にしてください。");
  }
}

function logTeacherSubjectQuestionnaireUrls_(form, spreadsheetId) {
  console.log(`フォーム編集URL: ${form.getEditUrl()}`);
  console.log(`回答用URL: ${form.getPublishedUrl()}`);
  if (spreadsheetId) {
    console.log(
      `回答原本URL: https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit`,
    );
  }
}
