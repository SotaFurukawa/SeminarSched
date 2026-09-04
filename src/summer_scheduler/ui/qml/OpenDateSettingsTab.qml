pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    property var checkedDateValues: []
    property var checkedSlotIds: []
    readonly property var calendarRows: buildCalendarRows()
    readonly property var weekdays: [
        qsTr("日"), qsTr("月"), qsTr("火"), qsTr("水"), qsTr("木"), qsTr("金"), qsTr("土")
    ]

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function buildCalendarRows() {
        const source = root.viewModel.openDates || []
        const dates = []
        for (let i = 0; i < source.length; ++i)
            dates.push(source[i])
        dates.sort((left, right) => String(left.date).localeCompare(String(right.date)))
        const rows = []
        if (dates.length > 0) {
            const first = new Date(String(dates[0].date) + "T00:00:00")
            for (let i = 0; i < first.getDay(); ++i)
                rows.push({"blank": true})
        }
        for (let i = 0; i < dates.length; ++i)
            rows.push(dates[i])
        return rows
    }

    function isDateChecked(value) {
        return root.checkedDateValues.indexOf(String(value)) >= 0
    }

    function dateRow(value) {
        const source = root.viewModel.openDates || []
        for (let i = 0; i < source.length; ++i) {
            if (String(source[i].date) === String(value))
                return source[i]
        }
        return null
    }

    function setDateChecked(value, checked) {
        const normalized = String(value)
        const next = root.checkedDateValues.slice()
        const index = next.indexOf(normalized)
        if (checked && index < 0) {
            next.push(normalized)
            if (next.length === 1) {
                const row = root.dateRow(normalized)
                root.checkedSlotIds = root.rowValue(row, "enabledTimeSlotIds", []).slice()
            }
        } else if (!checked && index >= 0) {
            next.splice(index, 1)
        }
        root.checkedDateValues = next
    }

    function selectAllDates() {
        const source = root.viewModel.openDates || []
        const next = []
        for (let i = 0; i < source.length; ++i)
            next.push(String(root.rowValue(source[i], "date", "")))
        root.checkedDateValues = next
        root.selectAllSlots()
    }

    function isSlotChecked(value) {
        return root.checkedSlotIds.indexOf(Number(value)) >= 0
    }

    function setSlotChecked(value, checked) {
        const id = Number(value)
        const next = root.checkedSlotIds.slice()
        const index = next.indexOf(id)
        if (checked && index < 0)
            next.push(id)
        else if (!checked && index >= 0)
            next.splice(index, 1)
        root.checkedSlotIds = next
    }

    function selectAllSlots() {
        const source = root.viewModel.timeSlots || []
        const next = []
        for (let i = 0; i < source.length; ++i) {
            if (Boolean(root.rowValue(source[i], "enabled", false)))
                next.push(Number(root.rowValue(source[i], "id", 0)))
        }
        root.checkedSlotIds = next
    }

    function applyCheckedDates(isOpen) {
        root.viewModel.setOpenDates(root.checkedDateValues, isOpen)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Label {
                text: qsTr("開校日・休校日カレンダー")
                color: "#344054"
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }
            Label {
                text: qsTr("%1 ～ %2（複数の日付を選択してまとめて変更できます）")
                      .arg(root.viewModel.currentStartDate || "----/--/--")
                      .arg(root.viewModel.currentEndDate || "----/--/--")
                color: "#667085"
                font.pixelSize: 9
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: bulkFlow.implicitHeight + 14
            color: "#f7f9fc"
            border.color: "#dce2ea"
            radius: 7
            Flow {
                id: bulkFlow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: 7
                spacing: 7
                Button { text: qsTr("期間内をすべて開校"); onClicked: root.viewModel.setAllDatesOpen() }
                ComboBox {
                    id: weekdayBulk
                    width: 110
                    model: [qsTr("日曜日"), qsTr("月曜日"), qsTr("火曜日"), qsTr("水曜日"), qsTr("木曜日"), qsTr("金曜日"), qsTr("土曜日")]
                }
                Button { text: qsTr("指定曜日を休校"); onClicked: root.viewModel.setWeekdayClosed(weekdayBulk.currentIndex) }
                Button { text: qsTr("すべて選択"); onClicked: root.selectAllDates() }
                Button { text: qsTr("選択解除"); enabled: root.checkedDateValues.length > 0; onClicked: root.checkedDateValues = [] }
                Label {
                    height: 36
                    verticalAlignment: Text.AlignVCenter
                    text: qsTr("%1日選択中").arg(root.checkedDateValues.length)
                    color: root.checkedDateValues.length ? "#2767c5" : "#667085"
                }
                Button { text: qsTr("選択日を休校"); enabled: root.checkedDateValues.length > 0; onClicked: root.applyCheckedDates(false) }
                Button { text: qsTr("選択日を開校"); highlighted: true; enabled: root.checkedDateValues.length > 0; onClicked: root.applyCheckedDates(true) }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: slotFlow.implicitHeight + 22
            color: "#f5f9ff"
            border.color: "#b9d4ee"
            radius: 7
            Flow {
                id: slotFlow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: 10
                spacing: 8
                Label {
                    height: 36
                    verticalAlignment: Text.AlignVCenter
                    text: qsTr("選択日に使用するコマ")
                    color: "#344054"
                    font.weight: Font.DemiBold
                }
                Repeater {
                    model: root.viewModel.timeSlots || []
                    delegate: CheckBox {
                        id: slotChoice
                        required property var modelData
                        visible: Boolean(root.rowValue(slotChoice.modelData, "enabled", false))
                        text: String(root.rowValue(slotChoice.modelData, "code", ""))
                        checked: root.isSlotChecked(root.rowValue(slotChoice.modelData, "id", 0))
                        onClicked: root.setSlotChecked(root.rowValue(slotChoice.modelData, "id", 0), checked)
                    }
                }
                Button { text: qsTr("全コマ"); onClicked: root.selectAllSlots() }
                Button {
                    text: qsTr("有効コマを保存")
                    highlighted: true
                    enabled: root.checkedDateValues.length > 0 && root.checkedSlotIds.length > 0
                    onClicked: root.viewModel.setOpenDateTimeSlots(root.checkedDateValues, root.checkedSlotIds)
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#f8fafc"
            border.color: "#e2e7ee"
            radius: 8
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4
                GridLayout {
                    Layout.fillWidth: true
                    columns: 7
                    columnSpacing: 3
                    Repeater {
                        model: root.weekdays
                        delegate: Rectangle {
                            id: weekdayDelegate
                            required property string modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 25
                            color: "#e9eef5"
                            radius: 4
                            Label { anchors.centerIn: parent; text: weekdayDelegate.modelData; color: "#475467"; font.pixelSize: 10; font.weight: Font.DemiBold }
                        }
                    }
                }

                GridView {
                    id: calendarGrid
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    cellWidth: width / 7
                    cellHeight: 88
                    model: root.calendarRows
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    delegate: Item {
                        id: dayDelegate
                        required property var modelData
                        width: GridView.view.cellWidth
                        height: GridView.view.cellHeight
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 2
                            visible: !root.rowValue(dayDelegate.modelData, "blank", false)
                            radius: 6
                            color: root.isDateChecked(root.rowValue(dayDelegate.modelData, "date", "")) ? "#e8f0ff"
                                   : root.rowValue(dayDelegate.modelData, "isOpen", true) ? "#ffffff" : "#f2f4f7"
                            border.color: root.isDateChecked(root.rowValue(dayDelegate.modelData, "date", "")) ? "#2767c5" : "#dce2ea"
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 7
                                spacing: 1
                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(dayDelegate.modelData, "date", "")
                                    color: "#344054"
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                Label {
                                    text: root.rowValue(dayDelegate.modelData, "isOpen", true) ? qsTr("✓ 開校") : qsTr("－ 休校")
                                    color: root.rowValue(dayDelegate.modelData, "isOpen", true) ? "#176b40" : "#667085"
                                    font.pixelSize: 10
                                    font.weight: Font.DemiBold
                                }
                                Label {
                                    Layout.fillWidth: true
                                    visible: root.rowValue(dayDelegate.modelData, "isOpen", true)
                                    text: root.rowValue(dayDelegate.modelData, "enabledSlotCodes", "")
                                    color: "#2767c5"
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.setDateChecked(root.rowValue(dayDelegate.modelData, "date", ""), !root.isDateChecked(root.rowValue(dayDelegate.modelData, "date", "")))
                            }
                            CheckBox {
                                anchors.top: parent.top
                                anchors.right: parent.right
                                anchors.margins: 2
                                z: 2
                                checked: root.isDateChecked(root.rowValue(dayDelegate.modelData, "date", ""))
                                onClicked: root.setDateChecked(root.rowValue(dayDelegate.modelData, "date", ""), checked)
                            }
                        }
                    }
                }
            }
        }
    }
}
