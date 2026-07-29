import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel

    ScrollView {
        id: dashboardScroll

        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        Item {
            width: dashboardScroll.availableWidth
            height: dashboardContent.implicitHeight + 48

            ColumnLayout {
                id: dashboardContent

                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.topMargin: 24
                anchors.leftMargin: 28
                anchors.rightMargin: 28
                spacing: 18

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            text: qsTr("ホーム")
                            color: "#18212f"
                            font.pixelSize: 24
                            font.weight: Font.Bold
                        }

                        Label {
                            text: qsTr("アプリ基盤の状態と講習準備の概要")
                            color: "#667085"
                            font.pixelSize: 12
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: dashboardPhaseLabel.implicitWidth + 20
                        Layout.preferredHeight: 28
                        radius: 14
                        color: "#edf4ff"
                        border.color: "#bfd3f5"

                        Label {
                            id: dashboardPhaseLabel

                            anchors.centerIn: parent
                            text: qsTr("Phase 1・土台")
                            color: "#174f9e"
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: welcomeContent.implicitHeight + 30
                    radius: 10
                    color: "#f8fbff"
                    border.color: "#cbdcf5"

                    RowLayout {
                        id: welcomeContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 18
                        anchors.rightMargin: 18
                        spacing: 13

                        Rectangle {
                            Layout.preferredWidth: 38
                            Layout.preferredHeight: 38
                            radius: 9
                            color: "#2767c5"

                            Label {
                                anchors.centerIn: parent
                                text: "✓"
                                color: "#ffffff"
                                font.pixelSize: 19
                                font.weight: Font.Bold
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3

                            Label {
                                Layout.fillWidth: true
                                text: qsTr("アプリの土台を利用できます")
                                color: "#1d3f70"
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }

                            Label {
                                Layout.fillWidth: true
                                text: qsTr("このダッシュボードの集計値と業務機能は、次のPhaseから順次接続されます。")
                                color: "#52647d"
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }

                Label {
                    text: qsTr("講習サマリー（仮表示）")
                    color: "#344054"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: width >= 820 ? 3 : width >= 520 ? 2 : 1
                    columnSpacing: 12
                    rowSpacing: 12

                    DashboardCard {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 180
                        cardTitle: qsTr("生徒数")
                        description: qsTr("Phase 2で生徒管理と接続")
                    }

                    DashboardCard {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 180
                        cardTitle: qsTr("講師数")
                        description: qsTr("Phase 2で講師管理と接続")
                    }

                    DashboardCard {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 180
                        cardTitle: qsTr("必要授業数")
                        description: qsTr("受講希望の登録後に集計")
                    }

                    DashboardCard {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 180
                        cardTitle: qsTr("配置済み")
                        description: qsTr("Phase 4以降で最適化結果と接続")
                    }

                    DashboardCard {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 180
                        cardTitle: qsTr("未配置")
                        description: qsTr("未配置理由と解決候補を集計")
                        accentColor: "#9b5d0a"
                        markerBackground: "#fff4db"
                    }

                    DashboardCard {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 180
                        cardTitle: qsTr("警告")
                        description: qsTr("入力検証・制約警告を集計")
                        accentColor: "#a23b3b"
                        markerBackground: "#fff0f0"
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: statusContent.implicitHeight + 30
                    radius: 10
                    color: "#ffffff"
                    border.color: "#dce2ea"

                    ColumnLayout {
                        id: statusContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 18
                        anchors.rightMargin: 18
                        spacing: 10

                        Label {
                            text: qsTr("基盤ステータス")
                            color: "#344054"
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 20

                            Label {
                                Layout.fillWidth: true
                                text: qsTr("✓ QMLユーザーインターフェース")
                                color: "#176b40"
                                font.pixelSize: 11
                            }

                            Label {
                                Layout.fillWidth: true
                                text: (root.viewModel.databaseReady ? "✓ " : "… ")
                                      + root.viewModel.databaseStatusText
                                color: root.viewModel.databaseReady ? "#176b40" : "#7a5710"
                                font.pixelSize: 11
                            }

                            Label {
                                Layout.fillWidth: true
                                text: qsTr("○ 業務機能はPhase 2以降")
                                color: "#667085"
                                font.pixelSize: 11
                            }
                        }
                    }
                }
            }
        }
    }
}
