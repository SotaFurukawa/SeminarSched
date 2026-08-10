import QtQuick
import QtQuick.Controls.Basic as Basic
import QtQuick.Layouts

Basic.Button {
    id: root

    property string itemTitle: ""
    property string iconText: ""
    property string stepPrefix: ""
    property bool selected: false

    UiTheme { id: theme }

    implicitHeight: 42
    leftPadding: 10
    rightPadding: 8
    focusPolicy: Qt.StrongFocus
    Accessible.name: (stepPrefix ? stepPrefix + " " : "") + itemTitle
                     + (selected ? qsTr("、選択中") : "")
    Accessible.description: selected ? qsTr("現在表示している画面です")
                                     : qsTr("この画面を表示します")
    Accessible.role: Accessible.Button

    background: Rectangle {
        radius: theme.radiusSm
        color: root.selected ? theme.accentSoft
               : root.hovered ? theme.surfaceSubtle : "transparent"
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? theme.accent
                      : root.selected ? "#B2D7F0" : "transparent"

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: 6
            anchors.bottomMargin: 6
            width: 4
            radius: 2
            visible: root.selected
            color: theme.accent
        }
    }

    contentItem: RowLayout {
        spacing: theme.spacingSm

        Rectangle {
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            radius: 7
            color: root.selected ? theme.accent : "#EDF1F6"

            Text {
                anchors.centerIn: parent
                text: root.iconText
                color: root.selected ? "#FFFFFF" : theme.textSecondary
                font.pixelSize: 12
                font.weight: Font.Bold
            }
        }

        Text {
            visible: root.stepPrefix.length > 0
            text: root.stepPrefix
            color: root.selected ? theme.accent : theme.textSecondary
            font.pixelSize: theme.captionSize
            font.weight: Font.DemiBold
        }

        Text {
            Layout.fillWidth: true
            text: root.itemTitle
            color: root.selected ? theme.accent : theme.textPrimary
            font.pixelSize: 13
            font.weight: root.selected ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
        }
    }
}
