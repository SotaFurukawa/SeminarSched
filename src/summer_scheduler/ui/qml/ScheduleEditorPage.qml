pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested
    signal openOptimizationRequested

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function dropColor(cellKey) {
        if (root.rowValue(root.viewModel.dropPreview, "targetKey", "") !== cellKey)
            return "#ffffff"
        const decision = root.rowValue(root.viewModel.dropPreview, "decision", "")
        if (decision === "green")
            return "#e8f8ef"
        if (decision === "yellow")
            return "#fff8df"
        if (decision === "red")
            return "#fff0ef"
        return "#ffffff"
    }

    function dropBorder(cellKey) {
        if (root.rowValue(root.viewModel.dropPreview, "targetKey", "") !== cellKey)
            return "#dce2ea"
        const decision = root.rowValue(root.viewModel.dropPreview, "decision", "")
        if (decision === "green")
            return "#2d8a57"
        if (decision === "yellow")
            return "#b7791f"
        return "#c33b35"
    }

    function requestDrop(lesson, targetDate, targetSlotId, targetTeacherId) {
        const outcome = root.viewModel.dropMove(
                          Number(root.rowValue(lesson, "lessonRequestId", 0)),
                          Number(root.rowValue(lesson, "sessionIndex", 0)),
                          String(targetDate),
                          Number(targetSlotId),
                          Number(targetTeacherId))
        if (outcome === "yellow")
            softWarningDialog.open()
    }

    function findById(rows, value) {
        const target = Number(value)
        for (let index = 0; index < rows.length; ++index) {
            if (Number(root.rowValue(rows[index], "id", -1)) === target)
                return index
        }
        return -1
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
            width: Math.min(parent.width - 48, 540)
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
                text: qsTr("時間割を確認・編集するには、ホームからプロジェクトを開いてください。")
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
        anchors.margins: 12
        visible: root.viewModel.hasOpenProject
        spacing: 7

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Label {
                    text: qsTr("時間割編集")
                    color: "#18212f"
                    font.pixelSize: 22
                    font.weight: Font.Bold
                }
                Label {
                    text: qsTr("ドラッグ前検証、ロック、Undo / Redoを同じ保存済みデータに適用します。")
                    color: "#667085"
                    font.pixelSize: 9
                }
            }

            Label {
                text: root.viewModel.saveStateText
                color: root.viewModel.hasUnsavedChanges ? "#8a5a00" : "#176b40"
                font.pixelSize: 10
                font.weight: Font.DemiBold
            }
            Button {
                text: qsTr("手動保存")
                Accessible.name: qsTr("現在の時間割をバックアップとして手動保存")
                onClicked: root.viewModel.manualSave()
            }
            Button {
                text: qsTr("↶ Undo")
                enabled: root.viewModel.canUndo
                Accessible.name: qsTr("直前の時間割編集を元に戻す")
                onClicked: root.viewModel.undo()
            }
            Button {
                text: qsTr("↷ Redo")
                enabled: root.viewModel.canRedo
                Accessible.name: qsTr("取り消した時間割編集をやり直す")
                onClicked: root.viewModel.redo()
            }
            Button {
                text: qsTr("ロック以外を再最適化")
                highlighted: true
                onClicked: {
                    if (root.viewModel.prepareReoptimization())
                        reoptimizationDialog.open()
                }
            }
        }

        StatusBanner {
            Layout.fillWidth: true
            viewModel: root.viewModel
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: filterRow.implicitHeight + 12
            radius: 7
            color: "#ffffff"
            border.color: "#dce2ea"

            RowLayout {
                id: filterRow

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 6

                TextField {
                    id: searchField

                    Layout.preferredWidth: 190
                    placeholderText: qsTr("生徒名・講師名を検索")
                    Accessible.name: qsTr("時間割検索")
                    onTextChanged: root.viewModel.setSearchQuery(text)
                }
                ComboBox {
                    id: gradeFilter

                    Layout.preferredWidth: 105
                    model: root.viewModel.gradeOptions
                    textRole: "label"
                    valueRole: "value"
                    onActivated: root.viewModel.setGradeFilter(currentValue)
                    Accessible.name: qsTr("学年絞込み")
                }
                ComboBox {
                    id: subjectFilter

                    Layout.preferredWidth: 130
                    model: root.viewModel.subjectOptions
                    textRole: "label"
                    valueRole: "value"
                    onActivated: root.viewModel.setSubjectFilter(currentValue)
                    Accessible.name: qsTr("科目絞込み")
                }
                CheckBox {
                    text: qsTr("1対1")
                    onToggled: root.viewModel.setFlagFilter("oneToOne", checked)
                }
                CheckBox {
                    text: qsTr("優先度5")
                    onToggled: root.viewModel.setFlagFilter("priority5", checked)
                }
                CheckBox {
                    text: qsTr("警告")
                    onToggled: root.viewModel.setFlagFilter("warning", checked)
                }
                CheckBox {
                    text: qsTr("ロック")
                    onToggled: root.viewModel.setFlagFilter("locked", checked)
                }
                CheckBox {
                    text: qsTr("未配置のみ")
                    onToggled: root.viewModel.setFlagFilter("unassigned", checked)
                }
                Item {
                    Layout.fillWidth: true
                }
                Label {
                    text: qsTr("拡大")
                    color: "#667085"
                    font.pixelSize: 9
                }
                Slider {
                    Layout.preferredWidth: 105
                    from: 0.75
                    to: 1.5
                    stepSize: 0.05
                    value: root.viewModel.zoomFactor
                    Accessible.name: qsTr("時間割の拡大縮小")
                    onMoved: root.viewModel.setZoomFactor(value)
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: dateControls.implicitHeight + 10
            radius: 7
            color: "#ffffff"
            border.color: "#dce2ea"

            RowLayout {
                id: dateControls

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 7
                anchors.rightMargin: 7
                spacing: 5

                Button {
                    text: qsTr("‹ 前日")
                    enabled: root.viewModel.canGoPreviousDate
                    onClicked: root.viewModel.previousDate()
                }
                Button {
                    text: qsTr("翌日 ›")
                    enabled: root.viewModel.canGoNextDate
                    onClicked: root.viewModel.nextDate()
                }
                Button {
                    text: qsTr("📅 %1").arg(root.viewModel.currentDate || qsTr("日付選択"))
                    Accessible.name: qsTr("カレンダーから日付を選択")
                    onClicked: calendarPopup.open()

                    Popup {
                        id: calendarPopup

                        y: parent.height + 3
                        width: 300
                        height: 290
                        modal: true
                        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

                        MonthGrid {
                            anchors.fill: parent
                            month: {
                                const value = new Date(root.viewModel.currentDate + "T12:00:00")
                                return isNaN(value.getTime()) ? new Date().getMonth()
                                                             : value.getMonth()
                            }
                            year: {
                                const value = new Date(root.viewModel.currentDate + "T12:00:00")
                                return isNaN(value.getTime()) ? new Date().getFullYear()
                                                             : value.getFullYear()
                            }
                            onClicked: function (dateValue) {
                                root.viewModel.selectDate(
                                            Qt.formatDate(dateValue, "yyyy-MM-dd"))
                                calendarPopup.close()
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 25
                    color: "#dce2ea"
                }
                Button {
                    text: qsTr("日表示")
                    checkable: true
                    checked: root.viewModel.viewMode === "day"
                    onClicked: root.viewModel.setViewMode("day")
                }
                Button {
                    text: qsTr("複数日サマリー")
                    checkable: true
                    checked: root.viewModel.viewMode === "multiple"
                    onClicked: root.viewModel.setViewMode("multiple")
                }

                ListView {
                    id: dateTabs

                    Layout.fillWidth: true
                    Layout.preferredHeight: 34
                    orientation: ListView.Horizontal
                    spacing: 3
                    clip: true
                    model: root.viewModel.dateTabs
                    boundsBehavior: Flickable.StopAtBounds

                    delegate: Rectangle {
                        id: dateTab

                        required property var modelData
                        width: 106
                        height: dateTabs.height
                        radius: 5
                        color: dateTabDrop.containsDrag
                               ? root.dropColor(
                                     root.rowValue(
                                         root.viewModel.dropPreview,
                                         "targetKey", ""))
                               : root.rowValue(
                                     dateTab.modelData, "selected", false)
                                 ? "#e8f0fb" : "#f8fafc"
                        border.width: dateTabDrop.containsDrag ? 2 : 1
                        border.color: dateTabDrop.containsDrag
                                      ? root.dropBorder(
                                            root.rowValue(
                                                root.viewModel.dropPreview,
                                                "targetKey", ""))
                                      : root.rowValue(
                                            dateTab.modelData, "selected", false)
                                        ? "#6c99d0" : "#dce2ea"
                        ToolTip.visible: dateTabDrop.containsDrag
                        ToolTip.delay: 0
                        ToolTip.text: root.rowValue(
                                          root.viewModel.dropPreview,
                                          "message", qsTr("移動先を検証中です"))

                        Label {
                            anchors.centerIn: parent
                            text: (dateTabDrop.containsDrag
                                   ? root.rowValue(
                                         root.viewModel.dropPreview,
                                         "icon", "…") + " "
                                   : "")
                                  + root.rowValue(
                                      dateTab.modelData, "label", "")
                            color: "#344054"
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                        }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: root.viewModel.selectDate(
                                           root.rowValue(dateTab.modelData, "date", ""))
                        }
                        DropArea {
                            id: dateTabDrop

                            anchors.fill: parent
                            keys: ["scheduleLesson"]
                            onEntered: function (drag) {
                                const lesson = root.rowValue(
                                                 drag.source,
                                                 "lessonData", null)
                                if (!lesson)
                                    return
                                root.viewModel.previewMove(
                                            Number(root.rowValue(
                                                       lesson, "lessonRequestId", 0)),
                                            Number(root.rowValue(
                                                       lesson, "sessionIndex", 0)),
                                            String(root.rowValue(
                                                       dateTab.modelData, "date", "")),
                                            Number(root.rowValue(
                                                       lesson, "timeSlotId", 0)),
                                            Number(root.rowValue(
                                                       lesson, "teacherId", 0)))
                            }
                            onDropped: function (drop) {
                                const lesson = root.rowValue(
                                                 drop.source,
                                                 "lessonData", null)
                                if (!lesson)
                                    return
                                root.requestDrop(
                                            lesson,
                                            root.rowValue(
                                                dateTab.modelData, "date", ""),
                                            root.rowValue(
                                                lesson, "timeSlotId", 0),
                                            root.rowValue(lesson, "teacherId", 0))
                                drop.acceptProposedAction()
                            }
                            onExited: root.viewModel.clearDropPreview()
                        }
                    }
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.preferredWidth: 238
                SplitView.minimumWidth: 210
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 7

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("未配置の授業")
                            color: "#344054"
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                        StatusBadge {
                            label: String(root.viewModel.unassignedCount)
                            status: root.viewModel.unassignedCount > 0
                                    ? "warning" : "complete"
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("カードを時間割へドラッグしてください")
                        color: "#667085"
                        font.pixelSize: 8
                        wrapMode: Text.Wrap
                    }

                    ListView {
                        id: unassignedRail

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 5
                        model: root.viewModel.unassignedLessons
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            id: unassignedRailCard

                            required property var modelData
                            property var lessonData: modelData
                            property real homeX: 0
                            property real homeY: 0
                            width: ListView.view.width
                            height: 82
                            radius: 6
                            color: root.rowValue(modelData, "matchesFilter", true)
                                   ? "#fff8f6" : "#f3f4f6"
                            opacity: root.rowValue(modelData, "matchesFilter", true)
                                     ? 1 : 0.35
                            border.color: "#e1aaa5"
                            Drag.active: unassignedRailDrag.drag.active
                            Drag.source: unassignedRailCard
                            Drag.keys: ["scheduleLesson"]

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 7
                                spacing: 2
                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(unassignedRailCard.modelData,
                                                        "studentName", "")
                                          + " / "
                                          + root.rowValue(unassignedRailCard.modelData,
                                                          "subjectShortName", "")
                                    color: "#592c29"
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("残り%1回・候補%2件")
                                          .arg(root.rowValue(
                                                   unassignedRailCard.modelData,
                                                   "remainingCount", 1))
                                          .arg(root.rowValue(
                                                   unassignedRailCard.modelData,
                                                   "candidateCount", 0))
                                    color: "#667085"
                                    font.pixelSize: 8
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(unassignedRailCard.modelData,
                                                        "reasonText",
                                                        qsTr("未配置理由を取得できません"))
                                    color: "#7d2925"
                                    font.pixelSize: 8
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                }
                            }

                            MouseArea {
                                id: unassignedRailDrag

                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.OpenHandCursor
                                drag.target: unassignedRailCard
                                onPressed: {
                                    unassignedRailCard.homeX = unassignedRailCard.x
                                    unassignedRailCard.homeY = unassignedRailCard.y
                                }
                                onClicked: root.viewModel.selectLesson(
                                               Number(root.rowValue(
                                                          unassignedRailCard.modelData,
                                                          "lessonRequestId", 0)),
                                               Number(root.rowValue(
                                                          unassignedRailCard.modelData,
                                                          "sessionIndex", 0)))
                                onReleased: {
                                    unassignedRailCard.Drag.drop()
                                    unassignedRailCard.x = unassignedRailCard.homeX
                                    unassignedRailCard.y = unassignedRailCard.homeY
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: unassignedRail.count === 0
                            text: qsTr("未配置授業はありません")
                            color: "#667085"
                            font.pixelSize: 10
                        }
                    }
                }
            }

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 540
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 7

                StackLayout {
                    anchors.fill: parent
                    anchors.margins: 7
                    currentIndex: root.viewModel.viewMode === "day" ? 0 : 1

                    GridLayout {
                        columns: 2
                        columnSpacing: 0
                        rowSpacing: 0

                        Rectangle {
                            Layout.preferredWidth: 66
                            Layout.preferredHeight: 38
                            color: "#eef2f6"
                            border.color: "#dce2ea"
                            Label {
                                anchors.centerIn: parent
                                text: qsTr("コマ＼講師")
                                color: "#475467"
                                font.pixelSize: 8
                            }
                        }

                        HorizontalHeaderView {
                            id: teacherHeader

                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            syncView: scheduleTable
                            clip: true
                            reuseItems: true
                            delegate: Rectangle {
                                required property var display
                                implicitWidth: 196 * root.viewModel.zoomFactor
                                implicitHeight: teacherHeader.height
                                color: "#eef2f6"
                                border.color: "#dce2ea"
                                Label {
                                    anchors.fill: parent
                                    anchors.margins: 5
                                    text: String(parent.display || "")
                                    color: "#344054"
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        VerticalHeaderView {
                            id: slotHeader

                            Layout.preferredWidth: 66
                            Layout.fillHeight: true
                            syncView: scheduleTable
                            clip: true
                            reuseItems: true
                            delegate: Rectangle {
                                required property var display
                                implicitWidth: slotHeader.width
                                implicitHeight: 124 * root.viewModel.zoomFactor
                                color: "#eef2f6"
                                border.color: "#dce2ea"
                                Label {
                                    anchors.centerIn: parent
                                    text: String(parent.display || "")
                                    color: "#344054"
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }

                        TableView {
                            id: scheduleTable

                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            model: root.viewModel.gridModel
                            reuseItems: true
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            columnSpacing: 1
                            rowSpacing: 1
                            columnWidthProvider: function (_column) {
                                return 196 * root.viewModel.zoomFactor
                            }
                            rowHeightProvider: function (_row) {
                                return 124 * root.viewModel.zoomFactor
                            }

                            ScrollBar.horizontal: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }
                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }

                            delegate: Rectangle {
                                id: scheduleCell

                                required property var cellData
                                required property int row
                                required property int column
                                implicitWidth: 196 * root.viewModel.zoomFactor
                                implicitHeight: 124 * root.viewModel.zoomFactor
                                color: root.dropColor(
                                           root.rowValue(
                                               scheduleCell.cellData,
                                               "cellKey", ""))
                                border.width: cellDrop.containsDrag ? 2 : 1
                                border.color: root.dropBorder(
                                                  root.rowValue(
                                                      scheduleCell.cellData,
                                                      "cellKey", ""))

                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 3
                                    spacing: 3

                                    Repeater {
                                        model: root.rowValue(
                                                   scheduleCell.cellData,
                                                   "groupLessons", [])

                                        delegate: Rectangle {
                                            id: groupCard

                                            required property var modelData
                                            width: scheduleCell.width - 6
                                            height: 26 * root.viewModel.zoomFactor
                                            radius: 4
                                            color: "#fff1dc"
                                            border.color: "#d68b27"
                                            Label {
                                                anchors.fill: parent
                                                anchors.margins: 4
                                                text: qsTr("集団 ◉ %1")
                                                      .arg(root.rowValue(
                                                               groupCard.modelData,
                                                               "courseName", ""))
                                                color: "#814c05"
                                                font.pixelSize: 8
                                                font.weight: Font.DemiBold
                                                elide: Text.ElideRight
                                            }
                                        }
                                    }

                                    Repeater {
                                        model: root.rowValue(
                                                   scheduleCell.cellData,
                                                   "lessonCards", [])

                                        delegate: Rectangle {
                                            id: lessonCard

                                            required property var modelData
                                            property var lessonData: modelData
                                            property real homeX: 0
                                            property real homeY: 0
                                            width: scheduleCell.width - 6
                                            height: 40 * root.viewModel.zoomFactor
                                            radius: 5
                                            opacity: root.rowValue(
                                                         lessonCard.modelData,
                                                         "matchesFilter", true) ? 1 : 0.3
                                            color: root.rowValue(
                                                       lessonCard.modelData,
                                                       "hasWarning", false)
                                                   ? "#fff8df" : "#eef5ff"
                                            border.width: root.rowValue(
                                                              lessonCard.modelData,
                                                              "isLocked", false) ? 2 : 1
                                            border.color: root.rowValue(
                                                              lessonCard.modelData,
                                                              "isLocked", false)
                                                          ? "#6b55a3" : "#91b4dc"
                                            z: cardDrag.drag.active ? 10 : 1
                                            Drag.active: cardDrag.drag.active
                                            Drag.source: lessonCard
                                            Drag.keys: ["scheduleLesson"]
                                            Drag.hotSpot.x: width / 2
                                            Drag.hotSpot.y: height / 2

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 5
                                                anchors.rightMargin: 5
                                                spacing: 3
                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 0
                                                    Label {
                                                        Layout.fillWidth: true
                                                        text: root.rowValue(
                                                                  lessonCard.modelData,
                                                                  "studentName", "")
                                                              + " "
                                                              + root.rowValue(
                                                                  lessonCard.modelData,
                                                                  "grade", "")
                                                        color: "#23344b"
                                                        font.pixelSize: 8
                                                        font.weight: Font.DemiBold
                                                        elide: Text.ElideRight
                                                    }
                                                    Label {
                                                        Layout.fillWidth: true
                                                        text: root.rowValue(
                                                                  lessonCard.modelData,
                                                                  "subjectShortName", "")
                                                        color: "#52657c"
                                                        font.pixelSize: 7
                                                        elide: Text.ElideRight
                                                    }
                                                }
                                                Label {
                                                    text: (root.rowValue(
                                                               lessonCard.modelData,
                                                               "oneToOneRequired", false)
                                                           ? "① " : "")
                                                          + (root.rowValue(
                                                                 lessonCard.modelData,
                                                                 "isPriorityFive", false)
                                                             ? "P5 " : "")
                                                          + (root.rowValue(
                                                                 lessonCard.modelData,
                                                                 "isLocked", false)
                                                             ? "🔒 " : "")
                                                          + (root.rowValue(
                                                                 lessonCard.modelData,
                                                                 "isManual", false)
                                                             ? "✎ " : "")
                                                          + (root.rowValue(
                                                                 lessonCard.modelData,
                                                                 "hasWarning", false)
                                                             ? "⚠" : "")
                                                    color: "#765c12"
                                                    font.pixelSize: 8
                                                }
                                            }

                                            MouseArea {
                                                id: cardDrag

                                                anchors.fill: parent
                                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                                hoverEnabled: true
                                                drag.target: lessonCard
                                                onPressed: function (mouse) {
                                                    lessonCard.homeX = lessonCard.x
                                                    lessonCard.homeY = lessonCard.y
                                                    if (mouse.button === Qt.RightButton) {
                                                        root.viewModel.selectLesson(
                                                                    Number(root.rowValue(
                                                                               lessonCard.modelData,
                                                                               "lessonRequestId",
                                                                               0)),
                                                                    Number(root.rowValue(
                                                                               lessonCard.modelData,
                                                                               "sessionIndex",
                                                                               0)))
                                                        detailDialog.open()
                                                    }
                                                }
                                                onClicked: root.viewModel.selectLesson(
                                                               Number(root.rowValue(
                                                                          lessonCard.modelData,
                                                                          "lessonRequestId", 0)),
                                                               Number(root.rowValue(
                                                                          lessonCard.modelData,
                                                                          "sessionIndex", 0)))
                                                onDoubleClicked: {
                                                    root.viewModel.selectLesson(
                                                                Number(root.rowValue(
                                                                           lessonCard.modelData,
                                                                           "lessonRequestId", 0)),
                                                                Number(root.rowValue(
                                                                           lessonCard.modelData,
                                                                           "sessionIndex", 0)))
                                                    detailDialog.open()
                                                }
                                                onReleased: {
                                                    lessonCard.Drag.drop()
                                                    lessonCard.x = lessonCard.homeX
                                                    lessonCard.y = lessonCard.homeY
                                                }
                                            }
                                            ToolTip.visible: cardDrag.containsMouse
                                            ToolTip.delay: 500
                                            ToolTip.text: root.rowValue(
                                                              lessonCard.modelData,
                                                              "detailText",
                                                              qsTr("詳細を取得できません"))
                                        }
                                    }
                                }

                                DropArea {
                                    id: cellDrop

                                    anchors.fill: parent
                                    keys: ["scheduleLesson"]
                                    onEntered: function (drag) {
                                        const lesson = root.rowValue(
                                                         drag.source,
                                                         "lessonData", null)
                                        if (!lesson)
                                            return
                                        root.viewModel.previewMove(
                                                    Number(root.rowValue(
                                                               lesson,
                                                               "lessonRequestId", 0)),
                                                    Number(root.rowValue(
                                                               lesson,
                                                               "sessionIndex", 0)),
                                                    String(root.rowValue(
                                                               scheduleCell.cellData,
                                                               "date", "")),
                                                    Number(root.rowValue(
                                                               scheduleCell.cellData,
                                                               "timeSlotId", 0)),
                                                    Number(root.rowValue(
                                                               scheduleCell.cellData,
                                                               "teacherId", 0)))
                                    }
                                    onDropped: function (drop) {
                                        const lesson = root.rowValue(
                                                         drop.source,
                                                         "lessonData", null)
                                        if (!lesson)
                                            return
                                        root.requestDrop(
                                                    lesson,
                                                    root.rowValue(
                                                        scheduleCell.cellData,
                                                        "date", ""),
                                                    root.rowValue(
                                                        scheduleCell.cellData,
                                                        "timeSlotId", 0),
                                                    root.rowValue(
                                                        scheduleCell.cellData,
                                                        "teacherId", 0))
                                        drop.acceptProposedAction()
                                    }
                                    onExited: root.viewModel.clearDropPreview()
                                }

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    anchors.margins: 3
                                    visible: cellDrop.containsDrag
                                    height: previewText.implicitHeight + 6
                                    radius: 3
                                    color: root.dropColor(
                                               root.rowValue(
                                                   scheduleCell.cellData,
                                                   "cellKey", ""))
                                    border.color: root.dropBorder(
                                                      root.rowValue(
                                                          scheduleCell.cellData,
                                                          "cellKey", ""))
                                    Label {
                                        id: previewText

                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.leftMargin: 4
                                        anchors.rightMargin: 4
                                        text: root.rowValue(
                                                  root.viewModel.dropPreview,
                                                  "icon", "…")
                                              + " "
                                              + root.rowValue(
                                                  root.viewModel.dropPreview,
                                                  "message", qsTr("検証中"))
                                        color: "#344054"
                                        font.pixelSize: 7
                                        wrapMode: Text.Wrap
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }
                    }

                    ListView {
                        id: multipleDaySummary

                        clip: true
                        spacing: 6
                        model: root.viewModel.daySummaries
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            id: summaryDay

                            required property var modelData
                            width: multipleDaySummary.width
                            height: 76
                            radius: 6
                            color: "#f8fafc"
                            border.color: "#dce2ea"

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 12
                                Label {
                                    Layout.preferredWidth: 130
                                    text: root.rowValue(
                                              summaryDay.modelData, "label", "")
                                    color: "#344054"
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                }
                                Repeater {
                                    model: [
                                        {
                                            "label": qsTr("配置"),
                                            "value": root.rowValue(
                                                         summaryDay.modelData,
                                                         "assignmentCount", 0)
                                        },
                                        {
                                            "label": qsTr("1対2枠"),
                                            "value": root.rowValue(
                                                         summaryDay.modelData,
                                                         "pairedCellCount", 0)
                                        },
                                        {
                                            "label": qsTr("集団"),
                                            "value": root.rowValue(
                                                         summaryDay.modelData,
                                                         "groupLessonCount", 0)
                                        },
                                        {
                                            "label": qsTr("警告"),
                                            "value": root.rowValue(
                                                         summaryDay.modelData,
                                                         "warningCount", 0)
                                        },
                                        {
                                            "label": qsTr("ロック"),
                                            "value": root.rowValue(
                                                         summaryDay.modelData,
                                                         "lockCount", 0)
                                        }
                                    ]
                                    delegate: ColumnLayout {
                                        id: summaryMetric

                                        required property var modelData
                                        Layout.fillWidth: true
                                        spacing: 0
                                        Label {
                                            Layout.alignment: Qt.AlignHCenter
                                            text: root.rowValue(
                                                      summaryMetric.modelData,
                                                      "value", 0)
                                            color: "#344054"
                                            font.pixelSize: 17
                                            font.weight: Font.Bold
                                        }
                                        Label {
                                            Layout.alignment: Qt.AlignHCenter
                                            text: root.rowValue(
                                                      summaryMetric.modelData,
                                                      "label", "")
                                            color: "#667085"
                                            font.pixelSize: 8
                                        }
                                    }
                                }
                                Button {
                                    text: qsTr("この日を開く")
                                    onClicked: {
                                        root.viewModel.selectDate(
                                                    root.rowValue(
                                                        summaryDay.modelData,
                                                        "date", ""))
                                        root.viewModel.setViewMode("day")
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                SplitView.preferredWidth: 350
                SplitView.minimumWidth: 300
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 7

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 5

                    TabBar {
                        id: sideTabs

                        Layout.fillWidth: true
                        Component.onCompleted: currentIndex = 1
                        TabButton {
                            text: qsTr("未配置 %1").arg(root.viewModel.unassignedCount)
                            visible: false
                        }
                        TabButton {
                            text: qsTr("詳細")
                        }
                        TabButton {
                            text: qsTr("差分")
                        }
                        TabButton {
                            text: qsTr("履歴")
                        }
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: sideTabs.currentIndex

                        ListView {
                            id: unassignedList

                            clip: true
                            spacing: 4
                            model: root.viewModel.unassignedLessons
                            boundsBehavior: Flickable.StopAtBounds

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }

                            delegate: Rectangle {
                                id: unassignedCard

                                required property var modelData
                                property var lessonData: modelData
                                property real homeX: 0
                                property real homeY: 0
                                width: unassignedList.width
                                height: 78
                                radius: 5
                                color: root.rowValue(
                                           unassignedCard.modelData,
                                           "matchesFilter", true)
                                       ? "#fff8f6" : "#f3f4f6"
                                opacity: root.rowValue(
                                             unassignedCard.modelData,
                                             "matchesFilter", true) ? 1 : 0.35
                                border.color: "#e1aaa5"
                                Drag.active: unassignedDrag.drag.active
                                Drag.source: unassignedCard
                                Drag.keys: ["scheduleLesson"]

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 7
                                    spacing: 1
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Label {
                                            Layout.fillWidth: true
                                            text: root.rowValue(
                                                      unassignedCard.modelData,
                                                      "studentName", "")
                                                  + " / "
                                                  + root.rowValue(
                                                      unassignedCard.modelData,
                                                      "subjectShortName", "")
                                            color: "#592c29"
                                            font.pixelSize: 9
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            text: (root.rowValue(
                                                       unassignedCard.modelData,
                                                       "isPriorityFive", false)
                                                   ? "P5 " : "")
                                                  + (root.rowValue(
                                                         unassignedCard.modelData,
                                                         "oneToOneRequired", false)
                                                     ? "①" : "")
                                            color: "#a23b3b"
                                            font.pixelSize: 8
                                        }
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("残り%1回 / 候補%2件")
                                              .arg(root.rowValue(
                                                       unassignedCard.modelData,
                                                       "remainingCount", 1))
                                              .arg(root.rowValue(
                                                       unassignedCard.modelData,
                                                       "candidateCount", 0))
                                        color: "#667085"
                                        font.pixelSize: 8
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(
                                                  unassignedCard.modelData,
                                                  "reasonText",
                                                  qsTr("未配置理由を取得できません"))
                                        color: "#7d2925"
                                        font.pixelSize: 8
                                        elide: Text.ElideRight
                                    }
                                }
                                MouseArea {
                                    id: unassignedDrag

                                    anchors.fill: parent
                                    hoverEnabled: true
                                    drag.target: unassignedCard
                                    onPressed: {
                                        unassignedCard.homeX = unassignedCard.x
                                        unassignedCard.homeY = unassignedCard.y
                                    }
                                    onClicked: root.viewModel.selectLesson(
                                                   Number(root.rowValue(
                                                              unassignedCard.modelData,
                                                              "lessonRequestId", 0)),
                                                   Number(root.rowValue(
                                                              unassignedCard.modelData,
                                                              "sessionIndex", 0)))
                                    onReleased: {
                                        unassignedCard.Drag.drop()
                                        unassignedCard.x = unassignedCard.homeX
                                        unassignedCard.y = unassignedCard.homeY
                                    }
                                }
                            }

                            Label {
                                anchors.centerIn: parent
                                visible: unassignedList.count === 0
                                text: qsTr("未配置授業はありません")
                                color: "#667085"
                                font.pixelSize: 10
                            }
                        }

                        ScrollView {
                            clip: true
                            ColumnLayout {
                                width: parent.width
                                spacing: 7
                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(
                                              root.viewModel.selectedLesson,
                                              "studentName",
                                              qsTr("授業カードを選択してください"))
                                    color: "#344054"
                                    font.pixelSize: 13
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.Wrap
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(
                                              root.viewModel.selectedLesson,
                                              "detailText", "")
                                    color: "#667085"
                                    font.pixelSize: 9
                                    wrapMode: Text.Wrap
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("通常担当: %1\n希望講師: %2\n日時希望: %3\n"
                                               + "連続状況: %4\n空きコマ状況: %5")
                                          .arg(root.rowValue(
                                                   root.viewModel.selectedLesson,
                                                   "regularTeacherName", "―"))
                                          .arg(root.rowValue(
                                                   root.viewModel.selectedLesson,
                                                   "preferredTeacherText", "―"))
                                          .arg(root.rowValue(
                                                   root.viewModel.selectedLesson,
                                                   "availabilityText", "―"))
                                          .arg(root.rowValue(
                                                   root.viewModel.selectedLesson,
                                                   "consecutiveText", "―"))
                                          .arg(root.rowValue(
                                                   root.viewModel.selectedLesson,
                                                   "gapText", "―"))
                                    color: "#475467"
                                    font.pixelSize: 9
                                    wrapMode: Text.Wrap
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Button {
                                        Layout.fillWidth: true
                                        text: root.rowValue(
                                                  root.viewModel.selectedLesson,
                                                  "isLocked", false)
                                              ? qsTr("ロック解除")
                                              : qsTr("授業をロック")
                                        enabled: root.rowValue(
                                                     root.viewModel.selectedLesson,
                                                     "lessonRequestId", 0) > 0
                                        onClicked: root.viewModel.toggleSelectedLock()
                                    }
                                    Button {
                                        Layout.fillWidth: true
                                        text: qsTr("詳細編集")
                                        enabled: root.rowValue(
                                                     root.viewModel.selectedLesson,
                                                     "lessonRequestId", 0) > 0
                                        onClicked: detailDialog.open()
                                    }
                                }
                                Button {
                                    Layout.fillWidth: true
                                    text: qsTr("未配置へ移動")
                                    enabled: root.rowValue(
                                                 root.viewModel.selectedLesson,
                                                 "teacherId", 0) > 0
                                             && !root.rowValue(
                                                 root.viewModel.selectedLesson,
                                                 "isLocked", false)
                                    onClicked: {
                                        const outcome = root.viewModel.unassignSelected(
                                                          qsTr("画面から未配置へ移動"))
                                        if (outcome === "yellow")
                                            softWarningDialog.open()
                                    }
                                }
                            }
                        }

                        ListView {
                            id: diffList

                            clip: true
                            spacing: 3
                            model: root.viewModel.diffRows
                            delegate: Rectangle {
                                id: diffRow

                                required property var modelData
                                width: diffList.width
                                height: 64
                                radius: 4
                                color: "#f8fafc"
                                border.color: "#dce2ea"
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    spacing: 1
                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(
                                                  diffRow.modelData,
                                                  "changeTypeLabel", "")
                                        color: "#344054"
                                        font.pixelSize: 9
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(
                                                  diffRow.modelData,
                                                  "summary", "")
                                        color: "#667085"
                                        font.pixelSize: 8
                                        wrapMode: Text.Wrap
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                            Label {
                                anchors.centerIn: parent
                                visible: diffList.count === 0
                                text: qsTr("比較対象との差分はありません")
                                color: "#667085"
                                font.pixelSize: 9
                            }
                        }

                        ListView {
                            id: historyList

                            clip: true
                            spacing: 3
                            model: root.viewModel.historyRows
                            delegate: Rectangle {
                                id: historyRow

                                required property var modelData
                                width: historyList.width
                                height: 102
                                radius: 4
                                color: "#f8fafc"
                                border.color: "#dce2ea"
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    spacing: 1
                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(
                                                  historyRow.modelData,
                                                  "timestamp", "")
                                              + " "
                                              + root.rowValue(
                                                  historyRow.modelData,
                                                  "actionLabel", "")
                                        color: "#344054"
                                        font.pixelSize: 8
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("変更前: %1")
                                              .arg(root.rowValue(
                                                       historyRow.modelData,
                                                       "beforeSummary", ""))
                                        color: "#667085"
                                        font.pixelSize: 8
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("変更後: %1")
                                              .arg(root.rowValue(
                                                       historyRow.modelData,
                                                       "afterSummary", ""))
                                        color: "#344054"
                                        font.pixelSize: 8
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("理由: %1")
                                              .arg(root.rowValue(
                                                       historyRow.modelData,
                                                       "reason", ""))
                                        color: "#7a8493"
                                        font.pixelSize: 7
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                            Label {
                                anchors.centerIn: parent
                                visible: historyList.count === 0
                                text: qsTr("手動変更履歴はありません")
                                color: "#667085"
                                font.pixelSize: 9
                            }
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: softWarningDialog

        title: qsTr("ソフト条件の悪化を確認")
        modal: true
        anchors.centerIn: parent
        width: Math.min(root.width - 60, 560)
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: root.viewModel.confirmPendingMove(
                        softReason.text || qsTr("ソフト条件を確認して変更"))
        onRejected: root.viewModel.cancelPendingMove()

        ColumnLayout {
            width: parent.width
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: "△ " + root.rowValue(
                          root.viewModel.dropPreview, "message",
                          qsTr("ソフト条件が悪化します"))
                color: "#7a5100"
                font.pixelSize: 11
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
            }
            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(contentHeight, 180)
                model: root.rowValue(
                           root.viewModel.dropPreview, "softDeltas", [])
                delegate: Label {
                    id: softDelta

                    required property var modelData
                    width: ListView.view.width
                    text: qsTr("%1: %2 → %3")
                          .arg(root.rowValue(
                                   softDelta.modelData, "label", ""))
                          .arg(root.rowValue(
                                   softDelta.modelData, "before", ""))
                          .arg(root.rowValue(
                                   softDelta.modelData, "after", ""))
                    color: "#667085"
                    font.pixelSize: 9
                    wrapMode: Text.Wrap
                }
            }
            TextField {
                id: softReason

                Layout.fillWidth: true
                placeholderText: qsTr("変更理由（監査ログへ保存）")
                Accessible.name: qsTr("ソフト条件悪化を承認する理由")
            }
        }
    }

    Dialog {
        id: detailDialog

        title: qsTr("授業の詳細編集")
        modal: true
        anchors.centerIn: parent
        width: Math.min(root.width - 60, 620)
        standardButtons: Dialog.Save | Dialog.Cancel
        onAboutToShow: {
            root.viewModel.setDraftEditing(true)
            editDate.text = root.rowValue(
                        root.viewModel.selectedLesson,
                        "date", root.viewModel.currentDate)
            editSlot.currentIndex = root.findById(
                        root.viewModel.slotHeaders,
                        root.rowValue(
                            root.viewModel.selectedLesson, "timeSlotId", -1))
            editTeacher.currentIndex = root.findById(
                        root.viewModel.teacherHeaders,
                        root.rowValue(
                            root.viewModel.selectedLesson, "teacherId", -1))
            editLock.checked = root.rowValue(
                        root.viewModel.selectedLesson, "isLocked", false)
            editNote.text = root.rowValue(
                        root.viewModel.selectedLesson, "note", "")
        }
        onAccepted: {
            const outcome = root.viewModel.editSelected(
                              editDate.text,
                              Number(editSlot.currentValue),
                              Number(editTeacher.currentValue),
                              editLock.checked,
                              editNote.text,
                              editReason.text || qsTr("詳細編集ダイアログから変更"))
            if (outcome === "yellow")
                softWarningDialog.open()
        }
        onClosed: root.viewModel.setDraftEditing(false)

        GridLayout {
            width: parent.width
            columns: 2
            columnSpacing: 8
            rowSpacing: 7

            Label {
                text: qsTr("授業")
                color: "#667085"
            }
            Label {
                Layout.fillWidth: true
                text: root.rowValue(
                          root.viewModel.selectedLesson,
                          "studentName", "")
                      + " / "
                      + root.rowValue(
                          root.viewModel.selectedLesson,
                          "subjectShortName", "")
                color: "#344054"
                font.weight: Font.DemiBold
            }
            Label {
                text: qsTr("日付")
                color: "#667085"
            }
            TextField {
                id: editDate

                Layout.fillWidth: true
                placeholderText: "yyyy-MM-dd"
                Accessible.name: qsTr("授業日")
            }
            Label {
                text: qsTr("コマ")
                color: "#667085"
            }
            ComboBox {
                id: editSlot

                Layout.fillWidth: true
                model: root.viewModel.slotHeaders
                textRole: "label"
                valueRole: "id"
                Accessible.name: qsTr("授業コマ")
            }
            Label {
                text: qsTr("講師")
                color: "#667085"
            }
            ComboBox {
                id: editTeacher

                Layout.fillWidth: true
                model: root.viewModel.teacherHeaders
                textRole: "label"
                valueRole: "id"
                Accessible.name: qsTr("担当講師")
            }
            Label {
                text: qsTr("固定")
                color: "#667085"
            }
            CheckBox {
                id: editLock

                text: qsTr("再最適化で変更しない")
            }
            Label {
                text: qsTr("備考")
                color: "#667085"
            }
            TextArea {
                id: editNote

                Layout.fillWidth: true
                Layout.preferredHeight: 70
                wrapMode: TextEdit.Wrap
                Accessible.name: qsTr("授業備考")
            }
            Label {
                text: qsTr("変更理由")
                color: "#667085"
            }
            TextField {
                id: editReason

                Layout.fillWidth: true
                placeholderText: qsTr("監査ログへ保存する理由")
                Accessible.name: qsTr("詳細編集の理由")
            }
        }
    }

    Dialog {
        id: reoptimizationDialog

        title: qsTr("ロック以外を全体再最適化")
        modal: true
        anchors.centerIn: parent
        width: Math.min(root.width - 60, 560)
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: {
            if (root.viewModel.createReoptimizationCheckpoint())
                root.openOptimizationRequested()
        }

        ColumnLayout {
            width: parent.width
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: qsTr("現在の保存済み時間割をバックアップしてから、"
                           + "Phase 4の最適化画面へ移動します。ロック済み授業は保持されます。")
                color: "#344054"
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("対象配置: %1件\nロック: %2件\n未配置: %3件\n"
                           + "変更可能: %4件")
                      .arg(root.rowValue(
                               root.viewModel.reoptimizationSummary,
                               "assignmentCount", 0))
                      .arg(root.rowValue(
                               root.viewModel.reoptimizationSummary,
                               "lockCount", 0))
                      .arg(root.rowValue(
                               root.viewModel.reoptimizationSummary,
                               "unassignedCount", 0))
                      .arg(root.rowValue(
                               root.viewModel.reoptimizationSummary,
                               "editableCount", 0))
                color: "#667085"
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("注意: 選択日・選択生徒・選択講師だけの部分再最適化は、"
                           + "安全な境界が確定するまで提供しません。")
                color: "#7a5100"
                font.pixelSize: 9
                wrapMode: Text.Wrap
            }
        }
    }
}
