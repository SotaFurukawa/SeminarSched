pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    property var selectedDateRow: null
    property var checkedDateValues: []
    property bool loadingDateDraft: false
    readonly property var calendarRows: buildCalendarRows()
    readonly property var weekdays: [
        qsTr("日"), qsTr("月"), qsTr("火"), qsTr("水"),
        qsTr("木"), qsTr("金"), qsTr("土")
    ]

    Connections {
        target: root.viewModel

        function onOpenDatesChanged() {
            root.checkedDateValues = []
        }
    }

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function dateSortValue(row) {
        return String(root.rowValue(row, "date", ""))
    }

    function weekdayOf(dateValue) {
        const parsed = new Date(String(dateValue) + "T00:00:00")
        return isNaN(parsed.getTime()) ? 0 : parsed.getDay()
    }

    function buildCalendarRows() {
        const source = root.viewModel.openDates || []
        const dates = []
        for (let i = 0; i < source.length; ++i)
            dates.push(source[i])
        dates.sort(function (left, right) {
            return root.dateSortValue(left).localeCompare(root.dateSortValue(right))
        })
        const rows = []
        if (dates.length > 0) {
            const padding = root.weekdayOf(root.rowValue(dates[0], "date", ""))
            for (let i = 0; i < padding; ++i)
                rows.push({"blank": true})
        }
        for (let i = 0; i < dates.length; ++i)
            rows.push(dates[i])
        return rows
    }

    function selectDate(row) {
        if (root.rowValue(row, "blank", false))
            return
        root.loadingDateDraft = true
        root.selectedDateRow = row
        selectedDateLabel.text = root.rowValue(row, "date", "")
        selectedDateOpen.checked = Boolean(root.rowValue(row, "isOpen", true))
        selectedDateNote.text = root.rowValue(row, "note", "")
        root.loadingDateDraft = false
    }

    function isDateChecked(dateValue) {
        return root.checkedDateValues.indexOf(String(dateValue)) >= 0
    }

    function setDateChecked(dateValue, checked) {
        const value = String(dateValue)
        const next = root.checkedDateValues.slice()
        const index = next.indexOf(value)
        if (checked && index < 0)
            next.push(value)
        else if (!checked && index >= 0)
            next.splice(index, 1)
        root.checkedDateValues = next
    }

    function selectAllDates() {
        const source = root.viewModel.openDates || []
        const next = []
        for (let i = 0; i < source.length; ++i)
            next.push(String(root.rowValue(source[i], "date", "")))
        root.checkedDateValues = next
    }

    function applyCheckedDates(isOpen) {
        if (root.viewModel.setOpenDates(root.checkedDateValues, isOpen))
            root.checkedDateValues = []
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
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
                    text: qsTr("%1 ～ %2（講習期間内のみ）")
                          .arg(root.viewModel.currentStartDate || "----/--/--")
                          .arg(root.viewModel.currentEndDate || "----/--/--")
                    color: "#667085"
                    font.pixelSize: 9
                }
            }

            Button {
                text: qsTr("期間内をすべて開校")
                onClicked: root.viewModel.setAllDatesOpen()
            }

            ComboBox {
                id: weekdayBulk

                Layout.preferredWidth: 110
                model: [
                    qsTr("日曜日"), qsTr("月曜日"), qsTr("火曜日"), qsTr("水曜日"),
                    qsTr("木曜日"), qsTr("金曜日"), qsTr("土曜日")
                ]
                Accessible.name: qsTr("一括休校曜日")
            }

            Button {
                text: qsTr("指定曜日を休校")
                onClicked: root.viewModel.setWeekdayClosed(weekdayBulk.currentIndex)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            color: "#f7f9fc"
            border.color: "#dce2ea"
            radius: 7

            RowLayout {
                anchors.fill: parent
                anchors.margins: 7
                spacing: 7

                Label {
                    text: qsTr("複数日の一括設定")
                    color: "#344054"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }

                Button {
                    text: qsTr("すべて選択")
                    onClicked: root.selectAllDates()
                }

                Button {
                    text: qsTr("選択解除")
                    enabled: root.checkedDateValues.length > 0
                    onClicked: root.checkedDateValues = []
                }

                Label {
                    Layout.fillWidth: true
                    text: qsTr("%1日選択中").arg(root.checkedDateValues.length)
                    color: root.checkedDateValues.length > 0 ? "#2767c5" : "#667085"
                    font.pixelSize: 10
                }

                Button {
                    text: qsTr("選択日を休校")
                    enabled: root.checkedDateValues.length > 0
                    onClicked: root.applyCheckedDates(false)
                }

                Button {
                    text: qsTr("選択日を開校")
                    enabled: root.checkedDateValues.length > 0
                    highlighted: true
                    onClicked: root.applyCheckedDates(true)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

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

                                Label {
                                    anchors.centerIn: parent
                                    text: weekdayDelegate.modelData
                                    color: "#475467"
                                    font.pixelSize: 10
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }

                    GridView {
                        id: calendarGrid

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        cellWidth: width / 7
                        cellHeight: 72
                        model: root.calendarRows
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

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
                                color: {
                                    const selected = root.selectedDateRow
                                                     && String(root.rowValue(
                                                                   root.selectedDateRow, "date", ""))
                                                        === String(root.rowValue(
                                                                      dayDelegate.modelData, "date", ""))
                                    if (selected)
                                        return "#e8f0ff"
                                    return root.rowValue(dayDelegate.modelData, "isOpen", true)
                                            ? "#ffffff" : "#f2f4f7"
                                }
                                border.color: {
                                    const selected = root.selectedDateRow
                                                     && String(root.rowValue(
                                                                   root.selectedDateRow, "date", ""))
                                                        === String(root.rowValue(
                                                                      dayDelegate.modelData, "date", ""))
                                    return selected ? "#2767c5" : "#dce2ea"
                                }
                                border.width: 1

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 7
                                    spacing: 2

                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(dayDelegate.modelData, "date", "")
                                        color: "#344054"
                                        font.pixelSize: 9
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(dayDelegate.modelData, "isOpen", true)
                                              ? qsTr("✓ 開校") : qsTr("－ 休校")
                                        color: root.rowValue(dayDelegate.modelData, "isOpen", true)
                                               ? "#176b40" : "#667085"
                                        font.pixelSize: 10
                                        font.weight: Font.DemiBold
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        visible: Boolean(root.rowValue(dayDelegate.modelData, "note", ""))
                                        text: root.rowValue(dayDelegate.modelData, "note", "")
                                        color: "#7a8493"
                                        font.pixelSize: 8
                                        elide: Text.ElideRight
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    Accessible.name: qsTr("%1 %2、編集")
                                                     .arg(root.rowValue(dayDelegate.modelData, "date", ""))
                                                     .arg(root.rowValue(dayDelegate.modelData, "isOpen", true)
                                                          ? qsTr("開校") : qsTr("休校"))
                                    Accessible.role: Accessible.Button
                                    onClicked: root.selectDate(dayDelegate.modelData)
                                }

                                CheckBox {
                                    anchors.top: parent.top
                                    anchors.right: parent.right
                                    anchors.margins: 2
                                    z: 2
                                    checked: root.isDateChecked(
                                                 root.rowValue(dayDelegate.modelData,
                                                               "date", ""))
                                    Accessible.name: qsTr("%1を一括設定の対象にする")
                                                     .arg(root.rowValue(
                                                              dayDelegate.modelData,
                                                              "date", ""))
                                    onClicked: root.setDateChecked(
                                                   root.rowValue(dayDelegate.modelData,
                                                                 "date", ""),
                                                   checked)
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: 285
                Layout.fillHeight: true
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 8

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 9

                    Label {
                        text: qsTr("選択日の設定")
                        color: "#344054"
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }

                    Label {
                        id: selectedDateLabel
                        Layout.fillWidth: true
                        text: qsTr("日付を選択してください")
                        color: root.selectedDateRow ? "#18212f" : "#7a8493"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }

                    CheckBox {
                        id: selectedDateOpen
                        text: checked ? qsTr("開校日にする") : qsTr("休校日にする")
                        enabled: Boolean(root.selectedDateRow)
                        Accessible.name: text
                        onClicked: root.viewModel.markDirty()
                    }

                    Label {
                        text: qsTr("備考")
                        color: "#344054"
                        font.pixelSize: 10
                    }

                    TextArea {
                        id: selectedDateNote
                        Layout.fillWidth: true
                        Layout.preferredHeight: 110
                        enabled: Boolean(root.selectedDateRow)
                        placeholderText: qsTr("例：午前のみ休校")
                        wrapMode: TextEdit.Wrap
                        Accessible.name: qsTr("開校日備考")
                        onTextChanged: {
                            if (activeFocus && !root.loadingDateDraft)
                                root.viewModel.markDirty()
                        }
                    }

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("個別の備考はここで編集します。複数日の状態変更は、左のチェックボックスと一括設定を使えます。")
                        color: "#667085"
                        font.pixelSize: 9
                        wrapMode: Text.Wrap
                    }

                    Item {
                        Layout.fillHeight: true
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Button {
                            Layout.fillWidth: true
                            text: qsTr("休校に設定")
                            enabled: Boolean(root.selectedDateRow)
                            onClicked: {
                                selectedDateOpen.checked = false
                                root.viewModel.markDirty()
                            }
                        }

                        Button {
                            Layout.fillWidth: true
                            text: qsTr("開校に設定")
                            enabled: Boolean(root.selectedDateRow)
                            onClicked: {
                                selectedDateOpen.checked = true
                                root.viewModel.markDirty()
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Button {
                            Layout.fillWidth: true
                            text: qsTr("キャンセル")
                            enabled: Boolean(root.selectedDateRow)
                            onClicked: {
                                root.selectDate(root.selectedDateRow)
                                root.viewModel.discardDraft()
                            }
                        }

                        Button {
                            Layout.fillWidth: true
                            text: qsTr("選択日の変更を保存")
                            highlighted: true
                            enabled: Boolean(root.selectedDateRow)
                            onClicked: root.viewModel.setOpenDate(
                                           root.rowValue(root.selectedDateRow, "date", ""),
                                           selectedDateOpen.checked,
                                           selectedDateNote.text)
                        }
                    }
                }
            }
        }
    }
}
