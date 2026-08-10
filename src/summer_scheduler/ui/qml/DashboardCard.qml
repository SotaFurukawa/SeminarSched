import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    UiTheme { id: theme }

    property string cardTitle: ""
    property string value: "—"
    property string description: ""
    property string markerText: "予定"
    property color accentColor: "#2767c5"
    property color markerBackground: "#e8f0ff"

    implicitHeight: 124
    radius: theme.radiusMd
    color: theme.surface
    border.color: theme.border
    border.width: 1
    Accessible.name: [cardTitle, value, description].join(" ")
    Accessible.role: Accessible.StaticText

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                Layout.fillWidth: true
                text: root.cardTitle
                color: theme.textSecondary
                font.pixelSize: 12
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Rectangle {
                Layout.preferredWidth: markerLabel.implicitWidth + 14
                Layout.preferredHeight: 22
                radius: 11
                color: root.markerBackground

                Label {
                    id: markerLabel

                    anchors.centerIn: parent
                    text: root.markerText
                    color: root.accentColor
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
            }
        }

        Label {
            text: root.value
            color: theme.textPrimary
            font.pixelSize: 28
            font.weight: Font.Bold
        }

        Label {
            Layout.fillWidth: true
            text: root.description
            color: theme.textSecondary
            font.pixelSize: 10
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }
    }
}
