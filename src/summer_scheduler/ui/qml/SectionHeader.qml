import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root

    property string title: ""
    property string description: ""

    UiTheme { id: theme }

    spacing: theme.spacingMd

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2

        Label {
            text: root.title
            color: theme.textPrimary
            font.pixelSize: theme.titleSize
            font.weight: Font.Bold
        }

        Label {
            Layout.fillWidth: true
            visible: root.description.length > 0
            text: root.description
            color: theme.textSecondary
            font.pixelSize: theme.captionSize
            wrapMode: Text.Wrap
        }
    }
}
