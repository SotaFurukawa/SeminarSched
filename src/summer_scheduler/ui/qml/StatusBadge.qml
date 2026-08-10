import QtQuick
import QtQuick.Controls

Rectangle {
    id: root

    property string status: "neutral"
    property string label: ""
    property string symbol: ""

    UiTheme { id: theme }

    implicitWidth: badgeLabel.implicitWidth + 20
    implicitHeight: 28
    radius: 14
    color: status === "complete" ? theme.successSoft
           : status === "current" ? theme.accentSoft
           : status === "warning" ? theme.warningSoft
           : status === "error" ? theme.dangerSoft
           : theme.surfaceSubtle
    border.color: status === "complete" ? "#ABEFC6"
                  : status === "current" ? "#B2D7F0"
                  : status === "warning" ? "#F3D690"
                  : status === "error" ? "#F1B5B0"
                  : theme.border
    Accessible.name: badgeLabel.text
    Accessible.role: Accessible.StaticText

    Label {
        id: badgeLabel
        anchors.centerIn: parent
        text: (root.symbol ? root.symbol + " " : "") + root.label
        color: root.status === "complete" ? theme.success
               : root.status === "current" ? theme.accent
               : root.status === "warning" ? theme.warning
               : root.status === "error" ? theme.danger
               : theme.textSecondary
        font.pixelSize: theme.captionSize
        font.weight: Font.DemiBold
    }
}
