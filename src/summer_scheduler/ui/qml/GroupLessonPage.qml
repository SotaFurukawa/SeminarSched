pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function summaryValue(key) {
        return Number(root.rowValue(root.viewModel.groupImportSummary, key, 0))
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 20
        visible: !root.viewModel.hasOpenProject
        radius: 10
        color: "#ffffff"
        border.color: "#dce2ea"

        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(parent.width - 48, 520)
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: qsTr("プロジェクトが開かれていません")
                color: "#344054"
                font.pixelSize: 18
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("集団授業はプロジェクトごとの固定予定として保存します。先にホームからプロジェクトを開いてください。")
                color: "#667085"
                font.pixelSize: 11
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
            }
            Button {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("ホームへ移動")
                onClicked: root.openHomeRequested()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        visible: root.viewModel.hasOpenProject
        spacing: 9

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Label {
                    text: qsTr("集団授業")
                    color: "#18212f"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                }
                Label {
                    text: qsTr("任意の開始・終了時刻を持つ固定予定を取り込み、担当講師・受講生の時間重複を検証します。")
                    color: "#667085"
                    font.pixelSize: 10
                }
            }

            Button {
                text: qsTr("再読込み")
                onClicked: root.viewModel.refreshPhase3()
            }
            Button {
                text: qsTr("group_lessons.xlsxを保存…")
                onClicked: groupTemplateDialog.open()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: Boolean(root.viewModel.errorMessage)
                     || Boolean(root.viewModel.statusMessage)
            implicitHeight: groupMessage.implicitHeight + 16
            radius: 6
            color: root.viewModel.errorMessage ? "#fff6f5" : "#ecfdf3"
            border.color: root.viewModel.errorMessage ? "#e5aaa6" : "#a9dec0"

            Label {
                id: groupMessage

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                text: root.viewModel.errorMessage
                      ? qsTr("✕ %1").arg(root.viewModel.errorMessage)
                      : qsTr("✓ %1").arg(root.viewModel.statusMessage)
                color: root.viewModel.errorMessage ? "#a23b3b" : "#176b40"
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }
        }

        TabBar {
            id: groupTabs
            Layout.fillWidth: true

            TabButton {
                text: qsTr("登録済み一覧（%1件）")
                      .arg((root.viewModel.groupLessons || []).length)
            }
            TabButton {
                text: qsTr("Excel取込み・差分")
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: groupTabs.currentIndex

            Rectangle {
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 8

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        color: "#eef2f6"
                        border.color: "#dce2ea"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 9
                            anchors.rightMargin: 9
                            spacing: 7

                            Label {
                                Layout.preferredWidth: 86
                                text: qsTr("集団授業ID")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.preferredWidth: 52
                                text: qsTr("学年")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.preferredWidth: 140
                                text: qsTr("科目／コース")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.preferredWidth: 82
                                text: qsTr("日付")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.preferredWidth: 112
                                text: qsTr("時刻")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.preferredWidth: 110
                                text: qsTr("担当講師")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.preferredWidth: 50
                                text: qsTr("受講者")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.preferredWidth: 78
                                text: qsTr("教室")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.fillWidth: true
                                text: qsTr("備考")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                        }
                    }

                    ListView {
                        id: groupLessonList

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 1
                        model: root.viewModel.groupLessons || []
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            id: groupLessonDelegate

                            required property int index
                            required property var modelData
                            width: ListView.view.width
                            height: 43
                            color: index % 2 === 0 ? "#ffffff" : "#f8fafc"
                            border.color: "#edf0f4"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 9
                                anchors.rightMargin: 9
                                spacing: 7

                                Label {
                                    Layout.preferredWidth: 86
                                    text: root.rowValue(groupLessonDelegate.modelData,
                                                        "groupCode", "")
                                    color: "#344054"
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 52
                                    text: root.rowValue(groupLessonDelegate.modelData,
                                                        "grade", "")
                                    color: "#475467"
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                                ColumnLayout {
                                    Layout.preferredWidth: 140
                                    spacing: 0
                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(groupLessonDelegate.modelData,
                                                            "subjectName", "")
                                        color: "#344054"
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(groupLessonDelegate.modelData,
                                                            "courseName", "")
                                        color: "#7a8493"
                                        font.pixelSize: 8
                                        elide: Text.ElideRight
                                    }
                                }
                                Label {
                                    Layout.preferredWidth: 82
                                    text: root.rowValue(groupLessonDelegate.modelData,
                                                        "date", "")
                                    color: "#475467"
                                    font.pixelSize: 9
                                }
                                Label {
                                    Layout.preferredWidth: 112
                                    text: qsTr("%1～%2")
                                          .arg(root.rowValue(
                                                   groupLessonDelegate.modelData,
                                                   "startTime", ""))
                                          .arg(root.rowValue(
                                                   groupLessonDelegate.modelData,
                                                   "endTime", ""))
                                    color: "#475467"
                                    font.pixelSize: 9
                                }
                                Label {
                                    Layout.preferredWidth: 110
                                    text: root.rowValue(groupLessonDelegate.modelData,
                                                        "teacherName", qsTr("未設定"))
                                    color: "#344054"
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.preferredWidth: 50
                                    text: qsTr("%1名").arg(root.rowValue(
                                                               groupLessonDelegate.modelData,
                                                               "studentCount", 0))
                                    color: "#344054"
                                    font.pixelSize: 9
                                }
                                Label {
                                    Layout.preferredWidth: 78
                                    text: root.rowValue(groupLessonDelegate.modelData,
                                                        "room", "")
                                    color: "#475467"
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(groupLessonDelegate.modelData,
                                                        "note", "")
                                    color: "#667085"
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: groupLessonList.count === 0
                        text: qsTr("登録済みの集団授業はありません。Excel取込みタブから追加できます。")
                        color: "#7a8493"
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("集団授業は個別授業より先に固定予定として扱われます。コマと一致しない時刻も区間重複で判定します。")
                        color: "#52647d"
                        font.pixelSize: 9
                        wrapMode: Text.Wrap
                    }
                }
            }

            ColumnLayout {
                spacing: 8

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: groupSourceControls.implicitHeight + 18
                    radius: 8
                    color: "#ffffff"
                    border.color: "#dce2ea"

                    ColumnLayout {
                        id: groupSourceControls

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 7

                        RowLayout {
                            Layout.fillWidth: true

                            Button {
                                text: qsTr("group_lessons.xlsxを選択…")
                                highlighted: true
                                onClicked: groupSourceDialog.open()
                            }
                            Label {
                                Layout.fillWidth: true
                                text: root.viewModel.groupSourcePath || qsTr("ファイル未選択")
                                color: root.viewModel.groupSourcePath ? "#475467" : "#7a8493"
                                font.pixelSize: 9
                                elide: Text.ElideMiddle
                            }
                            Button {
                                text: qsTr("検証して差分を作成")
                                highlighted: true
                                enabled: Boolean(root.viewModel.groupSourcePath)
                                onClicked: {
                                    groupIncludeDeletes.checked = false
                                    root.viewModel.validateGroupImport()
                                }
                            }
                            Button {
                                text: qsTr("クリア")
                                enabled: Boolean(root.viewModel.groupSourcePath)
                                onClicked: {
                                    groupIncludeDeletes.checked = false
                                    root.viewModel.clearGroupImport()
                                }
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("必須シート：集団授業／受講者。ID・参照先・資格・開校日・時刻・講師／生徒の重複を検証します。")
                            color: "#52647d"
                            font.pixelSize: 9
                            wrapMode: Text.Wrap
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Repeater {
                        model: [
                            {"label": qsTr("追加"), "key": "addCount"},
                            {"label": qsTr("変更"), "key": "changeCount"},
                            {"label": qsTr("変更なし"), "key": "unchangedCount"},
                            {"label": qsTr("削除候補"), "key": "deleteCandidateCount"},
                            {"label": qsTr("エラー"), "key": "errorCount"},
                            {"label": qsTr("警告"), "key": "warningCount"}
                        ]

                        delegate: Rectangle {
                            id: groupSummaryDelegate

                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 43
                            radius: 6
                            color: root.rowValue(groupSummaryDelegate.modelData,
                                                 "key", "") === "errorCount"
                                   && root.summaryValue("errorCount") > 0
                                   ? "#fff6f5" : "#ffffff"
                            border.color: "#dce2ea"

                            Column {
                                anchors.centerIn: parent
                                spacing: 0
                                Label {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: root.rowValue(
                                              groupSummaryDelegate.modelData, "label", "")
                                    color: "#667085"
                                    font.pixelSize: 8
                                }
                                Label {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: root.summaryValue(root.rowValue(
                                                                groupSummaryDelegate.modelData,
                                                                "key", ""))
                                    color: "#344054"
                                    font.pixelSize: 14
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: "#ffffff"
                    border.color: "#dce2ea"
                    radius: 8

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 9
                        spacing: 5

                        TabBar {
                            id: groupResultTabs
                            Layout.fillWidth: true

                            TabButton {
                                text: qsTr("差分（%1）")
                                      .arg((root.viewModel.groupImportDiffs || []).length)
                            }
                            TabButton {
                                text: qsTr("エラー・警告（%1）")
                                      .arg((root.viewModel.groupImportIssues || []).length)
                            }
                        }

                        StackLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            currentIndex: groupResultTabs.currentIndex

                            Phase3DiffList {
                                rows: root.viewModel.groupImportDiffs
                                emptyText: qsTr("検証すると集団授業と受講者の差分を表示します。")
                            }
                            Phase3IssueList {
                                rows: root.viewModel.groupImportIssues
                                emptyText: qsTr("検証エラー・警告はありません。")
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("エラーが1件でもある場合は反映できません。削除候補は選択しない限り保持されます。")
                        color: "#667085"
                        font.pixelSize: 9
                    }

                    CheckBox {
                        id: groupIncludeDeletes
                        visible: root.summaryValue("deleteCandidateCount") > 0
                        text: qsTr("削除候補も反映")
                        Accessible.description: qsTr("チェックした場合のみ既存の集団授業を削除します")
                    }

                    Button {
                        text: qsTr("検証済み差分を反映…")
                        highlighted: true
                        enabled: root.viewModel.canApplyGroupImport
                        ToolTip.visible: hovered && !enabled
                        ToolTip.text: qsTr("エラーがある場合は反映できません。")
                        onClicked: groupApplyConfirmation.open()
                    }
                }
            }
        }
    }

    Dialogs.FileDialog {
        id: groupSourceDialog
        title: qsTr("集団授業ファイルを選択")
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: [qsTr("Excelブック (*.xlsx)")]
        onAccepted: {
            groupIncludeDeletes.checked = false
            root.viewModel.inspectGroupSource(selectedFile.toString())
            groupTabs.currentIndex = 1
        }
    }

    Dialogs.FileDialog {
        id: groupTemplateDialog
        title: qsTr("集団授業テンプレートを保存")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("Excelブック (*.xlsx)")]
        onAccepted: root.viewModel.exportGroupTemplate(selectedFile.toString())
    }

    Dialogs.MessageDialog {
        id: groupApplyConfirmation
        title: qsTr("集団授業の差分を反映")
        text: groupIncludeDeletes.checked
              ? qsTr("追加・変更に加えて、削除候補も反映しますか？")
              : qsTr("追加・変更を反映しますか？")
        informativeText: groupIncludeDeletes.checked
                         ? qsTr("削除候補%1件も削除します。担当講師・受講者を含む処理全体は1トランザクションで保存されます。")
                           .arg(root.summaryValue("deleteCandidateCount"))
                         : qsTr("削除候補は保持します。処理全体は1トランザクションで保存されます。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.applyGroupImport(groupIncludeDeletes.checked)
        }
    }
}
