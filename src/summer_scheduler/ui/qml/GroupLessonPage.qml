pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested
    property int pendingDeleteId: 0

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function summaryValue(key) {
        return Number(root.rowValue(root.viewModel.groupImportSummary, key, 0))
    }

    function teacherOptions() {
        const result = [{"externalId": "", "label": qsTr("担当講師なし")}]
        const rows = root.viewModel.groupTeachers || []
        for (let index = 0; index < rows.length; index += 1)
            result.push(rows[index])
        return result
    }

    function subjectOptionsForGrade(grade) {
        const prefix = String(grade).startsWith("小") ? "小学校・"
                     : String(grade).startsWith("中") ? "中学校・"
                     : "高校・"
        const result = []
        const rows = root.viewModel.groupSubjects || []
        for (let index = 0; index < rows.length; index += 1) {
            if (String(rows[index].label).startsWith(prefix))
                result.push(rows[index])
        }
        return result
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
                text: qsTr("＋ カレンダーに追加")
                highlighted: true
                enabled: (root.viewModel.groupDates || []).length > 0
                onClicked: {
                    calendarDate.currentIndex = 0
                    calendarGrade.currentIndex = 0
                    calendarSubject.currentIndex = 0
                    calendarSlot.currentIndex = 0
                    calendarTeacher.currentIndex = 0
                    if (calendarSlot.count > 0) {
                        calendarStart.text = calendarSlot.model[0].start
                        calendarEnd.text = calendarSlot.model[0].end
                    }
                    calendarCourse.text = ""
                    calendarRoom.text = ""
                    calendarNote.text = ""
                    calendarCreateDialog.open()
                }
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
                text: qsTr("カレンダー（%1件）")
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
                            color: index % 2 === 0 ? "#ffffff" : "#f6f9fd"
                            border.color: "#edf0f4"

                            Rectangle {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                width: 4
                                color: "#4285f4"
                            }

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
                                ToolButton {
                                    text: qsTr("削除")
                                    Accessible.name: qsTr("この集団授業を削除")
                                    onClicked: {
                                        root.pendingDeleteId = Number(root.rowValue(
                                                    groupLessonDelegate.modelData, "id", 0))
                                        deleteCalendarConfirmation.open()
                                    }
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

    Dialog {
        id: calendarCreateDialog
        anchors.centerIn: Overlay.overlay
        width: Math.min(620, root.width - 48)
        modal: true
        title: qsTr("集団授業をカレンダーへ追加")
        standardButtons: Dialog.Ok | Dialog.Cancel

        GridLayout {
            width: parent.width
            columns: 2
            columnSpacing: 12
            rowSpacing: 8

            Label { text: qsTr("授業日（必須）") }
            ComboBox {
                id: calendarDate
                Layout.fillWidth: true
                model: root.viewModel.groupDates || []
                textRole: "label"
                valueRole: "value"
            }
            Label { text: qsTr("学年（必須）") }
            ComboBox {
                id: calendarGrade
                Layout.fillWidth: true
                model: ["小1", "小2", "小3", "小4", "小5", "小6",
                        "中1", "中2", "中3", "高1", "高2", "高3"]
            }
            Label { text: qsTr("科目（必須）") }
            ComboBox {
                id: calendarSubject
                Layout.fillWidth: true
                model: root.subjectOptionsForGrade(calendarGrade.currentText)
                textRole: "label"
                valueRole: "code"
            }
            Label { text: qsTr("標準コマ") }
            ComboBox {
                id: calendarSlot
                Layout.fillWidth: true
                model: root.viewModel.groupSlots || []
                textRole: "label"
                valueRole: "code"
                onActivated: {
                    calendarStart.text = model[currentIndex].start
                    calendarEnd.text = model[currentIndex].end
                }
            }
            Label { text: qsTr("開始・終了（必須）") }
            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: calendarStart
                    Layout.fillWidth: true
                    placeholderText: "17:10"
                }
                Label { text: qsTr("～") }
                TextField {
                    id: calendarEnd
                    Layout.fillWidth: true
                    placeholderText: "18:30"
                }
            }
            Label { text: qsTr("担当講師") }
            ComboBox {
                id: calendarTeacher
                Layout.fillWidth: true
                model: root.teacherOptions()
                textRole: "label"
                valueRole: "externalId"
            }
            Label { text: qsTr("コース名") }
            TextField {
                id: calendarCourse
                Layout.fillWidth: true
                placeholderText: qsTr("例：中3受験数学")
            }
            Label { text: qsTr("教室") }
            TextField {
                id: calendarRoom
                Layout.fillWidth: true
                placeholderText: qsTr("任意")
            }
            Label { text: qsTr("備考") }
            TextField {
                id: calendarNote
                Layout.fillWidth: true
                placeholderText: qsTr("任意")
            }
        }

        onAccepted: root.viewModel.createCalendarGroupLesson(
                        String(calendarGrade.currentText),
                        String(calendarSubject.currentValue || ""),
                        String(calendarDate.currentValue || ""),
                        calendarStart.text.trim(),
                        calendarEnd.text.trim(),
                        calendarCourse.text.trim(),
                        String(calendarTeacher.currentValue || ""),
                        calendarRoom.text.trim(),
                        calendarNote.text.trim())
    }

    Dialogs.MessageDialog {
        id: deleteCalendarConfirmation
        title: qsTr("集団授業を削除")
        text: qsTr("選択した集団授業を削除しますか？")
        informativeText: qsTr("この操作はプロジェクトの監査履歴に記録されます。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes && root.pendingDeleteId > 0)
                root.viewModel.deleteCalendarGroupLesson(root.pendingDeleteId)
            root.pendingDeleteId = 0
        }
    }
}
