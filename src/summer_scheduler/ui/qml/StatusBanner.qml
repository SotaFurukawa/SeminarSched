import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    UiTheme { id: theme }

    required property var viewModel
    readonly property bool hasError: Boolean(viewModel.errorMessage)
    readonly property string messageText: hasError
                                                  ? viewModel.errorMessage
                                                  : viewModel.statusMessage || ""

    visible: messageText.length > 0
    implicitHeight: visible ? bannerContent.implicitHeight + 14 : 0
    color: hasError ? theme.dangerSoft : theme.successSoft
    border.color: hasError ? "#F1B5B0" : "#ABEFC6"
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
            color: root.hasError ? theme.danger : theme.success
            font.pixelSize: theme.captionSize
            font.weight: Font.Bold
        }

        Label {
            Layout.fillWidth: true
            text: root.messageText
            color: theme.textPrimary
            font.pixelSize: theme.captionSize
            wrapMode: Text.Wrap
        }

        ToolButton {
            text: qsTr("閉じる")
            Accessible.name: qsTr("通知を閉じる")
            onClicked: root.viewModel.clearMessages()
        }
    }
}
