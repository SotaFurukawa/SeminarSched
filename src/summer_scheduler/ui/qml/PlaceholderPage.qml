import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property string pageTitle
    required property string phaseLabel
    required property string description

    ScrollView {
        id: placeholderScroll

        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        Item {
            width: placeholderScroll.availableWidth
            height: Math.max(
                        placeholderScroll.availableHeight,
                        placeholderContent.implicitHeight + 48
                    )

            ColumnLayout {
                id: placeholderContent

                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.topMargin: 24
                anchors.leftMargin: 28
                anchors.rightMargin: 28
                spacing: 18

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            text: root.pageTitle
                            color: "#18212f"
                            font.pixelSize: 24
                            font.weight: Font.Bold
                        }

                        Label {
                            text: qsTr("画面構成を先に用意しています")
                            color: "#667085"
                            font.pixelSize: 12
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: phaseLabelText.implicitWidth + 20
                        Layout.preferredHeight: 28
                        radius: 14
                        color: "#f2f4f7"
                        border.color: "#d0d5dd"

                        Label {
                            id: phaseLabelText

                            anchors.centerIn: parent
                            text: root.phaseLabel
                            color: "#475467"
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.minimumHeight: 270
                    implicitHeight: placeholderPanelContent.implicitHeight + 64
                    radius: 12
                    color: "#ffffff"
                    border.color: "#dce2ea"

                    ColumnLayout {
                        id: placeholderPanelContent

                        anchors.centerIn: parent
                        width: Math.min(parent.width - 48, 540)
                        spacing: 12

                        Rectangle {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: 54
                            Layout.preferredHeight: 54
                            radius: 14
                            color: "#edf1f6"
                            border.color: "#d6dde7"

                            Label {
                                anchors.centerIn: parent
                                text: "…"
                                color: "#52647d"
                                font.pixelSize: 24
                                font.weight: Font.Bold
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            text: qsTr("%1で実装予定").arg(root.phaseLabel)
                            color: "#344054"
                            font.pixelSize: 17
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            text: root.description
                            color: "#667085"
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }

                        Label {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            text: qsTr("現在は閲覧用プレースホルダーです。データの登録・変更は行いません。")
                            color: "#7a8493"
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }
                    }
                }
            }
        }
    }
}
