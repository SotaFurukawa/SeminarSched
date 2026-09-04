import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested

    component SettingsTabButton: TabButton {
        id: tabButton

        implicitHeight: 42
        font.pixelSize: 12
        font.weight: Font.DemiBold

        background: Rectangle {
            radius: 7
            color: tabButton.checked ? "#0f6cbd"
                                     : tabButton.hovered ? "#f4f7fb" : "#ffffff"
            border.width: 1
            border.color: tabButton.checked ? "#0f6cbd" : "#c5ccd8"
        }

        contentItem: Text {
            text: tabButton.text
            color: tabButton.checked ? "#ffffff" : "#344054"
            font: tabButton.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Label {
                    text: qsTr("設定")
                    color: "#18212f"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                }

                Label {
                    text: qsTr("プロジェクト、コマ、開校日、科目を設定します。")
                    color: "#667085"
                    font.pixelSize: 11
                }
            }

            Button {
                text: qsTr("再読込み")
                enabled: root.viewModel.hasOpenProject
                onClicked: root.viewModel.refreshAll()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.viewModel.hasOpenProject
            radius: 12
            color: "#ffffff"
            border.color: "#dce2ea"

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 540)
                spacing: 12

                Label {
                    Layout.fillWidth: true
                    text: qsTr("プロジェクトが開かれていません")
                    horizontalAlignment: Text.AlignHCenter
                    color: "#344054"
                    font.pixelSize: 18
                    font.weight: Font.DemiBold
                }

                Label {
                    Layout.fillWidth: true
                    text: qsTr("これらの設定は.jukuscheduleプロジェクトごとに保存されます。")
                    horizontalAlignment: Text.AlignHCenter
                    color: "#667085"
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }

                Button {
                    Layout.alignment: Qt.AlignHCenter
                    text: qsTr("ホームへ移動")
                    onClicked: root.openHomeRequested()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.viewModel.hasOpenProject
            radius: 9
            color: "#ffffff"
            border.color: "#dce2ea"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8

                TabBar {
                    id: settingsTabs

                    Layout.fillWidth: true
                    spacing: 8
                    background: Item {}

                    SettingsTabButton {
                        width: (settingsTabs.width - settingsTabs.spacing * 3) / 4
                        text: qsTr("プロジェクト")
                    }
                    SettingsTabButton {
                        width: (settingsTabs.width - settingsTabs.spacing * 3) / 4
                        text: qsTr("コマ設定")
                    }
                    SettingsTabButton {
                        width: (settingsTabs.width - settingsTabs.spacing * 3) / 4
                        text: qsTr("開校日・休校日")
                    }
                    SettingsTabButton {
                        width: (settingsTabs.width - settingsTabs.spacing * 3) / 4
                        text: qsTr("科目")
                    }
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: settingsTabs.currentIndex

                    ProjectSettingsTab {
                        viewModel: root.viewModel
                    }

                    TimeSlotSettingsTab {
                        viewModel: root.viewModel
                    }

                    OpenDateSettingsTab {
                        viewModel: root.viewModel
                    }

                    SubjectSettingsTab {
                        viewModel: root.viewModel
                    }

                }
            }
        }
    }
}
