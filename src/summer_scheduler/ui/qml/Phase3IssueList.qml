pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var rows
    property string emptyText: qsTr("エラー・警告はありません。")

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function severityLabel(value) {
        const severity = String(value).toLowerCase()
        if (severity === "error")
            return qsTr("✕ エラー")
        if (severity === "warning")
            return qsTr("△ 警告")
        return qsTr("ⓘ 情報")
    }

    function severityColor(value) {
        const severity = String(value).toLowerCase()
        if (severity === "error")
            return "#a23b3b"
        if (severity === "warning")
            return "#8a5a00"
        return "#174f9e"
    }

    function locationText(row) {
        const parts = []
        const sheet = root.rowValue(row, "sheet", "")
        const line = root.rowValue(row, "row", "")
        const column = root.rowValue(row, "column", "")
        if (sheet !== "")
            parts.push(qsTr("シート：%1").arg(sheet))
        if (line !== "")
            parts.push(qsTr("%1行").arg(line))
        if (column !== "")
            parts.push(qsTr("列：%1").arg(column))
        return parts.join(" / ")
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
                    Layout.preferredWidth: 82
                    text: qsTr("重要度")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.preferredWidth: 210
                    text: qsTr("入力位置")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.fillWidth: true
                    text: qsTr("検証内容")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
            }
        }

        ListView {
            id: issueList

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
                id: issueDelegate

                required property int index
                required property var modelData

                width: ListView.view.width
                height: 39
                color: index % 2 === 0 ? "#ffffff" : "#f8fafc"
                border.color: "#edf0f4"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 9
                    anchors.rightMargin: 9
                    spacing: 8

                    Label {
                        Layout.preferredWidth: 82
                        text: root.severityLabel(
                                  root.rowValue(issueDelegate.modelData, "severity", "info"))
                        color: root.severityColor(
                                   root.rowValue(issueDelegate.modelData, "severity", "info"))
                        font.pixelSize: 9
                        font.weight: Font.DemiBold
                    }
                    Label {
                        Layout.preferredWidth: 210
                        text: root.locationText(issueDelegate.modelData)
                        color: "#667085"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.rowValue(issueDelegate.modelData, "message", "")
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
            visible: issueList.count === 0
            text: root.emptyText
            color: "#176b40"
            font.pixelSize: 10
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }
}
