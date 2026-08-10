import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root

    property string symbol: "○"
    property string title: ""
    property string description: ""
    property string actionText: ""
    signal actionRequested

    UiTheme { id: theme }

    spacing: theme.spacingMd

    Label {
        Layout.alignment: Qt.AlignHCenter
        text: root.symbol
        color: theme.textSecondary
        font.pixelSize: 32
    }
    Label {
        Layout.fillWidth: true
        text: root.title
        color: theme.textPrimary
        font.pixelSize: theme.sectionSize
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
    }
    Label {
        Layout.fillWidth: true
        text: root.description
        color: theme.textSecondary
        font.pixelSize: theme.bodySize
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
    }
    AppButton {
        Layout.alignment: Qt.AlignHCenter
        visible: root.actionText.length > 0
        kind: "primary"
        text: root.actionText
        onClicked: root.actionRequested()
    }
}
