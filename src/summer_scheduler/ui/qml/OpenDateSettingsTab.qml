pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    property var checkedDateValues: []
    property var draftRows: []
    property bool draftDirty: false
    property int draftRevision: 0
    readonly property var calendarRows: buildCalendarRows(draftRevision)
    readonly property var weekdays: [
        qsTr("日"), qsTr("月"), qsTr("火"), qsTr("水"), qsTr("木"), qsTr("金"), qsTr("土")
    ]

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function cloneRows() {
        const source = root.viewModel.openDates || []
        const rows = []
        for (let i = 0; i < source.length; ++i) {
            rows.push({
                "date": String(root.rowValue(source[i], "date", "")),
                "isOpen": Boolean(root.rowValue(source[i], "isOpen", false)),
                "note": String(root.rowValue(source[i], "note", "")),
                "enabledTimeSlotIds": root.rowValue(source[i], "enabledTimeSlotIds", []).slice()
            })
        }
        rows.sort((left, right) => String(left.date).localeCompare(String(right.date)))
        return rows
    }

    function reloadDraft() {
        root.draftRows = root.cloneRows()
        root.checkedDateValues = []
        root.draftDirty = false
        root.draftRevision += 1
    }

    function buildCalendarRows(revision) {
        const rows = []
        if (root.draftRows.length > 0) {
            const first = new Date(String(root.draftRows[0].date) + "T00:00:00")
            for (let i = 0; i < first.getDay(); ++i)
                rows.push({"blank": true})
        }
        for (let i = 0; i < root.draftRows.length; ++i)
            rows.push(root.draftRows[i])
        return rows
    }

    function draftIndex(dateValue) {
        for (let i = 0; i < root.draftRows.length; ++i) {
            if (String(root.draftRows[i].date) === String(dateValue))
                return i
        }
        return -1
    }

    function draftRow(dateValue) {
        const index = root.draftIndex(dateValue)
        return index >= 0 ? root.draftRows[index] : null
    }

    function replaceDraftRow(index, isOpen, slotIds) {
        if (index < 0 || index >= root.draftRows.length)
            return
        const next = root.draftRows.slice()
        const current = next[index]
        next[index] = {
            "date": String(current.date),
            "isOpen": Boolean(isOpen),
            "note": String(root.rowValue(current, "note", "")),
            "enabledTimeSlotIds": slotIds.slice()
        }
        root.draftRows = next
        root.draftDirty = true
        root.draftRevision += 1
        root.viewModel.markDirty()
    }

    function allEnabledSlotIds() {
        const result = []
        const source = root.viewModel.timeSlots || []
        for (let i = 0; i < source.length; ++i) {
            if (Boolean(root.rowValue(source[i], "enabled", false)))
                result.push(Number(root.rowValue(source[i], "id", 0)))
        }
        return result
    }

    function enabledCodes(row) {
        const ids = root.rowValue(row, "enabledTimeSlotIds", [])
        const source = root.viewModel.timeSlots || []
        const codes = []
        for (let i = 0; i < source.length; ++i) {
            if (ids.indexOf(Number(root.rowValue(source[i], "id", 0))) >= 0)
                codes.push(String(root.rowValue(source[i], "code", "")))
        }
        return codes.join("・")
    }

    function isDateChecked(value) {
        return root.checkedDateValues.indexOf(String(value)) >= 0
    }

    function setDateChecked(value, checked) {
        const normalized = String(value)
        const next = root.checkedDateValues.slice()
        const index = next.indexOf(normalized)
        if (checked && index < 0)
            next.push(normalized)
        else if (!checked && index >= 0)
            next.splice(index, 1)
        root.checkedDateValues = next
    }

    function selectAllDates() {
        const next = []
        for (let i = 0; i < root.draftRows.length; ++i)
            next.push(String(root.draftRows[i].date))
        root.checkedDateValues = next
    }

    function slotCheckState(value) {
        if (root.checkedDateValues.length === 0)
            return Qt.Unchecked
        const id = Number(value)
        let selectedCount = 0
        for (let i = 0; i < root.checkedDateValues.length; ++i) {
            const row = root.draftRow(root.checkedDateValues[i])
            const slots = root.rowValue(row, "enabledTimeSlotIds", [])
            if (slots.indexOf(id) >= 0)
                selectedCount += 1
        }
        if (selectedCount === 0)
            return Qt.Unchecked
        if (selectedCount === root.checkedDateValues.length)
            return Qt.Checked
        return Qt.PartiallyChecked
    }

    function setSlotChecked(value, checked) {
        const id = Number(value)
        for (let i = 0; i < root.checkedDateValues.length; ++i) {
            const rowIndex = root.draftIndex(root.checkedDateValues[i])
            const row = rowIndex >= 0 ? root.draftRows[rowIndex] : null
            if (row) {
                const nextSlots = root.rowValue(row, "enabledTimeSlotIds", []).slice()
                const slotIndex = nextSlots.indexOf(id)
                if (checked && slotIndex < 0)
                    nextSlots.push(id)
                else if (!checked && slotIndex >= 0)
                    nextSlots.splice(slotIndex, 1)
                root.replaceDraftRow(rowIndex, row.isOpen, nextSlots)
            }
        }
        root.persistDraft()
    }

    function setAllSelectedSlots() {
        const slots = root.allEnabledSlotIds()
        for (let i = 0; i < root.checkedDateValues.length; ++i) {
            const rowIndex = root.draftIndex(root.checkedDateValues[i])
            const row = rowIndex >= 0 ? root.draftRows[rowIndex] : null
            if (row)
                root.replaceDraftRow(rowIndex, row.isOpen, slots)
        }
        root.persistDraft()
    }

    function setSelectedDatesOpen(isOpen) {
        const defaults = root.allEnabledSlotIds()
        for (let i = 0; i < root.checkedDateValues.length; ++i) {
            const rowIndex = root.draftIndex(root.checkedDateValues[i])
            const row = rowIndex >= 0 ? root.draftRows[rowIndex] : null
            if (row) {
                const slots = root.rowValue(row, "enabledTimeSlotIds", [])
                root.replaceDraftRow(rowIndex, isOpen,
                                     isOpen && slots.length === 0 ? defaults : slots)
            }
        }
        root.persistDraft()
    }

    function setAllDatesOpen() {
        const defaults = root.allEnabledSlotIds()
        for (let i = 0; i < root.draftRows.length; ++i) {
            const slots = root.rowValue(root.draftRows[i], "enabledTimeSlotIds", [])
            root.replaceDraftRow(i, true, slots.length === 0 ? defaults : slots)
        }
        root.persistDraft()
    }

    function setWeekdayClosed(weekdayIndex) {
        for (let i = 0; i < root.draftRows.length; ++i) {
            const day = new Date(String(root.draftRows[i].date) + "T00:00:00")
            if (day.getDay() === Number(weekdayIndex))
                root.replaceDraftRow(i, false, root.draftRows[i].enabledTimeSlotIds)
        }
        root.persistDraft()
    }

    function persistDraft() {
        if (!root.draftDirty)
            return
        const entries = []
        for (let i = 0; i < root.draftRows.length; ++i) {
            entries.push({
                "date": String(root.draftRows[i].date),
                "isOpen": Boolean(root.draftRows[i].isOpen),
                "enabledTimeSlotIds": root.draftRows[i].enabledTimeSlotIds.slice()
            })
        }
        if (root.viewModel.saveOpenDateSchedule(entries))
            root.draftDirty = false
    }

    Component.onCompleted: reloadDraft()

    Connections {
        target: root.viewModel
        function onOpenDatesChanged() {
            if (!root.draftDirty)
                root.reloadDraft()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Label { text: qsTr("開校日・休校日カレンダー"); color: "#344054"; font.pixelSize: 15; font.weight: Font.DemiBold }
                Label {
                    text: qsTr("%1 ～ %2（変更は自動的に保存されます）")
                          .arg(root.viewModel.currentStartDate || "----/--/--")
                          .arg(root.viewModel.currentEndDate || "----/--/--")
                    color: "#667085"; font.pixelSize: 9
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: bulkFlow.implicitHeight + 14
            color: "#f7f9fc"; border.color: "#dce2ea"; radius: 7
            Flow {
                id: bulkFlow
                anchors.left: parent.left; anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter; anchors.margins: 7; spacing: 7
                Button { text: qsTr("期間内をすべて開校"); onClicked: root.setAllDatesOpen() }
                ComboBox {
                    id: weekdayBulk; width: 110
                    model: [qsTr("日曜日"), qsTr("月曜日"), qsTr("火曜日"), qsTr("水曜日"), qsTr("木曜日"), qsTr("金曜日"), qsTr("土曜日")]
                }
                Button { text: qsTr("指定曜日を休校"); onClicked: root.setWeekdayClosed(weekdayBulk.currentIndex) }
                Button { text: qsTr("すべて選択"); onClicked: root.selectAllDates() }
                Button { text: qsTr("選択解除"); enabled: root.checkedDateValues.length > 0; onClicked: root.checkedDateValues = [] }
                Label { height: 36; verticalAlignment: Text.AlignVCenter; text: qsTr("%1日選択中").arg(root.checkedDateValues.length); color: root.checkedDateValues.length ? "#2767c5" : "#667085" }
                Button { text: qsTr("選択日を休校"); enabled: root.checkedDateValues.length > 0; onClicked: root.setSelectedDatesOpen(false) }
                Button { text: qsTr("選択日を開校"); highlighted: true; enabled: root.checkedDateValues.length > 0; onClicked: root.setSelectedDatesOpen(true) }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: slotFlow.implicitHeight + 22
            color: "#f5f9ff"; border.color: "#b9d4ee"; radius: 7
            Flow {
                id: slotFlow
                anchors.left: parent.left; anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter; anchors.margins: 10; spacing: 8
                Label { height: 36; verticalAlignment: Text.AlignVCenter; text: qsTr("選択日に使用するコマ"); color: "#344054"; font.weight: Font.DemiBold }
                Repeater {
                    model: root.viewModel.timeSlots || []
                    delegate: CheckBox {
                        id: slotChoice
                        required property var modelData
                        visible: Boolean(root.rowValue(slotChoice.modelData, "enabled", false))
                        enabled: root.checkedDateValues.length > 0
                        text: String(root.rowValue(slotChoice.modelData, "code", ""))
                        tristate: true
                        checkState: root.slotCheckState(root.rowValue(slotChoice.modelData, "id", 0))
                        nextCheckState: function() {
                            return checkState === Qt.Checked ? Qt.Unchecked : Qt.Checked
                        }
                        onClicked: root.setSlotChecked(root.rowValue(slotChoice.modelData, "id", 0), checkState === Qt.Checked)
                    }
                }
                Button {
                    text: qsTr("全コマ")
                    enabled: root.checkedDateValues.length > 0
                    onClicked: {
                        root.setAllSelectedSlots()
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            color: "#f8fafc"; border.color: "#e2e7ee"; radius: 8
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 8; spacing: 4
                GridLayout {
                    Layout.fillWidth: true; columns: 7; columnSpacing: 3
                    Repeater {
                        model: root.weekdays
                        delegate: Rectangle {
                            id: weekdayDelegate
                            required property string modelData
                            Layout.fillWidth: true; Layout.preferredHeight: 25; color: "#e9eef5"; radius: 4
                            Label { anchors.centerIn: parent; text: weekdayDelegate.modelData; color: "#475467"; font.pixelSize: 10; font.weight: Font.DemiBold }
                        }
                    }
                }
                GridView {
                    id: calendarGrid
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    cellWidth: Math.floor((width - 18) / 7); cellHeight: 88; model: root.calendarRows
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    delegate: Item {
                        id: dayDelegate
                        required property var modelData
                        width: GridView.view.cellWidth; height: GridView.view.cellHeight
                        Rectangle {
                            anchors.fill: parent; anchors.margins: 2
                            visible: !root.rowValue(dayDelegate.modelData, "blank", false)
                            radius: 6
                            color: root.isDateChecked(root.rowValue(dayDelegate.modelData, "date", "")) ? "#e8f0ff" : root.rowValue(dayDelegate.modelData, "isOpen", true) ? "#ffffff" : "#f2f4f7"
                            border.color: root.isDateChecked(root.rowValue(dayDelegate.modelData, "date", "")) ? "#2767c5" : "#dce2ea"
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 7; spacing: 1
                                Label { Layout.fillWidth: true; text: root.rowValue(dayDelegate.modelData, "date", ""); color: "#344054"; font.pixelSize: 9; font.weight: Font.DemiBold; elide: Text.ElideRight }
                                Label { text: root.rowValue(dayDelegate.modelData, "isOpen", true) ? qsTr("✓ 開校") : qsTr("－ 休校"); color: root.rowValue(dayDelegate.modelData, "isOpen", true) ? "#176b40" : "#667085"; font.pixelSize: 10; font.weight: Font.DemiBold }
                                Label { Layout.fillWidth: true; visible: root.rowValue(dayDelegate.modelData, "isOpen", true); text: root.enabledCodes(dayDelegate.modelData); color: "#2767c5"; font.pixelSize: 9; font.weight: Font.DemiBold; elide: Text.ElideRight }
                            }
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.setDateChecked(root.rowValue(dayDelegate.modelData, "date", ""), !root.isDateChecked(root.rowValue(dayDelegate.modelData, "date", "")))
                            }
                            CheckBox {
                                anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 2; z: 2
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
