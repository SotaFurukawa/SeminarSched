pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var rows
    property string emptyText: qsTr("差分はありません。")

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function operationLabel(value) {
        const operation = String(value)
        if (operation === "add")
            return qsTr("＋ 追加")
        if (operation === "change")
            return qsTr("↻ 変更")
        if (operation === "unchanged")
            return qsTr("＝ 変更なし")
        if (operation === "delete_candidate")
            return qsTr("－ 削除候補")
        return operation || qsTr("不明")
    }

    function operationColor(value) {
        const operation = String(value)
        if (operation === "add")
            return "#176b40"
        if (operation === "change")
            return "#174f9e"
        if (operation === "delete_candidate")
            return "#9a3412"
        return "#667085"
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            color: "#eef2f6"
            border.color: "#dce2ea"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 9
                anchors.rightMargin: 9
                spacing: 8

                Label {
                    Layout.preferredWidth: 86
                    text: qsTr("差分")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.preferredWidth: 118
                    text: qsTr("対象")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.preferredWidth: 78
                    text: qsTr("日付")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.preferredWidth: 42
                    text: qsTr("コマ")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.preferredWidth: 82
                    text: qsTr("変更前")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.preferredWidth: 82
                    text: qsTr("変更後")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.fillWidth: true
                    text: qsTr("内容")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
            }
        }

        ListView {
            id: diffList

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 1
            model: root.rows || []
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            delegate: Rectangle {
                id: diffDelegate

                required property int index
                required property var modelData

                width: ListView.view.width
                height: 37
                color: index % 2 === 0 ? "#ffffff" : "#f8fafc"
                border.color: "#edf0f4"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 9
                    anchors.rightMargin: 9
                    spacing: 8

                    Label {
                        Layout.preferredWidth: 86
                        text: root.operationLabel(
                                  root.rowValue(diffDelegate.modelData, "operation", ""))
                        color: root.operationColor(
                                   root.rowValue(diffDelegate.modelData, "operation", ""))
                        font.pixelSize: 9
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.preferredWidth: 118
                        text: root.rowValue(diffDelegate.modelData, "entityName",
                                            root.rowValue(diffDelegate.modelData,
                                                          "groupCode", ""))
                        color: "#344054"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.preferredWidth: 78
                        text: root.rowValue(diffDelegate.modelData, "date", "")
                        color: "#475467"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.preferredWidth: 42
                        text: root.rowValue(diffDelegate.modelData, "slotCode", "")
                        color: "#475467"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.preferredWidth: 82
                        text: root.rowValue(diffDelegate.modelData, "before", "")
                        color: "#667085"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.preferredWidth: 82
                        text: root.rowValue(diffDelegate.modelData, "after", "")
                        color: "#344054"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.rowValue(diffDelegate.modelData, "message", "")
                        color: "#344054"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: diffList.count === 0
            text: root.emptyText
            color: "#7a8493"
            font.pixelSize: 10
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
}
