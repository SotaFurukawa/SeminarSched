/**
 * SummerCourseScheduler用の生徒・保護者アンケートを作成するGoogle Apps Script。
 *
 * 使い方:
 * 1. https://script.google.com/ で新しいプロジェクトを作る。
 * 2. このファイルの内容を Code.gs へ貼り付ける。
 * 3. QUESTIONNAIRE_CONFIG の年度・日程・締切等を実際の講習へ合わせる。
 * 4. createStudentQuestionnaire を実行し、権限を許可する。
 * 5. 実行ログに表示された編集URL、回答URL、回答表URLを開く。
 *
 * 実データや回答内容をこのリポジトリへ保存しないでください。
 */

const QUESTIONNAIRE_CONFIG = Object.freeze({
  title: "2026夏期講習 個別指導受講申込",
  deadline: "2026年6月25日（木）",
  contact: "校舎へお問い合わせください",
  description:
    "個別指導コースの受講申込フォームです。" +
    "メールアドレス、お子様のお名前、学年、受講教科・回数、" +
    "受講できない日時をご回答ください。\n\n" +
    "回答は講習の受付、時間割作成、内容確認、必要な連絡にだけ使用します。" +
    "回答先スプレッドシートの閲覧者は担当者に限定してください。",
  gradeGroups: {
    elementary: ["小1", "小2", "小3", "小4", "小5", "小6"],
    juniorHigh: ["中1", "中2", "中3"],
    highSchool: ["高1", "高2", "高3"],
  },
  enrollmentTypes: ["在籍生", "体験生"],
  subjectsBySchoolLevel: {
    elementary: [
      "小学校・英語",
      "小学校・算数",
      "小学校・国語",
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
      "高校・数学一般",
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
  sessionCounts: [
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
  ],
  openDates: [
    "2026-07-24",
    "2026-07-25",
    "2026-07-27",
    "2026-07-28",
    "2026-07-30",
    "2026-07-31",
    "2026-08-01",
    "2026-08-03",
    "2026-08-04",
    "2026-08-06",
    "2026-08-07",
    "2026-08-08",
    "2026-08-17",
    "2026-08-18",
    "2026-08-20",
    "2026-08-21",
    "2026-08-22",
    "2026-08-24",
    "2026-08-25",
    "2026-08-27",
    "2026-08-29",
  ],
  timeSlots: [
    "Z 15:40～17:00",
    "A 17:10～18:30",
    "B 18:40～20:00",
    "C 20:10～21:30",
  ],
  summerTestChoices: [
    "夏期学力テストを受験する",
    "夏期学力テストを受験しない",
    "対象外（小1～小3・高校生）",
  ],
});

const FORM_ID_PROPERTY = "SUMMER_SCHEDULER_STUDENT_FORM_ID";
const SPREADSHEET_ID_PROPERTY = "SUMMER_SCHEDULER_STUDENT_RESPONSE_SHEET_ID";

/** フォームと回答先スプレッドシートを1組だけ作成する。 */
function createStudentQuestionnaire() {
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
      if (String(error).includes("フォームを作成済みです")) {
        throw error;
      }
      properties.deleteProperty(FORM_ID_PROPERTY);
      properties.deleteProperty(SPREADSHEET_ID_PROPERTY);
    }
  }

  const form = FormApp.create(QUESTIONNAIRE_CONFIG.title, true)
    .setDescription(
      QUESTIONNAIRE_CONFIG.description +
        `\n\n申込締切: ${QUESTIONNAIRE_CONFIG.deadline}` +
        `\n問い合わせ先: ${QUESTIONNAIRE_CONFIG.contact}`,
    )
    .setCollectEmail(true)
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
      "回答を講習の受付、時間割作成、内容確認、必要な連絡に使用することを" +
        "確認してください。",
    )
    .setChoiceValues(["上記の利用目的を確認し、回答します"])
    .setRequired(true);

  form
    .addTextItem()
    .setTitle("姓（苗字）（必須）")
    .setHelpText("お子様の姓（苗字）をご記入ください。例: 山田")
    .setRequired(true);
  form
    .addTextItem()
    .setTitle("名（必須）")
    .setHelpText("お子様の名をご記入ください。例: 太郎")
    .setRequired(true);
  const gradeItem = form
    .addListItem()
    .setTitle("学年（必須）")
    .setRequired(true);
  form
    .addListItem()
    .setTitle("在籍区分（必須）")
    .setChoiceValues(QUESTIONNAIRE_CONFIG.enrollmentTypes)
    .setRequired(true);

  const elementaryPage = form
    .addPageBreakItem()
    .setTitle("小学生の受講教科・回数")
    .setHelpText("小学校の科目だけが表示されています。最大4教科まで回答できます。");
  addSubjectRequestSection_(
    form,
    "小学校",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.elementary,
  );

  const juniorHighPage = form
    .addPageBreakItem()
    .setTitle("中学生の受講教科・回数")
    .setHelpText("中学校の科目だけが表示されています。最大4教科まで回答できます。");
  addSubjectRequestSection_(
    form,
    "中学校",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.juniorHigh,
  );

  const highSchoolPage = form
    .addPageBreakItem()
    .setTitle("高校生の受講教科・回数")
    .setHelpText("高校の科目だけが表示されています。最大4教科まで回答できます。");
  addSubjectRequestSection_(
    form,
    "高校",
    QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel.highSchool,
  );

  const availabilityPage = form
    .addPageBreakItem()
    .setTitle("受講できない日時")
    .setHelpText(
      "チェックを入れた日時は『受講できない』として扱います。" +
      "受講できる日時にはチェックを入れないでください。",
    );

  // 各校種の科目回答後は、他校種の科目を飛ばして共通の日程欄へ進む。
  elementaryPage.setGoToPage(availabilityPage);
  juniorHighPage.setGoToPage(availabilityPage);
  highSchoolPage.setGoToPage(availabilityPage);

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
  form
    .addCheckboxGridItem()
    .setTitle("受講不可日時（チェックしたコマは受講不可）")
    .setRows(QUESTIONNAIRE_CONFIG.openDates.map(formatDateLabel_))
    .setColumns(QUESTIONNAIRE_CONFIG.timeSlots)
    .setRequired(false);
  form
    .addPageBreakItem()
    .setTitle("確認・特記事項")
    .setHelpText("受講不可日時の意味を確認し、必要に応じて特記事項をご記入ください。");
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

  const spreadsheet = SpreadsheetApp.create(`${QUESTIONNAIRE_CONFIG.title} 回答原本`);
  form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheet.getId());

  properties.setProperty(FORM_ID_PROPERTY, form.getId());
  properties.setProperty(SPREADSHEET_ID_PROPERTY, spreadsheet.getId());
  logQuestionnaireUrls_(form, spreadsheet.getId());
}

/** 指定校種だけを候補にした、最大4教科分の質問を追加する。 */
function addSubjectRequestSection_(form, schoolLabel, subjects) {
  for (let index = 1; index <= 4; index += 1) {
    const required = index === 1;
    form
      .addListItem()
      .setTitle(
        `受講教科（${schoolLabel}・${index}教科目）${required ? "（必須）" : ""}`,
      )
      .setHelpText(
        index === 1
          ? "受講する科目を選択してください。"
          : "受講しない場合は未回答のままにしてください。",
      )
      .setChoiceValues(subjects)
      .setRequired(required);
    form
      .addListItem()
      .setTitle(
        `受講回数（${schoolLabel}・${index}教科目）${required ? "（必須）" : ""}`,
      )
      .setHelpText("直前の受講教科について、希望する授業回数を選択してください。")
      .setChoiceValues(QUESTIONNAIRE_CONFIG.sessionCounts)
      .setRequired(required);
  }
}

/** 作成済みフォームのURLをもう一度表示する。 */
function showCreatedQuestionnaireUrls() {
  const properties = PropertiesService.getScriptProperties();
  const formId = properties.getProperty(FORM_ID_PROPERTY);
  if (!formId) {
    throw new Error("フォームはまだ作成されていません。");
  }
  logQuestionnaireUrls_(
    FormApp.openById(formId),
    properties.getProperty(SPREADSHEET_ID_PROPERTY),
  );
}

/**
 * 既存フォームを残したまま、現在の設定とコードで置換用フォームを新規作成する。
 *
 * 質問構成を変更したときだけ使用する。旧フォームと旧回答表は削除しない。
 * 実行後は新しいフォームが作成済みとして記録されるため、通常の作成関数を
 * 再実行しても重複作成されない。
 */
function createReplacementStudentQuestionnaire() {
  const properties = PropertiesService.getScriptProperties();
  properties.deleteProperty(FORM_ID_PROPERTY);
  properties.deleteProperty(SPREADSHEET_ID_PROPERTY);
  createStudentQuestionnaire();
}

function formatDateLabel_(isoDate) {
  const parts = isoDate.split("-").map(Number);
  const date = new Date(parts[0], parts[1] - 1, parts[2]);
  const weekdays = ["日", "月", "火", "水", "木", "金", "土"];
  return `${isoDate}（${weekdays[date.getDay()]}）`;
}

function validateQuestionnaireConfig_() {
  const grades = Object.values(QUESTIONNAIRE_CONFIG.gradeGroups).flat();
  if (grades.length !== 12 || new Set(grades).size !== grades.length) {
    throw new Error("学年は小1～高3の重複しない12項目にしてください。");
  }
  const subjects = Object.values(QUESTIONNAIRE_CONFIG.subjectsBySchoolLevel).flat();
  if (subjects.length !== 23) {
    throw new Error("科目選択肢はアプリ既定の23科目と一致させてください。");
  }
  if (new Set(subjects).size !== subjects.length) {
    throw new Error("科目選択肢が重複しています。");
  }
  if (new Set(QUESTIONNAIRE_CONFIG.openDates).size !== QUESTIONNAIRE_CONFIG.openDates.length) {
    throw new Error("開校日が重複しています。");
  }
  QUESTIONNAIRE_CONFIG.openDates.forEach((value) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      throw new Error(`開校日はYYYY-MM-DD形式にしてください: ${value}`);
    }
  });
  if (QUESTIONNAIRE_CONFIG.timeSlots.length === 0) {
    throw new Error("時間帯を1件以上設定してください。");
  }
}

function logQuestionnaireUrls_(form, spreadsheetId) {
  console.log(`フォーム編集URL: ${form.getEditUrl()}`);
  console.log(`回答用URL: ${form.getPublishedUrl()}`);
  if (spreadsheetId) {
    console.log(`回答原本URL: https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit`);
  }
}
