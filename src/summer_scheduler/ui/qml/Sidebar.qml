pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    required property var itemsModel
    required property bool projectOpen
    property int currentIndex: 0
    signal pageSelected(int index)

    UiTheme { id: theme }

    implicitWidth: 248
    color: theme.surface

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 18
            Layout.rightMargin: 18
            Layout.topMargin: 16
            Layout.bottomMargin: 12
            spacing: 2

            Label {
                text: qsTr("業務メニュー")
                color: theme.textPrimary
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }

            Label {
                text: qsTr("上から順に進められます")
                color: theme.textSecondary
                font.pixelSize: theme.captionSize
            }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            ColumnLayout {
                width: parent.width
                spacing: 3

                SidebarNavButton {
                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    itemTitle: root.itemsModel.get(0).title
                    iconText: root.itemsModel.get(0).shortLabel
                    selected: root.currentIndex === 0
                    onClicked: root.pageSelected(0)
                }

                Item {
                    Layout.fillWidth: true
                    implicitHeight: workflowColumn.implicitHeight

                    ColumnLayout {
                        id: workflowColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: 3

                        Label {
                            Layout.leftMargin: 18
                            Layout.topMargin: 12
                            Layout.bottomMargin: 3
                            text: qsTr("業務フロー")
                            color: theme.textSecondary
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                        }

                        Repeater {
                            model: [
                                {"index": 8, "prefix": "①"},
                                {"index": 9, "prefix": "②"},
                                {"index": 4, "prefix": "③"},
                                {"index": 10, "prefix": "④"},
                                {"index": 5, "prefix": "⑤"},
                                {"index": 7, "prefix": "⑥"}
                            ]

                            delegate: SidebarNavButton {
                                id: workflowButton
                                required property var modelData
                                readonly property int targetIndex: Number(modelData.index)
                                Layout.fillWidth: true
                                Layout.leftMargin: 10
                                Layout.rightMargin: 10
                                enabled: root.projectOpen
                                itemTitle: root.itemsModel.get(targetIndex).title
                                iconText: root.itemsModel.get(targetIndex).shortLabel
                                stepPrefix: String(modelData.prefix)
                                selected: root.currentIndex === targetIndex
                                onClicked: root.pageSelected(targetIndex)
                            }
                        }
                    }

                    Rectangle {
                        anchors.fill: parent
                        visible: !root.projectOpen
                        z: 10
                        radius: 7
                        color: "#e3e6eb"
                        opacity: 0.88

                        Label {
                            anchors.centerIn: parent
                            width: parent.width - 28
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            text: qsTr("プロジェクトが開かれていません")
                            color: "#667085"
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }

                        MouseArea { anchors.fill: parent }
                    }
                }

                Label {
                    Layout.leftMargin: 18
                    Layout.topMargin: 12
                    Layout.bottomMargin: 3
                    text: qsTr("データ")
                    color: theme.textSecondary
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }

                Repeater {
                    model: [1, 2, 3]

                    delegate: SidebarNavButton {
                        id: dataButton
                        required property int modelData
                        Layout.fillWidth: true
                        Layout.leftMargin: 10
                        Layout.rightMargin: 10
                        itemTitle: root.itemsModel.get(modelData).title
                        iconText: root.itemsModel.get(modelData).shortLabel
                        selected: root.currentIndex === modelData
                        onClicked: root.pageSelected(modelData)
                    }
                }

                Label {
                    Layout.leftMargin: 18
                    Layout.topMargin: 12
                    Layout.bottomMargin: 3
                    text: qsTr("確認")
                    color: theme.textSecondary
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }

                SidebarNavButton {
                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    itemTitle: root.itemsModel.get(6).title
                    iconText: root.itemsModel.get(6).shortLabel
                    selected: root.currentIndex === 6
                    onClicked: root.pageSelected(6)
                }

                Item { Layout.preferredHeight: 12 }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            color: theme.surfaceSubtle
            border.color: theme.border
            border.width: 1

            Label {
                anchors.centerIn: parent
                text: qsTr("🔒 端末内に保存・オフライン動作")
                color: theme.textSecondary
                font.pixelSize: 11
            }
        }
    }
}
