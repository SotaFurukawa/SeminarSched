/**
 * SummerCourseScheduler用の講師出勤アンケートを作成するGoogle Apps Script。
 * 実行方法は同じディレクトリのREADME.mdを参照してください。
 */

const TEACHER_QUESTIONNAIRE_CONFIG = Object.freeze({
  title: "2026夏期講習 非常勤勤務アンケート",
  deadline: "2026年6月13日（土）",
  contact: "校舎へお問い合わせください",
  description:
    "夏期講習の出勤可能日時を確認するフォームです。" +
    "出勤できない日時にだけチェックを入れてください。\n\n" +
    "回答は勤務希望の確認、時間割作成、内容確認、必要な連絡にだけ使用します。" +
    "回答先スプレッドシートの閲覧者は担当者に限定してください。",
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
});

const TEACHER_FORM_ID_PROPERTY = "SUMMER_SCHEDULER_TEACHER_FORM_ID";
const TEACHER_SHEET_ID_PROPERTY = "SUMMER_SCHEDULER_TEACHER_RESPONSE_SHEET_ID";

/** 講師フォームと回答先スプレッドシートを1組だけ作成する。 */
function createTeacherQuestionnaire() {
  validateTeacherQuestionnaireConfig_();

  const properties = PropertiesService.getScriptProperties();
  const existingFormId = properties.getProperty(TEACHER_FORM_ID_PROPERTY);
  if (existingFormId) {
    try {
      const existingForm = FormApp.openById(existingFormId);
      logTeacherQuestionnaireUrls_(
        existingForm,
        properties.getProperty(TEACHER_SHEET_ID_PROPERTY),
      );
      throw new Error(
        "このスクリプトでは講師フォームを作成済みです。" +
          "重複作成せず、実行ログのURLから既存フォームを開いてください。",
      );
    } catch (error) {
      if (String(error).includes("講師フォームを作成済みです")) {
        throw error;
      }
      properties.deleteProperty(TEACHER_FORM_ID_PROPERTY);
      properties.deleteProperty(TEACHER_SHEET_ID_PROPERTY);
    }
  }

  const form = FormApp.create(TEACHER_QUESTIONNAIRE_CONFIG.title, true)
    .setDescription(
      TEACHER_QUESTIONNAIRE_CONFIG.description +
        `\n\n回答締切: ${TEACHER_QUESTIONNAIRE_CONFIG.deadline}` +
        `\n問い合わせ先: ${TEACHER_QUESTIONNAIRE_CONFIG.contact}`,
    )
    .setCollectEmail(false)
    .setProgressBar(true)
    .setShowLinkToRespondAgain(false)
    .setAllowResponseEdits(true)
    .setConfirmationMessage(
      "回答を受け付けました。修正が必要な場合は、回答編集リンクを使用するか、" +
        TEACHER_QUESTIONNAIRE_CONFIG.contact + "。",
    );

  form
    .addMultipleChoiceItem()
    .setTitle("個人情報の利用目的への同意（必須）")
    .setHelpText(
      "回答を勤務希望の確認、時間割作成、内容確認、必要な連絡に使用することを" +
        "確認してください。",
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
    .addPageBreakItem()
    .setTitle("出勤できない日時")
    .setHelpText(
      "チェックを入れた日時は『出勤不可』として扱います。" +
        "出勤できる日時にはチェックを入れないでください。",
    );
  form
    .addCheckboxGridItem()
    .setTitle("出勤不可日時（チェックしたコマは出勤不可）")
    .setRows(TEACHER_QUESTIONNAIRE_CONFIG.openDates.map(formatTeacherDateLabel_))
    .setColumns(TEACHER_QUESTIONNAIRE_CONFIG.timeSlots)
    .setRequired(false);
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

  const spreadsheet = SpreadsheetApp.create(
    `${TEACHER_QUESTIONNAIRE_CONFIG.title} 回答原本`,
  );
  form.setDestination(FormApp.DestinationType.SPREADSHEET, spreadsheet.getId());

  properties.setProperty(TEACHER_FORM_ID_PROPERTY, form.getId());
  properties.setProperty(TEACHER_SHEET_ID_PROPERTY, spreadsheet.getId());
  logTeacherQuestionnaireUrls_(form, spreadsheet.getId());
}

/** 作成済み講師フォームのURLをもう一度表示する。 */
function showCreatedTeacherQuestionnaireUrls() {
  const properties = PropertiesService.getScriptProperties();
  const formId = properties.getProperty(TEACHER_FORM_ID_PROPERTY);
  if (!formId) {
    throw new Error("講師フォームはまだ作成されていません。");
  }
  logTeacherQuestionnaireUrls_(
    FormApp.openById(formId),
    properties.getProperty(TEACHER_SHEET_ID_PROPERTY),
  );
}

function formatTeacherDateLabel_(isoDate) {
  const parts = isoDate.split("-").map(Number);
  const date = new Date(parts[0], parts[1] - 1, parts[2]);
  const weekdays = ["日", "月", "火", "水", "木", "金", "土"];
  return `${isoDate}（${weekdays[date.getDay()]}）`;
}

function validateTeacherQuestionnaireConfig_() {
  const dates = TEACHER_QUESTIONNAIRE_CONFIG.openDates;
  if (new Set(dates).size !== dates.length) {
    throw new Error("開校日が重複しています。");
  }
  dates.forEach((value) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      throw new Error(`開校日はYYYY-MM-DD形式にしてください: ${value}`);
    }
  });
  if (TEACHER_QUESTIONNAIRE_CONFIG.timeSlots.length === 0) {
    throw new Error("時間帯を1件以上設定してください。");
  }
}

function logTeacherQuestionnaireUrls_(form, spreadsheetId) {
  console.log(`フォーム編集URL: ${form.getEditUrl()}`);
  console.log(`回答用URL: ${form.getPublishedUrl()}`);
  if (spreadsheetId) {
    console.log(`回答原本URL: https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit`);
  }
}
