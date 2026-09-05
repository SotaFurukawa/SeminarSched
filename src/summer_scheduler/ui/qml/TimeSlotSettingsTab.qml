pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel

    function savePendingChanges() {
        root.saveAttempted = true
        if (slotCode.text.trim() === ""
                || slotDisplayName.text.trim() === ""
                || slotStart.text.trim() === ""
                || slotEnd.text.trim() === "")
            return false
        return root.viewModel.saveTimeSlot(
                    root.editingId,
                    slotCode.text.trim(),
                    slotDisplayName.text.trim(),
                    slotStart.text.trim(),
                    slotEnd.text.trim(),
                    root.editingSortOrder,
                    slotEnabled.checked)
    }
    property int editingId: 0
    property int editingSortOrder: 1
    property var selectedRow: null
    property bool saveAttempted: false
    readonly property var sortedSlots: buildSortedSlots()

    function moveSlot(fromIndex, toIndex) {
        if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex
                || fromIndex >= root.sortedSlots.length || toIndex >= root.sortedSlots.length)
            return
        const ids = []
        for (let i = 0; i < root.sortedSlots.length; ++i)
            ids.push(Number(root.rowValue(root.sortedSlots[i], "id", 0)))
        const moved = ids.splice(fromIndex, 1)[0]
        ids.splice(toIndex, 0, moved)
        root.viewModel.reorderTimeSlots(ids)
    }

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function buildSortedSlots() {
        const rows = []
        const source = root.viewModel.timeSlots || []
        for (let i = 0; i < source.length; ++i)
            rows.push(source[i])
        rows.sort(function (left, right) {
            return Number(root.rowValue(left, "sortOrder", 0))
                    - Number(root.rowValue(right, "sortOrder", 0))
        })
        return rows
    }

    function loadSlot(row) {
        root.selectedRow = row
        root.editingId = Number(root.rowValue(row, "id", 0))
        slotCode.text = root.rowValue(row, "code", "")
        slotDisplayName.text = root.rowValue(row, "displayName", "")
        slotStart.text = root.rowValue(row, "startTime", "")
        slotEnd.text = root.rowValue(row, "endTime", "")
        root.editingSortOrder = Number(root.rowValue(row, "sortOrder", 1))
        slotEnabled.checked = Boolean(root.rowValue(row, "enabled", true))
        root.saveAttempted = false
    }

    function clearSlot() {
        root.selectedRow = null
        root.editingId = 0
        slotCode.text = ""
        slotDisplayName.text = ""
        slotStart.text = ""
        slotEnd.text = ""
        root.editingSortOrder = Math.max(1, slotList.count + 1)
        slotEnabled.checked = true
        root.saveAttempted = false
    }

    SplitView {
        anchors.fill: parent
        orientation: root.width < 820 ? Qt.Vertical : Qt.Horizontal
        handle: Rectangle {
            implicitWidth: 16
            color: "transparent"

            Rectangle {
                anchors.centerIn: parent
                width: 1
                height: parent.height - 16
                color: "#d5dce6"
            }
        }

        Rectangle {
            SplitView.preferredWidth: 430
            SplitView.minimumWidth: root.width < 820 ? 0 : 320
            SplitView.preferredHeight: root.width < 820 ? 405 : -1
            color: "#f8fafc"
            border.color: "#e2e7ee"
            radius: 8

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1

                        Label {
                            text: qsTr("コマ一覧")
                            color: "#344054"
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }

                        Label {
                            text: qsTr("左のつまみをドラッグして順序を変更")
                            color: "#667085"
                            font.pixelSize: 9
                        }
                    }

                    Button {
                        text: qsTr("＋ 追加")
                        onClicked: root.clearSlot()
                    }
                }

                ListView {
                    id: slotList

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 5
                    model: root.sortedSlots
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: ItemDelegate {
                        id: slotDelegate

                        required property var modelData
                        required property int index
                        property real dragOriginY: 0
                        width: ListView.view.width
                        height: 54
                        z: dragArea.drag.active ? 10 : 0
                        highlighted: root.editingId
                                     === Number(root.rowValue(modelData, "id", 0))
                        Accessible.name: qsTr("%1 %2 %3から%4 %5")
                                         .arg(root.rowValue(modelData, "sortOrder", ""))
                                         .arg(root.rowValue(modelData, "code", ""))
                                         .arg(root.rowValue(modelData, "startTime", ""))
                                         .arg(root.rowValue(modelData, "endTime", ""))
                                         .arg(root.rowValue(modelData, "enabled", true)
                                              ? qsTr("使用") : qsTr("停止"))
                        onClicked: root.loadSlot(modelData)

                        contentItem: RowLayout {
                            spacing: 9

                            Label {
                                Layout.preferredWidth: 34
                                text: "≡"
                                horizontalAlignment: Text.AlignHCenter
                                color: slotDelegate.highlighted ? "#2767c5" : "#667085"
                                font.pixelSize: 24
                                font.weight: Font.Bold

                                MouseArea {
                                    id: dragArea
                                    anchors.fill: parent
                                    cursorShape: Qt.SizeVerCursor
                                    drag.target: slotDelegate
                                    drag.axis: Drag.YAxis
                                    onPressed: slotDelegate.dragOriginY = slotDelegate.y
                                    onReleased: {
                                        const centerY = slotDelegate.y + slotDelegate.height / 2
                                        const targetIndex = Math.max(
                                                    0,
                                                    Math.min(slotList.count - 1,
                                                             Math.floor(centerY / (slotDelegate.height + slotList.spacing))))
                                        slotDelegate.y = slotDelegate.dragOriginY
                                        root.moveSlot(slotDelegate.index, targetIndex)
                                    }
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1

                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("%1　%2")
                                          .arg(root.rowValue(slotDelegate.modelData, "code", ""))
                                          .arg(root.rowValue(slotDelegate.modelData, "displayName", ""))
                                    color: "#344054"
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }

                                Label {
                                    text: qsTr("%1 ～ %2")
                                          .arg(root.rowValue(slotDelegate.modelData, "startTime", ""))
                                          .arg(root.rowValue(slotDelegate.modelData, "endTime", ""))
                                    color: "#667085"
                                    font.pixelSize: 9
                                }
                            }

                            Label {
                                text: root.rowValue(slotDelegate.modelData, "enabled", true)
                                      ? qsTr("使用") : qsTr("停止")
                                color: root.rowValue(slotDelegate.modelData, "enabled", true)
                                       ? "#176b40" : "#7a8493"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: qsTr("連続・空きコマ判定には時刻ではなく順序を使用します。")
                    color: "#667085"
                    font.pixelSize: 9
                    wrapMode: Text.Wrap
                }
            }
        }

        ScrollView {
            id: slotEditorScroll

            SplitView.fillWidth: true
            SplitView.minimumWidth: root.width < 820 ? 0 : 380
            SplitView.fillHeight: true
            clip: true
            leftPadding: 10
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: slotEditorScroll.availableWidth
                spacing: 10

                Label {
                    text: root.editingId > 0 ? qsTr("コマを編集") : qsTr("新しいコマ")
                    color: "#344054"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: width >= 500 ? 2 : 1
                    columnSpacing: 12
                    rowSpacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: qsTr("コマ名 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: slotCode
                            Layout.fillWidth: true
                            placeholderText: qsTr("例：Y")
                            Accessible.name: qsTr("コマ名")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && slotCode.text.trim() === ""
                            text: qsTr("コマ名を入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 9
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: qsTr("表示名 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: slotDisplayName
                            Layout.fillWidth: true
                            placeholderText: qsTr("例：Yコマ")
                            Accessible.name: qsTr("コマ表示名")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && slotDisplayName.text.trim() === ""
                            text: qsTr("表示名を入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 9
                        }
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: width >= 500 ? 2 : 1
                    columnSpacing: 12
                    rowSpacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: qsTr("開始時刻 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: slotStart
                            Layout.fillWidth: true
                            placeholderText: "14:10"
                            inputMethodHints: Qt.ImhTime
                            Accessible.name: qsTr("コマ開始時刻")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && slotStart.text.trim() === ""
                            text: qsTr("HH:mm形式で入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 9
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: qsTr("終了時刻 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: slotEnd
                            Layout.fillWidth: true
                            placeholderText: "15:30"
                            inputMethodHints: Qt.ImhTime
                            Accessible.name: qsTr("コマ終了時刻")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && slotEnd.text.trim() === ""
                            text: qsTr("HH:mm形式で入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 9
                        }
                    }

                }

                CheckBox {
                    id: slotEnabled
                    text: qsTr("このコマを時間割作成に使用する")
                    checked: true
                    onClicked: root.viewModel.markDirty()
                }

                Label {
                    visible: root.saveAttempted && root.viewModel.errorMessage
                    Layout.fillWidth: true
                    text: root.viewModel.errorMessage
                    color: "#a23b3b"
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        visible: root.editingId > 0
                        text: qsTr("削除…")
                        onClicked: deleteSlotDialog.open()
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    Button {
                        text: qsTr("キャンセル")
                        onClicked: {
                            if (root.selectedRow)
                                root.loadSlot(root.selectedRow)
                            else
                                root.clearSlot()
                            root.viewModel.discardDraft()
                        }
                    }

                    Button {
                        text: qsTr("保存")
                        highlighted: true
                        onClicked: root.savePendingChanges()
                    }
                }
            }
        }
    }

    Dialogs.MessageDialog {
        id: deleteSlotDialog

        title: qsTr("コマを削除")
        text: qsTr("%1を削除しますか？").arg(slotCode.text || qsTr("選択中のコマ"))
        informativeText: qsTr("関連データから参照されている場合は削除できません。使用しない場合は「使用する」のチェックを外してください。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.deleteTimeSlot(root.editingId)
        }
    }
}
