pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

Rectangle {
    id: root

    required property var itemsModel
    property int currentIndex: 0
    signal pageSelected(int index)

    implicitWidth: 232
    color: "#ffffff"

    ColumnLayout {
        id: sidebarHeading

        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 18
        spacing: 2

        Label {
            text: qsTr("メニュー")
            color: "#18212f"
            font.pixelSize: 15
            font.weight: Font.DemiBold
        }

        Label {
            text: qsTr("機能を選択してください")
            color: "#7a8493"
            font.pixelSize: 11
        }
    }

    ListView {
        id: navigationList

        anchors.top: sidebarHeading.bottom
        anchors.bottom: sidebarFooter.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 18
        anchors.bottomMargin: 12
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        spacing: 4
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: root.itemsModel
        currentIndex: root.currentIndex

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        delegate: Basic.Button {
            id: navigationButton

            required property int index
            required property string title
            required property string shortLabel
            readonly property string itemTitle: title
            readonly property string itemShortLabel: shortLabel

            width: ListView.view.width
            height: 46
            leftPadding: 12
            rightPadding: 9
            topPadding: 5
            bottomPadding: 5
            checkable: true
            checked: index === root.currentIndex
            focusPolicy: Qt.StrongFocus
            Accessible.name: itemTitle + (checked ? qsTr("、選択中") : "")
            Accessible.description: checked
                                    ? qsTr("現在表示している画面です")
                                    : qsTr("この画面を表示します")
            Accessible.role: Accessible.Button

            onClicked: root.pageSelected(index)

            background: Rectangle {
                radius: 7
                color: navigationButton.checked
                       ? "#e8f0ff"
                       : navigationButton.hovered
                         ? "#f2f5f9"
                         : "transparent"
                border.color: navigationButton.activeFocus
                              ? "#2767c5"
                              : navigationButton.checked
                                ? "#bfd3f5"
                                : "transparent"
                border.width: navigationButton.activeFocus ? 2 : 1

                Rectangle {
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.topMargin: 7
                    anchors.bottomMargin: 7
                    width: 4
                    radius: 2
                    visible: navigationButton.checked
                    color: "#2767c5"
                }
            }

            contentItem: RowLayout {
                spacing: 9

                Rectangle {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    radius: 7
                    color: navigationButton.checked ? "#2767c5" : "#edf1f6"

                    Label {
                        anchors.centerIn: parent
                        text: navigationButton.itemShortLabel
                        color: navigationButton.checked ? "#ffffff" : "#475467"
                        font.pixelSize: 12
                        font.weight: Font.Bold
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: navigationButton.itemTitle
                    color: navigationButton.checked ? "#174f9e" : "#344054"
                    font.pixelSize: 13
                    font.weight: navigationButton.checked ? Font.DemiBold : Font.Normal
                    elide: Text.ElideRight
                }

                Label {
                    visible: navigationButton.checked
                    text: qsTr("選択中")
                    color: "#174f9e"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
            }
        }
    }

    Rectangle {
        id: sidebarFooter

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 44
        color: "#f8fafc"
        border.color: "#e5e9ef"
        border.width: 1

        Label {
            anchors.centerIn: parent
            text: qsTr("端末内に保存・オフライン動作")
            color: "#667085"
            font.pixelSize: 10
        }
    }
}
