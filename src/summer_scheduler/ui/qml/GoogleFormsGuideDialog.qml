pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Dialog {
    id: root

    readonly property var guideSteps: [
        {
            "number": "1",
            "title": qsTr("アプリで作成キットを保存"),
            "description": qsTr("生徒用・講師用のフォーム名、回答締切、問い合わせ先を確認し、「フォーム作成キットを保存…」を押して保存先を選びます。"),
            "images": [
                {"source": "assets/google_forms_guide/01_save_kit.png", "accessible": qsTr("フォーム作成キットを保存する画面"), "height": 220}
            ],
            "note": qsTr("開校日と有効コマが未設定の場合は保存できません。先に①設定で授業日とコマを確定してください。")
        },
        {
            "number": "2",
            "title": qsTr("保存先を開く"),
            "description": qsTr("保存が完了すると「保存先を開く」ボタンが表示されます。押すと、作成された3つの.gsと手順書が入ったフォルダーを開けます。"),
            "images": [
                {"source": "assets/google_forms_guide/02_open_saved_folder.png", "accessible": qsTr("保存先を開くボタンが表示された画面"), "height": 220}
            ],
            "note": qsTr("生徒用は create_student_questionnaire.gs、講師勤務日時用は create_teacher_questionnaire.gs、講師指導可能科目用は create_teacher_subject_questionnaire.gs です。")
        },
        {
            "number": "3",
            "title": qsTr("create_student_questionnaire.gsをメモ帳で開く"),
            "description": qsTr("create_student_questionnaire.gsを右クリックし、「プログラムから開く」から「メモ帳」を選びます。メモ帳に表示された内容を先頭から最後まで選択してコピーします。"),
            "images": [
                {"source": "assets/google_forms_guide/03_open_with_menu.png", "accessible": qsTr("gsファイルのプログラムから開くメニュー"), "height": 340},
                {"source": "assets/google_forms_guide/03_choose_notepad.png", "accessible": qsTr("gsファイルをメモ帳で開く選択画面"), "height": 340}
            ],
            "note": qsTr("ファイル名ではなく、メモ帳に表示されたコードの全内容をコピーします。")
        },
        {
            "number": "4",
            "title": qsTr("Apps Scriptで新しいプロジェクトを作る"),
            "description": qsTr("https://script.google.com/home を開き、「新しいプロジェクト」を押します。Code.gsに最初から入っている function myFunction() のコードをすべて削除します。"),
            "images": [
                {"source": "assets/google_forms_guide/04_apps_script_home.png", "accessible": qsTr("Google Apps Scriptの新しいプロジェクトボタン"), "height": 330},
                {"source": "assets/google_forms_guide/04_blank_code_gs.png", "accessible": qsTr("初期コードが表示されたCode.gs"), "height": 330}
            ],
            "note": qsTr("生徒用・講師勤務日時用・講師指導可能科目用は、それぞれ別のApps Scriptプロジェクトで作成します。")
        },
        {
            "number": "5",
            "title": qsTr("メモ帳の内容をコピー＆ペースト"),
            "description": qsTr("空にしたCode.gsへ、メモ帳からコピーした.gsの全内容を貼り付けます。日付・コマ・フォーム名などは、アプリで設定した内容がコード内へ反映されています。"),
            "images": [
                {"source": "assets/google_forms_guide/05_paste_script.png", "accessible": qsTr("作成スクリプトをCode.gsへ貼り付けた画面"), "height": 360}
            ],
            "note": qsTr("貼り付けた後に先頭や末尾が欠けていないことを確認してください。")
        },
        {
            "number": "6",
            "title": qsTr("保存して作成関数を実行"),
            "description": qsTr("Ctrl＋Sまたはフロッピーディスクのボタンで保存します。関数が createStudentQuestionnaire になっていることを確認し、「実行」を押します。"),
            "images": [
                {"source": "assets/google_forms_guide/06_select_function.png", "accessible": qsTr("createStudentQuestionnaireを選択して実行する画面"), "height": 360}
            ],
            "note": qsTr("講師勤務日時用は createTeacherQuestionnaire、講師指導可能科目用は createTeacherSubjectQuestionnaire を選びます。Google Apps Scriptの「デプロイ」は不要です。")
        },
        {
            "number": "7",
            "title": qsTr("権限を確認"),
            "description": qsTr("初回実行時に「承認が必要です」と表示されたら、「権限を確認」を押して使用するGoogleアカウントを選択します。"),
            "images": [
                {"source": "assets/google_forms_guide/07_confirm_permissions.png", "accessible": qsTr("承認が必要ですダイアログの権限を確認ボタン"), "height": 260}
            ],
            "note": qsTr("自分でアプリから保存したコードを貼り付けたことを確認してから進んでください。第三者から受け取った不明なコードは実行しません。")
        },
        {
            "number": "8",
            "title": qsTr("詳細を表示し、安全ではないページへ移動"),
            "description": qsTr("「このアプリはGoogleで確認されていません」と表示された場合は「詳細」を押し、続いて「無題のプロジェクト（安全ではないページ）に移動」を押します。"),
            "images": [
                {"source": "assets/google_forms_guide/08_google_warning.png", "accessible": qsTr("Googleの未確認アプリ警告で詳細を押す画面"), "height": 440},
                {"source": "assets/google_forms_guide/08_continue_unsafe.png", "accessible": qsTr("安全ではないページに移動するリンクが表示された画面"), "height": 440}
            ],
            "note": qsTr("これは自分のGoogleアカウント内で作成した未公開スクリプトに対する警告です。コードの出所を確認できない場合は進まないでください。")
        },
        {
            "number": "9",
            "title": qsTr("すべて選択して続行"),
            "description": qsTr("アクセス権限の画面で「すべて選択」にチェックを入れ、フォームとスプレッドシートの権限内容を確認して「続行」を押します。"),
            "images": [
                {"source": "assets/google_forms_guide/09_select_all_continue.png", "accessible": qsTr("Googleのアクセス権限ですべて選択して続行する画面"), "height": 430}
            ],
            "note": qsTr("フォームと回答先スプレッドシートを自分のGoogleドライブへ作成するために必要な権限です。")
        },
        {
            "number": "10",
            "title": qsTr("実行ログのリンクからアンケートを開く"),
            "description": qsTr("実行が完了すると、実行ログにフォーム編集URL・回答URL・回答原本URLが表示されます。回答URLを開けばアンケートへ回答でき、生徒や講師へ案内できます。"),
            "images": [
                {"source": "assets/google_forms_guide/10_result_links.png", "accessible": qsTr("フォーム編集URLと回答URLと回答原本URLが表示された実行ログ"), "height": 480}
            ],
            "note": qsTr("配布前に回答URLを自分で開いてテストしてください。フォーム編集URLと回答原本URLは担当者だけで管理します。")
        }
    ]

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(1120, parent.width - 40)
    height: Math.min(780, parent.height - 40)
    modal: true
    title: qsTr("Googleフォーム作成手順（画像つき）")
    closePolicy: Popup.CloseOnEscape

    UiTheme { id: theme }

    contentItem: Loader {
        sourceComponent: guideContentComponent
    }

    footer: Rectangle {
        implicitHeight: 58
        color: theme.surface
        border.color: theme.border

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            spacing: 10

            Button {
                text: qsTr("別ウィンドウで表示")
                icon.name: "window-new"
                onClicked: {
                    root.close()
                    separateGuideWindow.show()
                    separateGuideWindow.raise()
                    separateGuideWindow.requestActivate()
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                text: qsTr("閉じる")
                onClicked: root.close()
            }
        }
    }

    Window {
        id: separateGuideWindow

        width: 1180
        height: 820
        minimumWidth: 760
        minimumHeight: 560
        visible: false
        title: qsTr("Googleフォーム作成手順")
        color: theme.appBackground

        Loader {
            anchors.fill: parent
            anchors.margins: 14
            sourceComponent: guideContentComponent
        }
    }

    Component {
        id: guideContentComponent

        ScrollView {
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
                message: qsTr("上から1～10の順に進めてください。説明と実際の画面を同じ場所にまとめています。Google側の表示は更新により多少異なる場合があります。")
            }

            Repeater {
                model: root.guideSteps

                delegate: Rectangle {
                    id: guideCard

                    required property var modelData

                    Layout.fillWidth: true
                    implicitHeight: guideContent.implicitHeight + 24
                    radius: 10
                    color: theme.surface
                    border.color: theme.border

                    ColumnLayout {
                        id: guideContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: 12
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 9

                            Rectangle {
                                Layout.preferredWidth: 34
                                Layout.preferredHeight: 34
                                radius: 17
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
                                font.pixelSize: 16
                                font.weight: Font.DemiBold
                                wrapMode: Text.WordWrap
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            text: guideCard.modelData.description
                            color: theme.textSecondary
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: guideCard.modelData.images.length > 1 ? 2 : 1
                            columnSpacing: 10
                            rowSpacing: 10

                            Repeater {
                                model: guideCard.modelData.images

                                delegate: Rectangle {
                                    id: screenshotFrame

                                    required property var modelData

                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Number(modelData.height)
                                    radius: 7
                                    color: "#f7f9fc"
                                    border.color: "#cfd9e8"
                                    clip: true

                                    Image {
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        source: screenshotFrame.modelData.source
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                        asynchronous: true
                                        Accessible.name: screenshotFrame.modelData.accessible
                                    }
                                }
                            }
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
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
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
}
