import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root

    required property var viewModel
    property bool saveAttempted: false
    readonly property string generatedTitle: String(projectYear.currentText)
                                             + String(projectSeason.currentText)
                                             + qsTr("講習")

    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

    function reload() {
        const title = String(root.viewModel.currentProjectTitle || "")
        const yearMatch = title.match(/(20\d{2})/)
        const wantedYear = yearMatch ? yearMatch[1] : String(new Date().getFullYear())
        for (let index = 0; index < projectYear.count; ++index) {
            if (String(projectYear.model[index]) === wantedYear) {
                projectYear.currentIndex = index
                break
            }
        }
        if (title.indexOf("春期") >= 0)
            projectSeason.currentIndex = 0
        else if (title.indexOf("冬期") >= 0)
            projectSeason.currentIndex = 2
        else
            projectSeason.currentIndex = 1
        startDate.setDateString(root.viewModel.currentStartDate || "")
        endDate.setDateString(root.viewModel.currentEndDate || "")
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
                            text: qsTr("年度 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        ComboBox {
                            id: projectYear
                            Layout.fillWidth: true
                            model: {
                                const years = []
                                for (let year = 2020; year <= 2070; ++year)
                                    years.push(String(year))
                                return years
                            }
                            currentIndex: Math.max(0, Math.min(50,
                                                               new Date().getFullYear() - 2020))
                            Accessible.name: qsTr("講習年度")
                            onActivated: root.viewModel.markDirty()
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: qsTr("講習区分 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        ComboBox {
                            id: projectSeason
                            Layout.fillWidth: true
                            model: [qsTr("春期"), qsTr("夏期"), qsTr("冬期")]
                            currentIndex: 1
                            onActivated: root.viewModel.markDirty()
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: qsTr("プロジェクト名：%1").arg(root.generatedTitle)
                    color: "#183b59"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
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
                        DateDropdownField {
                            id: startDate
                            Layout.fillWidth: true
                            fromYear: 2020
                            toYear: 2070
                            accessibleName: qsTr("講習開始日")
                            onDateEdited: root.viewModel.markDirty()
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
                        DateDropdownField {
                            id: endDate
                            Layout.fillWidth: true
                            fromYear: 2020
                            toYear: 2070
                            accessibleName: qsTr("講習終了日")
                            onDateEdited: root.viewModel.markDirty()
                        }
                    }
                }

                Label {
                    visible: root.saveAttempted && startDate.dateText > endDate.dateText
                    Layout.fillWidth: true
                    text: qsTr("終了日は開始日以降を選択してください。")
                    color: "#a23b3b"
                    font.pixelSize: 10
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
                            if (startDate.dateText > endDate.dateText)
                                return
                            root.viewModel.saveProjectInfo(
                                        root.generatedTitle,
                                        root.viewModel.currentCampusName || "既定校舎",
                                        startDate.dateText,
                                        endDate.dateText)
                        }
                    }
                }
            }
        }
    }
}
