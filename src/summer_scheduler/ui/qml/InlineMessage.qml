import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string kind: "info"
    property string message: ""
    property string actionText: ""
    signal actionRequested

    UiTheme { id: theme }

    visible: message.length > 0
    implicitHeight: visible ? messageRow.implicitHeight + 20 : 0
    radius: theme.radiusSm
    color: kind === "error" ? theme.dangerSoft
           : kind === "warning" ? theme.warningSoft
           : kind === "success" ? theme.successSoft
           : theme.infoSoft
    border.color: kind === "error" ? "#F1B5B0"
                  : kind === "warning" ? "#F3D690"
                  : kind === "success" ? "#ABEFC6"
                  : "#B2DDFF"

    RowLayout {
        id: messageRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 12
        anchors.rightMargin: 10
        spacing: 10

        Label {
            text: root.kind === "error" ? "✕"
                  : root.kind === "warning" ? "△"
                  : root.kind === "success" ? "✓" : "ⓘ"
            color: root.kind === "error" ? theme.danger
                   : root.kind === "warning" ? theme.warning
                   : root.kind === "success" ? theme.success : theme.info
            font.pixelSize: 16
            font.weight: Font.Bold
        }

        Label {
            Layout.fillWidth: true
            text: root.message
            color: theme.textPrimary
            font.pixelSize: theme.captionSize
            wrapMode: Text.Wrap
        }

        AppButton {
            visible: root.actionText.length > 0
            text: root.actionText
            onClicked: root.actionRequested()
        }
    }
}
