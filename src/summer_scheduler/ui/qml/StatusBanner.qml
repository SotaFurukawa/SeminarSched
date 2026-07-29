import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    required property var viewModel
    readonly property bool hasError: Boolean(viewModel.errorMessage)
    readonly property string messageText: hasError
                                                  ? viewModel.errorMessage
                                                  : viewModel.statusMessage || ""

    visible: messageText.length > 0
    implicitHeight: visible ? bannerContent.implicitHeight + 14 : 0
    color: hasError ? "#fff1f0" : "#edf7ee"
    border.color: hasError ? "#e5aaa6" : "#a7d3ad"
    clip: true

    RowLayout {
        id: bannerContent

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 18
        anchors.rightMargin: 12
        spacing: 10

        Label {
            text: root.hasError ? qsTr("エラー") : qsTr("完了")
            color: root.hasError ? "#9f2f2a" : "#256b35"
            font.pixelSize: 11
            font.weight: Font.Bold
        }

        Label {
            Layout.fillWidth: true
            text: root.messageText
            color: root.hasError ? "#7d2925" : "#245d30"
            font.pixelSize: 11
            wrapMode: Text.Wrap
        }

        ToolButton {
            text: qsTr("閉じる")
            Accessible.name: qsTr("通知を閉じる")
            onClicked: root.viewModel.clearMessages()
        }
    }
}
