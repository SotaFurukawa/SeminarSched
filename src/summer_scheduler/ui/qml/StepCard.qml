import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string stepNumber: "1"
    property string title: ""
    property string description: ""
    property string status: "pending"
    property string statusText: qsTr("未着手")
    property string actionText: ""
    property bool primaryAction: false
    signal actionRequested

    UiTheme { id: theme }

    implicitHeight: 170
    radius: theme.radiusMd
    color: theme.surface
    border.width: status === "current" ? 2 : 1
    border.color: status === "current" ? theme.accent : theme.border

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: theme.spacingLg
        spacing: theme.spacingSm

        RowLayout {
            Layout.fillWidth: true
            spacing: theme.spacingSm

            Rectangle {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                radius: 16
                color: root.status === "complete" ? theme.success
                       : root.status === "current" ? theme.accent : "#E7EAF0"

                Label {
                    anchors.centerIn: parent
                    text: root.status === "complete" ? "✓" : root.stepNumber
                    color: root.status === "complete" || root.status === "current"
                           ? "#FFFFFF" : theme.textSecondary
                    font.weight: Font.Bold
                }
            }

            Label {
                Layout.fillWidth: true
                text: root.title
                color: theme.textPrimary
                font.pixelSize: 16
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
            }

            StatusBadge {
                status: root.status
                label: root.statusText
                symbol: root.status === "current" ? "●"
                        : root.status === "warning" ? "△" : ""
            }
        }

        Label {
            Layout.fillWidth: true
            text: root.description
            color: theme.textSecondary
            font.pixelSize: theme.captionSize
            wrapMode: Text.Wrap
        }

        Item { Layout.fillHeight: true }

        AppButton {
            Layout.fillWidth: true
            text: root.actionText
            kind: root.primaryAction ? "primary" : "secondary"
            onClicked: root.actionRequested()
        }
    }
}
