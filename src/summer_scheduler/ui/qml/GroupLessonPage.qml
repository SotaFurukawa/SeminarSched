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
    property int calendarWeekOffset: 0
    property var selectedCalendarLesson: null

    UiTheme { id: theme }

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

    function parseIsoDate(value) {
        const parts = String(value || "").split("-")
        if (parts.length !== 3)
            return new Date()
        return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
    }

    function calendarBaseDate() {
        const dates = root.viewModel.groupDates || []
        if (dates.length > 0)
            return root.parseIsoDate(dates[0].value)
        return new Date()
    }

    function calendarDay(dayIndex) {
        const base = root.calendarBaseDate()
        const mondayOffset = (base.getDay() + 6) % 7
        base.setDate(base.getDate() - mondayOffset
                     + (root.calendarWeekOffset * 7) + dayIndex)
        return base
    }

    function isoDate(dateValue) {
        const year = dateValue.getFullYear()
        const month = String(dateValue.getMonth() + 1).padStart(2, "0")
        const day = String(dateValue.getDate()).padStart(2, "0")
        return year + "-" + month + "-" + day
    }

    function calendarDayIso(dayIndex) {
        return root.isoDate(root.calendarDay(dayIndex))
    }

    function calendarDayLabel(dayIndex) {
        const value = root.calendarDay(dayIndex)
        const weekdays = [qsTr("月"), qsTr("火"), qsTr("水"), qsTr("木"),
                          qsTr("金"), qsTr("土"), qsTr("日")]
        return qsTr("%1/%2（%3）")
                .arg(value.getMonth() + 1)
                .arg(value.getDate())
                .arg(weekdays[dayIndex])
    }

    function calendarWeekLabel() {
        return qsTr("%1 ～ %2")
                .arg(root.calendarDayLabel(0))
                .arg(root.calendarDayLabel(6))
    }

    function lessonsForDate(isoValue) {
        const rows = root.viewModel.groupLessons || []
        const result = []
        for (let index = 0; index < rows.length; index += 1) {
            if (String(root.rowValue(rows[index], "date", "")) === isoValue)
                result.push(rows[index])
        }
        result.sort((left, right) => String(root.rowValue(left, "startTime", ""))
                    .localeCompare(String(root.rowValue(right, "startTime", ""))))
        return result
    }

    function dateOptionIndex(isoValue) {
        const dates = root.viewModel.groupDates || []
        for (let index = 0; index < dates.length; index += 1) {
            if (String(dates[index].value) === isoValue)
                return index
        }
        return -1
    }

    function resetCalendarForm(isoValue) {
        const optionIndex = root.dateOptionIndex(isoValue)
        calendarDate.currentIndex = optionIndex >= 0 ? optionIndex : 0
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
    }

    function openCalendarCreate(isoValue) {
        if (root.dateOptionIndex(isoValue) < 0)
            return
        root.resetCalendarForm(isoValue)
        calendarCreateDialog.open()
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
                    root.resetCalendarForm(root.calendarDayIso(0))
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
                color: theme.surface
                border.color: theme.border
                radius: theme.radiusLg

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: theme.spacingMd
                    spacing: theme.spacingSm

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: theme.spacingSm

                        AppButton {
                            text: qsTr("‹ 前の週")
                            onClicked: root.calendarWeekOffset -= 1
                        }
                        AppButton {
                            text: qsTr("基準週")
                            onClicked: root.calendarWeekOffset = 0
                        }
                        Label {
                            Layout.fillWidth: true
                            text: root.calendarWeekLabel()
                            color: theme.textPrimary
                            font.pixelSize: theme.bodySize
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                        }
                        AppButton {
                            text: qsTr("次の週 ›")
                            onClicked: root.calendarWeekOffset += 1
                        }
                    }

                    InlineMessage {
                        Layout.fillWidth: true
                        kind: "info"
                        message: qsTr("空いている日付の「＋ 授業を追加」から登録できます。集団授業は個別授業より先に固定予定として扱われ、コマと一致しない時刻も区間重複で検証されます。")
                    }

                    GridLayout {
                        id: weeklyCalendar

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        columns: 7
                        columnSpacing: theme.spacingSm
                        rowSpacing: 0

                        Repeater {
                            model: 7

                            Rectangle {
                                id: calendarDayColumn

                                required property int index
                                readonly property string dayIso: root.calendarDayIso(index)
                                readonly property bool isOpenDate:
                                    root.dateOptionIndex(dayIso) >= 0
                                readonly property var dayLessons:
                                    root.lessonsForDate(dayIso)

                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.minimumWidth: 112
                                radius: theme.radiusMd
                                color: isOpenDate ? theme.surface : theme.surfaceSubtle
                                border.color: isOpenDate ? theme.borderStrong : theme.border

                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 0

                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 42
                                        radius: theme.radiusMd
                                        color: calendarDayColumn.isOpenDate
                                               ? theme.accentSoft : theme.surfaceSubtle

                                        Label {
                                            anchors.centerIn: parent
                                            text: root.calendarDayLabel(calendarDayColumn.index)
                                            color: calendarDayColumn.isOpenDate
                                                   ? theme.accent : theme.textSecondary
                                            font.pixelSize: theme.captionSize
                                            font.weight: Font.DemiBold
                                        }
                                    }

                                    ListView {
                                        id: calendarEventList

                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        Layout.margins: 6
                                        spacing: 6
                                        clip: true
                                        model: calendarDayColumn.dayLessons
                                        boundsBehavior: Flickable.StopAtBounds

                                        ScrollBar.vertical: ScrollBar {
                                            policy: ScrollBar.AsNeeded
                                        }

                                        delegate: Rectangle {
                                            id: calendarEventCard

                                            required property var modelData
                                            width: ListView.view.width
                                            height: eventCardContent.implicitHeight + 14
                                            radius: theme.radiusSm
                                            color: theme.accentSoft
                                            border.color: theme.accent

                                            ColumnLayout {
                                                id: eventCardContent

                                                anchors.left: parent.left
                                                anchors.right: parent.right
                                                anchors.verticalCenter: parent.verticalCenter
                                                anchors.margins: 7
                                                spacing: 1

                                                Label {
                                                    Layout.fillWidth: true
                                                    text: qsTr("%1～%2")
                                                          .arg(root.rowValue(
                                                                   calendarEventCard.modelData,
                                                                   "startTime", ""))
                                                          .arg(root.rowValue(
                                                                   calendarEventCard.modelData,
                                                                   "endTime", ""))
                                                    color: theme.accent
                                                    font.pixelSize: theme.captionSize
                                                    font.weight: Font.Bold
                                                }
                                                Label {
                                                    Layout.fillWidth: true
                                                    text: qsTr("%1 %2")
                                                          .arg(root.rowValue(
                                                                   calendarEventCard.modelData,
                                                                   "grade", ""))
                                                          .arg(root.rowValue(
                                                                   calendarEventCard.modelData,
                                                                   "subjectName", ""))
                                                    color: theme.textPrimary
                                                    font.pixelSize: theme.captionSize
                                                    font.weight: Font.DemiBold
                                                    wrapMode: Text.Wrap
                                                }
                                                Label {
                                                    Layout.fillWidth: true
                                                    text: root.rowValue(
                                                              calendarEventCard.modelData,
                                                              "teacherName", qsTr("担当未設定"))
                                                    color: theme.textSecondary
                                                    font.pixelSize: theme.captionSize
                                                    elide: Text.ElideRight
                                                }
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                Accessible.name: qsTr("集団授業の詳細を開く")
                                                onClicked: {
                                                    root.selectedCalendarLesson =
                                                            calendarEventCard.modelData
                                                    calendarDetailDialog.open()
                                                }
                                            }
                                        }
                                    }

                                    AppButton {
                                        Layout.fillWidth: true
                                        Layout.margins: 6
                                        text: calendarDayColumn.isOpenDate
                                              ? qsTr("＋ 授業を追加")
                                              : qsTr("授業日ではありません")
                                        enabled: calendarDayColumn.isOpenDate
                                        onClicked: root.openCalendarCreate(
                                                       calendarDayColumn.dayIso)
                                    }
                                }
                            }
                        }
                    }

                    EmptyState {
                        Layout.fillWidth: true
                        visible: (root.viewModel.groupLessons || []).length === 0
                        title: qsTr("登録済みの集団授業はありません")
                        description: qsTr("授業日の追加ボタン、またはExcel取込みから登録できます。")
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

    Dialog {
        id: calendarDetailDialog

        anchors.centerIn: Overlay.overlay
        width: Math.min(480, root.width - 48)
        modal: true
        title: qsTr("集団授業の詳細")
        standardButtons: Dialog.Close

        ColumnLayout {
            width: parent.width
            spacing: theme.spacingMd

            SectionHeader {
                Layout.fillWidth: true
                title: qsTr("%1 %2")
                       .arg(root.rowValue(root.selectedCalendarLesson, "grade", ""))
                       .arg(root.rowValue(root.selectedCalendarLesson,
                                          "subjectName", ""))
                description: root.rowValue(root.selectedCalendarLesson,
                                           "courseName", "")
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("%1　%2～%3")
                      .arg(root.rowValue(root.selectedCalendarLesson, "date", ""))
                      .arg(root.rowValue(root.selectedCalendarLesson,
                                         "startTime", ""))
                      .arg(root.rowValue(root.selectedCalendarLesson,
                                         "endTime", ""))
                color: theme.textPrimary
                font.pixelSize: theme.bodySize
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("担当講師：%1\n教室：%2\n受講者：%3名\n備考：%4")
                      .arg(root.rowValue(root.selectedCalendarLesson,
                                         "teacherName", qsTr("未設定")))
                      .arg(root.rowValue(root.selectedCalendarLesson, "room", "－"))
                      .arg(root.rowValue(root.selectedCalendarLesson,
                                         "studentCount", 0))
                      .arg(root.rowValue(root.selectedCalendarLesson, "note", "－"))
                color: theme.textSecondary
                font.pixelSize: theme.captionSize
                wrapMode: Text.Wrap
            }
            InlineMessage {
                Layout.fillWidth: true
                kind: "info"
                message: qsTr("変更が必要な場合は、監査履歴を保つため一度削除してから登録し直してください。")
            }
            AppButton {
                Layout.alignment: Qt.AlignRight
                text: qsTr("この予定を削除")
                onClicked: {
                    root.pendingDeleteId = Number(root.rowValue(
                                root.selectedCalendarLesson, "id", 0))
                    calendarDetailDialog.close()
                    deleteCalendarConfirmation.open()
                }
            }
        }
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
