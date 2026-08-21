pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root

    readonly property var guideSteps: [
        {
            "number": "1",
            "title": qsTr("アプリで作成キットを保存"),
            "description": qsTr("②のフォーム作成欄へフォーム名・締切・問い合わせ先を入力し、3種類をまとめて作成します。"),
            "mockTitle": qsTr("SummerCourseScheduler"),
            "mockRows": [
                {"label": qsTr("開校日 18日／有効コマ 4件"), "kind": "complete"},
                {"label": qsTr("フォーム名・締切・問い合わせ先"), "kind": "field"},
                {"label": qsTr("3種類のフォームをまとめて作成"), "kind": "action"}
            ],
            "bullets": [
                qsTr("①で設定した開校日・コマ・科目が自動反映されます。"),
                qsTr("保存先には3つの.gsと手順書が作成されます。")
            ]
        },
        {
            "number": "2",
            "title": qsTr("Apps Scriptを3つ用意"),
            "description": qsTr("ブラウザーでGoogle Apps Scriptを開き、3種類それぞれに別の「新しいプロジェクト」を作ります。"),
            "mockTitle": qsTr("Google Apps Script"),
            "mockRows": [
                {"label": qsTr("＋ 新しいプロジェクト"), "kind": "action"},
                {"label": qsTr("生徒アンケート用プロジェクト"), "kind": "field"},
                {"label": qsTr("講師勤務日時用プロジェクト"), "kind": "field"},
                {"label": qsTr("講師指導科目用プロジェクト"), "kind": "field"}
            ],
            "bullets": [
                qsTr("同じプロジェクトへ複数ファイルを混ぜないでください。"),
                qsTr("Google Apps Scriptの「デプロイ」は不要です。")
            ]
        },
        {
            "number": "3",
            "title": qsTr("Code.gsへ全内容を貼り付け"),
            "description": qsTr("最初から入っているコードをすべて削除し、出力された.gsの内容を先頭から最後まで貼り付けて保存します。"),
            "mockTitle": qsTr("コードエディタ — Code.gs"),
            "mockRows": [
                {"label": qsTr("1  const QUESTIONNAIRE_CONFIG = …"), "kind": "code"},
                {"label": qsTr("2  function createStudent…() {"), "kind": "code"},
                {"label": qsTr("Ctrl + S　保存"), "kind": "action"}
            ],
            "bullets": [
                qsTr("生徒用にはcreate_student_questionnaire.gsを使います。"),
                qsTr("講師勤務日時用にはcreate_teacher_questionnaire.gsを使います。"),
                qsTr("指導可能科目用にはcreate_teacher_subject_questionnaire.gsを使います。")
            ]
        },
        {
            "number": "4",
            "title": qsTr("作成関数を選んで実行"),
            "description": qsTr("上部の関数選択から作成関数を選び、「実行」を押します。初回だけGoogleの権限確認を許可します。"),
            "mockTitle": qsTr("Apps Script ツールバー"),
            "mockRows": [
                {"label": qsTr("createStudentQuestionnaire ▼"), "kind": "field"},
                {"label": qsTr("▶ 実行"), "kind": "action"},
                {"label": qsTr("権限を確認 → 許可"), "kind": "warning"}
            ],
            "bullets": [
                qsTr("講師勤務日時用はcreateTeacherQuestionnaire、指導可能科目用はcreateTeacherSubjectQuestionnaireを選びます。"),
                qsTr("再実行時は既存フォームのURLが表示され、重複作成を防ぎます。")
            ]
        },
        {
            "number": "5",
            "title": qsTr("実行ログのURLを確認"),
            "description": qsTr("実行ログに3つのURLが表示されます。編集用で質問を確認し、回答用だけを対象者へ案内します。"),
            "mockTitle": qsTr("実行ログ"),
            "mockRows": [
                {"label": qsTr("フォーム編集URL：担当者用"), "kind": "complete"},
                {"label": qsTr("回答用URL：生徒・講師へ案内"), "kind": "action"},
                {"label": qsTr("回答原本URL：担当者だけで共有"), "kind": "warning"}
            ],
            "bullets": [
                qsTr("配布前に日付・コマ・質問・締切をテスト回答で確認します。"),
                qsTr("回答原本の閲覧者は業務上必要な担当者だけに限定します。")
            ]
        }
    ]

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(920, parent.width - 48)
    height: Math.min(680, parent.height - 48)
    modal: true
    title: qsTr("画像つき：Googleフォームの作り方")
    standardButtons: Dialog.Close
    closePolicy: Popup.CloseOnEscape

    UiTheme { id: theme }

    contentItem: ScrollView {
        id: guideScroll

        clip: true
        contentWidth: availableWidth
        Accessible.name: root.title
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: guideScroll.availableWidth
            spacing: 12

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: guideNotice.implicitHeight + 22
                radius: 8
                color: "#eef4ff"
                border.color: "#b9cdf5"

                Label {
                    id: guideNotice

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 11
                    text: qsTr("画面イメージを見ながら上から順に進めてください。Google側の表示は更新により多少異なる場合があります。")
                    color: "#31558a"
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }

            Repeater {
                model: root.guideSteps

                delegate: Rectangle {
                    id: guideCard

                    required property var modelData

                    Layout.fillWidth: true
                    implicitHeight: Math.max(mockScreen.implicitHeight,
                                             stepExplanation.implicitHeight) + 24
                    radius: 10
                    color: theme.surface
                    border.color: theme.border

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 16

                        Rectangle {
                            id: mockScreen

                            Layout.preferredWidth: Math.min(360,
                                                            Math.max(280,
                                                                     guideCard.width * 0.44))
                            implicitHeight: Math.max(
                                                188,
                                                50 + guideCard.modelData.mockRows.length * 43)
                            radius: 8
                            color: "#f8fafc"
                            border.color: "#aeb8c7"
                            clip: true
                            Accessible.name: qsTr("手順%1の画面イメージ")
                                             .arg(guideCard.modelData.number)

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 0

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 34
                                    color: "#e7ebf1"

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 6

                                        Repeater {
                                            model: ["#e46b63", "#e7b64b", "#59b56f"]
                                            delegate: Rectangle {
                                                required property var modelData
                                                width: 8
                                                height: 8
                                                radius: 4
                                                color: modelData
                                            }
                                        }

                                        Label {
                                            Layout.fillWidth: true
                                            text: guideCard.modelData.mockTitle
                                            color: "#475467"
                                            font.pixelSize: 10
                                            font.weight: Font.DemiBold
                                            horizontalAlignment: Text.AlignHCenter
                                            elide: Text.ElideRight
                                        }
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.margins: 12
                                    spacing: 8

                                    Repeater {
                                        model: guideCard.modelData.mockRows

                                        delegate: Rectangle {
                                            id: mockRow

                                            required property var modelData

                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 35
                                            radius: 5
                                            color: mockRow.modelData.kind === "action" ? "#e9f1ff"
                                                   : mockRow.modelData.kind === "complete" ? "#e9f8ef"
                                                   : mockRow.modelData.kind === "warning" ? "#fff5dd"
                                                   : mockRow.modelData.kind === "code" ? "#202937"
                                                   : "#ffffff"
                                            border.color: mockRow.modelData.kind === "action" ? theme.accent
                                                          : mockRow.modelData.kind === "complete" ? "#69b886"
                                                          : mockRow.modelData.kind === "warning" ? "#dcaa3e"
                                                          : mockRow.modelData.kind === "code" ? "#202937"
                                                          : "#cdd5df"

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 10
                                                anchors.rightMargin: 10
                                                spacing: 8

                                                Rectangle {
                                                    Layout.preferredWidth: 16
                                                    Layout.preferredHeight: 16
                                                    radius: 8
                                                    color: mockRow.modelData.kind === "action" ? theme.accent
                                                           : mockRow.modelData.kind === "complete" ? "#3f9b64"
                                                           : mockRow.modelData.kind === "warning" ? "#c38a18"
                                                           : mockRow.modelData.kind === "code" ? "#75839a"
                                                           : "#98a2b3"

                                                    Label {
                                                        anchors.centerIn: parent
                                                        text: mockRow.modelData.kind === "complete" ? "✓" : ""
                                                        color: "#ffffff"
                                                        font.pixelSize: 9
                                                        font.weight: Font.Bold
                                                    }
                                                }

                                                Label {
                                                    Layout.fillWidth: true
                                                    text: mockRow.modelData.label
                                                    color: mockRow.modelData.kind === "code"
                                                           ? "#f4f7fb" : "#344054"
                                                    font.pixelSize: 10
                                                    font.family: mockRow.modelData.kind === "code"
                                                                 ? "Consolas" : ""
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            id: stepExplanation

                            Layout.fillWidth: true
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 9

                                Rectangle {
                                    Layout.preferredWidth: 30
                                    Layout.preferredHeight: 30
                                    radius: 15
                                    color: theme.accent

                                    Label {
                                        anchors.centerIn: parent
                                        text: guideCard.modelData.number
                                        color: "#ffffff"
                                        font.pixelSize: 13
                                        font.weight: Font.Bold
                                    }
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: guideCard.modelData.title
                                    color: theme.textPrimary
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.WordWrap
                                }
                            }

                            Label {
                                Layout.fillWidth: true
                                text: guideCard.modelData.description
                                color: theme.textSecondary
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }

                            Repeater {
                                model: guideCard.modelData.bullets

                                delegate: Label {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    text: qsTr("• %1").arg(modelData)
                                    color: "#475467"
                                    font.pixelSize: 10
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: finalNotice.implicitHeight + 20
                radius: 8
                color: "#fff8e7"
                border.color: "#e2bc62"

                Label {
                    id: finalNotice

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 10
                    text: qsTr("注意：回答原本には個人情報が含まれます。一般公開せず、GitHubにも追加しないでください。")
                    color: "#7a5710"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
