import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root

    required property var viewModel
    property bool saveAttempted: false

    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

    function reload() {
        projectTitle.text = root.viewModel.currentProjectTitle || ""
        campusName.text = root.viewModel.currentCampusName || ""
        startDate.text = root.viewModel.currentStartDate || ""
        endDate.text = root.viewModel.currentEndDate || ""
        root.saveAttempted = false
    }

    Component.onCompleted: reload()

    ColumnLayout {
        width: root.availableWidth
        spacing: 12

        Label {
            text: qsTr("プロジェクト情報")
            color: "#344054"
            font.pixelSize: 17
            font.weight: Font.DemiBold
        }

        Label {
            Layout.fillWidth: true
            text: qsTr("講習期間を変更すると、期間内の開校日データが更新されます。既存データへの影響は保存時に検証されます。")
            color: "#667085"
            font.pixelSize: 10
            wrapMode: Text.Wrap
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: formContent.implicitHeight + 32
            radius: 9
            color: "#f8fafc"
            border.color: "#e2e7ee"

            ColumnLayout {
                id: formContent

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 14

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            text: qsTr("プロジェクト名 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: projectTitle
                            Layout.fillWidth: true
                            Accessible.name: qsTr("プロジェクト名")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && projectTitle.text.trim() === ""
                            text: qsTr("プロジェクト名を入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 10
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            text: qsTr("校舎名 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: campusName
                            Layout.fillWidth: true
                            Accessible.name: qsTr("校舎名")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && campusName.text.trim() === ""
                            text: qsTr("校舎名を入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 10
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 14

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            text: qsTr("講習開始日 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: startDate
                            Layout.fillWidth: true
                            placeholderText: "2026-07-20"
                            Accessible.name: qsTr("講習開始日")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && startDate.text.trim() === ""
                            text: qsTr("開始日をYYYY-MM-DDで入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 10
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            text: qsTr("講習終了日 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: endDate
                            Layout.fillWidth: true
                            placeholderText: "2026-08-31"
                            Accessible.name: qsTr("講習終了日")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && endDate.text.trim() === ""
                            text: qsTr("終了日をYYYY-MM-DDで入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 10
                        }
                    }
                }

                Label {
                    visible: root.saveAttempted && root.viewModel.errorMessage
                    Layout.fillWidth: true
                    text: root.viewModel.errorMessage
                    color: "#a23b3b"
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }

                RowLayout {
                    Layout.fillWidth: true

                    Label {
                        Layout.fillWidth: true
                        text: root.viewModel.isDirty
                              ? qsTr("● このプロジェクトには未保存の変更があります")
                              : qsTr("✓ プロジェクトは保存済みです")
                        color: root.viewModel.isDirty ? "#7a5710" : "#176b40"
                        font.pixelSize: 10
                    }

                    Button {
                        text: qsTr("キャンセル")
                        onClicked: {
                            root.reload()
                            root.viewModel.discardDraft()
                        }
                    }

                    Button {
                        text: qsTr("変更を保存")
                        highlighted: true
                        onClicked: {
                            root.saveAttempted = true
                            if (projectTitle.text.trim() === ""
                                    || campusName.text.trim() === ""
                                    || startDate.text.trim() === ""
                                    || endDate.text.trim() === "")
                                return
                            root.viewModel.saveProjectInfo(
                                        projectTitle.text.trim(),
                                        campusName.text.trim(),
                                        startDate.text.trim(),
                                        endDate.text.trim())
                        }
                    }
                }
            }
        }
    }
}
