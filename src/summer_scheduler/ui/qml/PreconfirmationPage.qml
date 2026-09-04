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

    function selectedRow(box) {
        if (!box.model || box.currentIndex < 0 || box.currentIndex >= box.model.length)
            return null
        return box.model[box.currentIndex]
    }

    function uniqueRows(rows, keyName, labelName) {
        const result = []
        const seen = {}
        for (let i = 0; i < rows.length; ++i) {
            const key = String(root.rowValue(rows[i], keyName, ""))
            if (!key || seen[key])
                continue
            seen[key] = true
            result.push({"value": key, "label": String(root.rowValue(rows[i], labelName, key))})
        }
        return result
    }

    function individualGrades() {
        return root.uniqueRows(root.viewModel.preconfirmationCandidates || [], "grade", "grade")
    }

    function individualStudents() {
        const grade = root.selectedRow(individualGradeBox)
        if (!grade)
            return []
        const rows = root.viewModel.preconfirmationCandidates || []
        const filtered = []
        for (let i = 0; i < rows.length; ++i) {
            if (String(root.rowValue(rows[i], "grade", "")) === String(grade.value))
                filtered.push(rows[i])
        }
        return root.uniqueRows(filtered, "studentId", "studentName")
    }

    function individualSubjects() {
        const student = root.selectedRow(individualStudentBox)
        if (!student)
            return []
        const rows = root.viewModel.preconfirmationCandidates || []
        const result = []
        const seen = {}
        for (let i = 0; i < rows.length; ++i) {
            if (String(root.rowValue(rows[i], "studentId", "")) !== String(student.value))
                continue
            const requestId = String(root.rowValue(rows[i], "lessonRequestId", ""))
            if (!requestId || seen[requestId])
                continue
            seen[requestId] = true
            result.push({
                "value": requestId,
                "label": String(root.rowValue(rows[i], "subjectName", ""))
            })
        }
        return result
    }

    function selectedIndividualCandidate() {
        const student = root.selectedRow(individualStudentBox)
        const subject = root.selectedRow(individualSubjectBox)
        if (!student || !subject)
            return null
        const rows = root.viewModel.preconfirmationCandidates || []
        let selected = null
        for (let i = 0; i < rows.length; ++i) {
            if (String(root.rowValue(rows[i], "studentId", "")) === String(student.value)
                    && String(root.rowValue(rows[i], "lessonRequestId", "")) === String(subject.value)
                    && (!selected || Number(rows[i].sessionIndex) < Number(selected.sessionIndex)))
                selected = rows[i]
        }
        return selected
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

    function resetIndividualSelection() {
        individualGradeBox.currentIndex = individualGradeBox.count > 0 ? 0 : -1
        individualStudentBox.currentIndex = individualStudentBox.count > 0 ? 0 : -1
        individualSubjectBox.currentIndex = individualSubjectBox.count > 0 ? 0 : -1
    }

    function createFixedEntry() {
        const lesson = root.selectedIndividualCandidate()
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
            root.resetIndividualSelection()
        }
    }

    readonly property int registeredCount: (root.viewModel.preconfirmedAssignments || []).length

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
                        text: qsTr("あらかじめ調整された指導枠を固定します。")
                        color: theme.textSecondary
                        font.pixelSize: theme.captionSize
                    }
                }
                StatusBadge {
                    status: "current"
                    symbol: "🔒"
                    label: qsTr("登録済み %1枠").arg(root.registeredCount)
                }
            }

            InlineMessage {
                Layout.fillWidth: true
                kind: "info"
                message: qsTr("空きコマ・講師指導科目・その他条件を確認してロックします。ロックされた枠には自動配置しません。")
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
                        description: qsTr("複数回登録する場合は1枠ずつ繰り返してください。")
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        Layout.maximumWidth: 920
                        Layout.alignment: Qt.AlignLeft
                        columns: 2
                        columnSpacing: 14
                        rowSpacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("学年（必須）"); color: "#344054" }
                            ComboBox {
                                id: individualGradeBox
                                Layout.fillWidth: true
                                model: root.individualGrades()
                                textRole: "label"
                                valueRole: "value"
                                Accessible.name: qsTr("個別指導の学年")
                                onActivated: {
                                    individualStudentBox.currentIndex = individualStudentBox.count > 0 ? 0 : -1
                                    individualSubjectBox.currentIndex = individualSubjectBox.count > 0 ? 0 : -1
                                }
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("生徒（必須）"); color: "#344054" }
                            ComboBox {
                                id: individualStudentBox
                                Layout.fillWidth: true
                                model: root.individualStudents()
                                textRole: "label"
                                valueRole: "value"
                                Accessible.name: qsTr("個別指導の生徒")
                                onActivated: individualSubjectBox.currentIndex = individualSubjectBox.count > 0 ? 0 : -1
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("受講予定科目（必須）"); color: "#344054" }
                            ComboBox {
                                id: individualSubjectBox
                                Layout.fillWidth: true
                                model: root.individualSubjects()
                                textRole: "label"
                                valueRole: "value"
                                Accessible.name: qsTr("個別指導の受講予定科目")
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
                                Accessible.name: qsTr("個別指導の講師")
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
                                Accessible.name: qsTr("個別指導の日付")
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
                                Accessible.name: qsTr("個別指導のコマ")
                            }
                        }
                    }

                    TextField {
                        id: noteField
                        Layout.fillWidth: true
                        Layout.maximumWidth: 920
                        Layout.alignment: Qt.AlignLeft
                        placeholderText: qsTr("メモ（任意）：保護者と電話で調整済み など")
                        Accessible.name: qsTr("事前確定のメモ")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: (root.viewModel.preconfirmationCandidates || []).length > 0
                                  ? qsTr("未配置のうち、選んだ生徒・科目の次の1回を固定します。")
                                  : qsTr("固定できる未配置授業がありません。先に③回答取込みで受講希望を反映してください。")
                            color: "#667085"
                            wrapMode: Text.Wrap
                        }
                        AppButton {
                            text: qsTr("この個別枠を固定")
                            kind: "primary"
                            enabled: root.selectedIndividualCandidate() !== null
                                     && teacherBox.currentIndex >= 0
                                     && dateBox.currentIndex >= 0
                                     && slotBox.currentIndex >= 0
                            onClicked: root.createFixedEntry()
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
                        visible: root.registeredCount === 0
                        text: qsTr("まだ事前確定枠はありません。")
                        color: "#667085"
                    }

                    Repeater {
                        model: root.viewModel.preconfirmedAssignments || []
                        delegate: Rectangle {
                            id: fixedIndividualRow
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: fixedIndividualLabel.implicitHeight + 18
                            radius: 6
                            color: "#f7f9fc"
                            border.color: "#dce2ea"
                            Label {
                                id: fixedIndividualLabel
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: 9
                                text: qsTr("個別指導｜%1").arg(String(fixedIndividualRow.modelData.detailText || ""))
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
