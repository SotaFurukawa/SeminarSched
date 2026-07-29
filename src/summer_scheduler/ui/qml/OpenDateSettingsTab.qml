pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    property var selectedDateRow: null
    property bool loadingDateDraft: false
    readonly property var calendarRows: buildCalendarRows()
    readonly property var weekdays: [
        qsTr("日"), qsTr("月"), qsTr("火"), qsTr("水"),
        qsTr("木"), qsTr("金"), qsTr("土")
    ]

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
                        text: qsTr("状態は「開校／休校」の文字でも表示されます。")
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
