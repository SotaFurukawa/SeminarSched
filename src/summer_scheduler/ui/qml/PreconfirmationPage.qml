pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested
    signal openTimetableRequested

    UiTheme { id: theme }

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function availableDates() {
        const result = []
        const rows = root.viewModel.dateTabs || []
        for (let i = 0; i < rows.length; ++i) {
            if (Boolean(root.rowValue(rows[i], "isOpen", false)))
                result.push(rows[i])
        }
        return result
    }

    function enabledSlots() {
        const result = []
        const rows = root.viewModel.slotHeaders || []
        for (let i = 0; i < rows.length; ++i) {
            if (Boolean(root.rowValue(rows[i], "enabled", false)))
                result.push(rows[i])
        }
        return result
    }

    function activeTeachers() {
        const result = []
        const rows = root.viewModel.teacherHeaders || []
        for (let i = 0; i < rows.length; ++i) {
            if (Boolean(root.rowValue(rows[i], "active", false)))
                result.push(rows[i])
        }
        return result
    }

    function selectedRow(box) {
        if (!box.model || box.currentIndex < 0 || box.currentIndex >= box.model.length)
            return null
        return box.model[box.currentIndex]
    }

    Component.onCompleted: root.viewModel.refreshSchedule()

    Rectangle {
        anchors.fill: parent
        anchors.margins: 20
        visible: !root.viewModel.hasOpenProject
        radius: 10
        color: "#ffffff"
        border.color: "#dce2ea"

        EmptyState {
            anchors.centerIn: parent
            title: qsTr("プロジェクトが開かれていません")
            description: qsTr("事前確定枠はプロジェクトの時間割へ保存します。")
            actionText: qsTr("ホームへ移動")
            onActionRequested: root.openHomeRequested()
        }
    }

    ScrollView {
        anchors.fill: parent
        anchors.margins: 20
        visible: root.viewModel.hasOpenProject
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: parent.width
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Label {
                        text: qsTr("事前確定")
                        color: theme.textPrimary
                        font.pixelSize: theme.titleSize
                        font.weight: Font.Bold
                    }
                    Label {
                        text: qsTr("保護者等と調整済みの『生徒・講師・日付・コマ』を、時間割作成前に固定します。")
                        color: theme.textSecondary
                        font.pixelSize: theme.captionSize
                    }
                }
                StatusBadge {
                    status: "current"
                    symbol: "🔒"
                    label: qsTr("登録済み %1枠")
                           .arg((root.viewModel.preconfirmedAssignments || []).length)
                }
            }

            InlineMessage {
                Layout.fillWidth: true
                kind: "info"
                message: qsTr("登録時に空き時間・集団授業・講師資格・同時最大2名・1対1必須などのハード制約を検査します。登録した1枠はロックされ、自動配置や再最適化では動きません。")
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: entryContent.implicitHeight + 32
                radius: 10
                color: "#ffffff"
                border.color: "#cfd9e8"

                ColumnLayout {
                    id: entryContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 16
                    spacing: 10

                    SectionHeader {
                        Layout.fillWidth: true
                        title: qsTr("固定する1枠を選択")
                        description: qsTr("アンケート取込み後の受講希望から、まだ配置されていない1回を選びます。")
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 14
                        rowSpacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("生徒・科目・回数（必須）"); color: "#344054" }
                            ComboBox {
                                id: lessonBox
                                Layout.fillWidth: true
                                model: root.viewModel.preconfirmationCandidates || []
                                textRole: "label"
                                Accessible.name: qsTr("事前確定する受講希望")
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("講師（必須）"); color: "#344054" }
                            ComboBox {
                                id: teacherBox
                                Layout.fillWidth: true
                                model: root.activeTeachers()
                                textRole: "label"
                                Accessible.name: qsTr("事前確定する講師")
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("日付（必須）"); color: "#344054" }
                            ComboBox {
                                id: dateBox
                                Layout.fillWidth: true
                                model: root.availableDates()
                                textRole: "label"
                                Accessible.name: qsTr("事前確定する日付")
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("コマ（必須）"); color: "#344054" }
                            ComboBox {
                                id: slotBox
                                Layout.fillWidth: true
                                model: root.enabledSlots()
                                textRole: "label"
                                Accessible.name: qsTr("事前確定するコマ")
                            }
                        }
                    }

                    TextField {
                        id: noteField
                        Layout.fillWidth: true
                        placeholderText: qsTr("メモ（任意）：保護者と電話で調整済み など")
                        Accessible.name: qsTr("事前確定のメモ")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: (root.viewModel.preconfirmationCandidates || []).length > 0
                                  ? qsTr("登録すると自動保存され、1対2のうち1席を使用します。")
                                  : qsTr("固定できる未配置授業がありません。先に③回答取込みで受講希望を反映してください。")
                            color: "#667085"
                            wrapMode: Text.Wrap
                        }
                        AppButton {
                            text: qsTr("この1枠を固定")
                            kind: "primary"
                            enabled: lessonBox.currentIndex >= 0
                                     && teacherBox.currentIndex >= 0
                                     && dateBox.currentIndex >= 0
                                     && slotBox.currentIndex >= 0
                            onClicked: {
                                const lesson = root.selectedRow(lessonBox)
                                const teacher = root.selectedRow(teacherBox)
                                const selectedDate = root.selectedRow(dateBox)
                                const slot = root.selectedRow(slotBox)
                                if (lesson && teacher && selectedDate && slot
                                        && root.viewModel.createPreconfirmedAssignment(
                                            Number(lesson.lessonRequestId),
                                            Number(lesson.sessionIndex),
                                            String(selectedDate.date),
                                            Number(slot.id),
                                            Number(teacher.id),
                                            noteField.text)) {
                                    noteField.clear()
                                    lessonBox.currentIndex = 0
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: fixedContent.implicitHeight + 30
                radius: 10
                color: "#ffffff"
                border.color: "#dce2ea"

                ColumnLayout {
                    id: fixedContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 15
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("登録済みの事前確定枠")
                            color: "#344054"
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }
                        AppButton {
                            text: qsTr("時間割で確認・変更")
                            onClicked: root.openTimetableRequested()
                        }
                    }

                    Label {
                        visible: (root.viewModel.preconfirmedAssignments || []).length === 0
                        text: qsTr("まだ事前確定枠はありません。")
                        color: "#667085"
                    }

                    Repeater {
                        model: root.viewModel.preconfirmedAssignments || []
                        delegate: Rectangle {
                            id: fixedRow
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: fixedLabel.implicitHeight + 18
                            radius: 6
                            color: "#f7f9fc"
                            border.color: "#dce2ea"

                            Label {
                                id: fixedLabel
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: 9
                                text: String(fixedRow.modelData.detailText || "")
                                color: "#344054"
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }
        }
    }
}
