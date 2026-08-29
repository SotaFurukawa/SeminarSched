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
            "description": qsTr("アンケート作成画面でフォーム名と回答締切を確認し、保存先を選びます。生徒用・講師用の.gsと手順書が同じフォルダーへ保存されます。"),
            "screen": qsTr("SummerCourseScheduler"),
            "rows": [qsTr("開校日・コマを確認"), qsTr("回答締切を選択"), qsTr("フォーム作成キットを保存…")],
            "target": 2,
            "note": qsTr("保存後に「保存先を開く」を押すと、.gsが入ったフォルダーをすぐ開けます。")
        },
        {
            "number": "2",
            "title": qsTr("Apps Scriptを3つ用意"),
            "description": qsTr("ブラウザーで script.google.com を開き、左上の「新しいプロジェクト」を押します。.gsごとに別のプロジェクトを1つずつ作ります。"),
            "screen": qsTr("Google Apps Script"),
            "rows": [qsTr("＋ 新しいプロジェクト"), qsTr("自分のプロジェクト"), qsTr("無題のプロジェクト")],
            "target": 0,
            "note": qsTr("Google Apps Scriptの「デプロイ」は不要です。生徒用・講師勤務日時用・講師指導可能科目用の3プロジェクトを作ります。")
        },
        {
            "number": "3",
            "title": qsTr("Code.gsへ全内容を貼り付け"),
            "description": qsTr("保存フォルダーの.gsを右クリックし、「プログラムから開く」→「メモ帳」で開いて全内容をコピーします。Apps ScriptのCode.gsにある初期コードをすべて削除し、貼り付けて保存します。"),
            "screen": qsTr("コードエディタ — Code.gs"),
            "rows": [qsTr("function myFunction() { … } を削除"), qsTr(".gsの全内容を貼り付け"), qsTr("Ctrl + S で保存")],
            "target": 1,
            "note": qsTr("ファイル名だけでなく、先頭から最後まで全内容をコピーしてください。画面上部の雲マークが保存済みになれば完了です。")
        },
        {
            "number": "4",
            "title": qsTr("作成関数を選んで実行"),
            "description": qsTr("上部の関数一覧で作成関数を選び、左側の「実行」を押します。"),
            "screen": qsTr("Apps Script ツールバー"),
            "rows": [qsTr("▶ 実行"), qsTr("createStudentQuestionnaire ▼"), qsTr("実行ログ")],
            "target": 0,
            "note": qsTr("生徒用は createStudentQuestionnaire、講師勤務日時用は createTeacherQuestionnaire、指導可能科目用は createTeacherSubjectQuestionnaire を選びます。")
        },
        {
            "number": "5",
            "title": qsTr("初回だけ権限を確認"),
            "description": qsTr("「承認が必要です」と表示されたら「権限を確認」を押し、使用するGoogleアカウントを選びます。"),
            "screen": qsTr("承認が必要です"),
            "rows": [qsTr("キャンセル"), qsTr("権限を確認"), qsTr("Googleアカウントを選択")],
            "target": 1,
            "note": qsTr("この処理は自分のGoogleドライブ内にフォームと回答スプレッドシートを作るため、フォームとスプレッドシートの権限を求めます。")
        },
        {
            "number": "6",
            "title": qsTr("Googleの警告画面を進む"),
            "description": qsTr("自分で作成した未公開スクリプトのため「このアプリはGoogleで確認されていません」と表示される場合があります。「詳細」を押してから「無題のプロジェクト（安全ではないページ）に移動」を押します。"),
            "screen": qsTr("このアプリはGoogleで確認されていません"),
            "rows": [qsTr("詳細"), qsTr("安全なページに戻る"), qsTr("無題のプロジェクト（安全ではないページ）に移動")],
            "target": 0,
            "note": qsTr("自分でアプリから保存して貼り付けたコードであることを確認してから進んでください。第三者から受け取った不明なコードでは実行しません。")
        },
        {
            "number": "7",
            "title": qsTr("必要なアクセスを許可"),
            "description": qsTr("権限一覧で「すべて選択」にチェックを入れ、内容を確認して「続行」を押します。"),
            "screen": qsTr("アクセスできる情報を選択"),
            "rows": [qsTr("□ すべて選択"), qsTr("□ スプレッドシート"), qsTr("□ Googleフォーム　　続行")],
            "target": 0,
            "note": qsTr("許可はGoogleアカウントから後で取り消せます。アプリからGoogleへ個人情報を自動送信する処理はありません。")
        },
        {
            "number": "8",
            "title": qsTr("実行ログのURLを確認"),
            "description": qsTr("実行が完了すると、実行ログに質問ページ・編集ページ・回答確認ページのURLが表示されます。"),
            "screen": qsTr("実行ログ"),
            "rows": [qsTr("回答用URL：生徒・講師へ配布"), qsTr("フォーム編集URL：担当者用"), qsTr("回答原本URL：担当者だけで管理")],
            "target": 0,
            "note": qsTr("配布前に回答用URLを自分で開き、日付・コマ・科目をテスト回答して確認してください。回答原本は一般公開しません。")
        },
        {
            "number": "9",
            "title": qsTr("回答をCSVでダウンロード"),
            "description": qsTr("回答スプレッドシートを開き、「ファイル」→「ダウンロード」→「カンマ区切り形式（.csv）」を選びます。そのCSVをアプリの③アンケート取込みで選択します。"),
            "screen": qsTr("Google スプレッドシート"),
            "rows": [qsTr("ファイル"), qsTr("ダウンロード"), qsTr("カンマ区切り形式（.csv）")],
            "target": 2,
            "note": qsTr("Z・A・B・Cの複数回答が同じセルに入るのは正常です。アプリが区切って各コマの不可情報として読み取ります。")
        }
    ]

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(1000, parent.width - 40)
    height: Math.min(740, parent.height - 40)
    modal: true
    title: qsTr("赤い案内つき：Googleフォームの作り方")
    standardButtons: Dialog.Close
    closePolicy: Popup.CloseOnEscape

    UiTheme { id: theme }

    contentItem: ScrollView {
        id: guideScroll

        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AlwaysOn

        ColumnLayout {
            width: guideScroll.availableWidth
            spacing: 12

            InlineMessage {
                Layout.fillWidth: true
                kind: "info"
                message: qsTr("実際の画面に近い図で、押す場所を赤枠と赤い矢印で示します。Google側の表示は更新により多少異なる場合があります。")
            }

            Repeater {
                model: root.guideSteps

                delegate: Rectangle {
                    id: guideCard

                    required property var modelData

                    Layout.fillWidth: true
                    implicitHeight: Math.max(mockScreen.implicitHeight,
                                             explanation.implicitHeight) + 24
                    radius: 10
                    color: theme.surface
                    border.color: theme.border

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 16

                        Rectangle {
                            id: mockScreen

                            Layout.preferredWidth: Math.min(420,
                                                            Math.max(320,
                                                                     guideCard.width * 0.46))
                            implicitHeight: 192
                            radius: 8
                            color: "#f8fafc"
                            border.color: "#aeb8c7"
                            clip: true

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 0

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 38
                                    color: "#e7ebf1"

                                    Label {
                                        anchors.centerIn: parent
                                        width: parent.width - 20
                                        text: guideCard.modelData.screen
                                        color: "#475467"
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                        horizontalAlignment: Text.AlignHCenter
                                        elide: Text.ElideRight
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.margins: 12
                                    spacing: 8

                                    Repeater {
                                        model: guideCard.modelData.rows

                                        delegate: Rectangle {
                                            id: mockRow

                                            required property int index
                                            required property var modelData

                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 38
                                            radius: 5
                                            color: index === Number(guideCard.modelData.target)
                                                   ? "#fff1f0" : "#ffffff"
                                            border.width: index === Number(guideCard.modelData.target) ? 3 : 1
                                            border.color: index === Number(guideCard.modelData.target)
                                                          ? "#d92d20" : "#cdd5df"

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 9
                                                anchors.rightMargin: 9
                                                spacing: 8

                                                Rectangle {
                                                    Layout.preferredWidth: 22
                                                    Layout.preferredHeight: 22
                                                    radius: 11
                                                    color: mockRow.index === Number(guideCard.modelData.target)
                                                           ? "#d92d20" : "#98a2b3"

                                                    Label {
                                                        anchors.centerIn: parent
                                                        text: mockRow.index === Number(guideCard.modelData.target)
                                                              ? "→" : ""
                                                        color: "#ffffff"
                                                        font.pixelSize: 13
                                                        font.weight: Font.Bold
                                                    }
                                                }

                                                Label {
                                                    Layout.fillWidth: true
                                                    text: String(mockRow.modelData)
                                                    color: mockRow.index === Number(guideCard.modelData.target)
                                                           ? "#9b231b" : "#344054"
                                                    font.pixelSize: 10
                                                    font.weight: mockRow.index === Number(guideCard.modelData.target)
                                                                 ? Font.DemiBold : Font.Normal
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            id: explanation

                            Layout.fillWidth: true
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 9

                                Rectangle {
                                    Layout.preferredWidth: 32
                                    Layout.preferredHeight: 32
                                    radius: 16
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

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: noteText.implicitHeight + 18
                                radius: 6
                                color: "#fff8e7"
                                border.color: "#e2bc62"

                                Label {
                                    id: noteText
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.margins: 9
                                    text: qsTr("補足：%1").arg(guideCard.modelData.note)
                                    color: "#6b4f13"
                                    font.pixelSize: 10
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }
            }

            InlineMessage {
                Layout.fillWidth: true
                kind: "warning"
                message: qsTr("回答原本には氏名・学年・希望日時などの個人情報が含まれます。一般公開せず、担当者だけがアクセスできる場所で管理してください。")
            }
        }
    }
}
