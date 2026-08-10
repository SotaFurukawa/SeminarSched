import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.Button {
    id: root

    property string kind: "secondary"
    property color accentColor: theme.accent

    implicitHeight: theme.controlHeight
    implicitWidth: Math.max(96, contentItem.implicitWidth + 28)
    leftPadding: 14
    rightPadding: 14
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.Button

    UiTheme { id: theme }

    background: Rectangle {
        radius: theme.radiusSm
        color: {
            if (!root.enabled)
                return "#E8EBF0"
            if (root.kind === "primary")
                return root.down ? theme.accentHover : root.accentColor
            if (root.kind === "danger")
                return root.down ? "#8E1B12" : theme.danger
            return root.down ? "#EEF1F5" : root.hovered ? theme.surfaceSubtle : theme.surface
        }
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus
                      ? theme.accent
                      : root.kind === "secondary" ? theme.borderStrong : "transparent"
    }

    contentItem: Text {
        text: root.text
        color: !root.enabled
               ? "#98A2B3"
               : root.kind === "secondary" ? theme.textPrimary : "#FFFFFF"
        font.pixelSize: theme.bodySize
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
