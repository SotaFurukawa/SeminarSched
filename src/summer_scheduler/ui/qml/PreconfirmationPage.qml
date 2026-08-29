pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    required property var groupViewModel
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

    function groupGrades() {
        return ["小1", "小2", "小3", "小4", "小5", "小6",
                "中1", "中2", "中3", "高1", "高2", "高3"]
    }

    function groupSubjectsForGrade(grade) {
        const prefix = String(grade).startsWith("小") ? "小学校・"
                     : String(grade).startsWith("中") ? "中学校・" : "高校・"
        const result = []
        const rows = root.groupViewModel.groupSubjects || []
        for (let i = 0; i < rows.length; ++i) {
            if (String(root.rowValue(rows[i], "label", "")).startsWith(prefix))
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
        if (root.individualMode) {
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
            return
        }

        const groupSubject = root.selectedRow(groupSubjectBox)
        const groupTeacher = root.selectedRow(groupTeacherBox)
        const groupDate = root.selectedRow(groupDateBox)
        const groupSlot = root.selectedRow(groupSlotBox)
        if (!groupSubject || !groupTeacher || !groupDate || !groupSlot)
            return
        const courseName = String(groupGradeBox.currentText) + " "
                + String(root.rowValue(groupSubject, "label", "集団授業"))
        if (root.groupViewModel.createCalendarGroupLesson(
                    String(groupGradeBox.currentText),
                    String(root.rowValue(groupSubject, "code", "")),
                    String(root.rowValue(groupDate, "value", "")),
                    String(root.rowValue(groupSlot, "start", "")),
                    String(root.rowValue(groupSlot, "end", "")),
                    courseName,
                    String(root.rowValue(groupTeacher, "externalId", "")),
                    "",
                    noteField.text)) {
            noteField.clear()
            root.viewModel.refreshSchedule()
        }
    }

    readonly property bool individualMode: lessonTypeBox.currentValue === "individual"
    readonly property int registeredCount: (root.viewModel.preconfirmedAssignments || []).length
                                           + (root.groupViewModel.groupLessons || []).length

    Component.onCompleted: {
        root.viewModel.refreshSchedule()
        root.groupViewModel.refreshPhase3()
    }

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
                        text: qsTr("調整済みの個別指導、または個別指導を入れない集団授業枠を先に固定します。")
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
                message: qsTr("個別指導は空き時間・講師資格・同時最大2名・1対1必須などを検査してロックします。集団授業は担当講師の同じ日時を占有し、自動配置で個別指導を重ねません。")
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
                        description: root.individualMode
                                     ? qsTr("学年、生徒、受講予定科目、講師、日時の順に選びます。複数回は1枠ずつ繰り返して登録します。")
                                     : qsTr("集団授業の学年・科目・担当講師・日時を登録し、その枠を個別指導から除外します。")
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("授業種別（必須）"); color: "#344054" }
                        ComboBox {
                            id: lessonTypeBox
                            Layout.fillWidth: true
                            model: [
                                {"label": qsTr("個別指導"), "value": "individual"},
                                {"label": qsTr("集団授業"), "value": "group"}
                            ]
                            textRole: "label"
                            valueRole: "value"
                            Accessible.name: qsTr("事前確定する授業種別")
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        visible: root.individualMode
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

                    GridLayout {
                        Layout.fillWidth: true
                        visible: !root.individualMode
                        columns: 2
                        columnSpacing: 14
                        rowSpacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("学年（必須）"); color: "#344054" }
                            ComboBox {
                                id: groupGradeBox
                                Layout.fillWidth: true
                                model: root.groupGrades()
                                Accessible.name: qsTr("集団授業の学年")
                                onActivated: groupSubjectBox.currentIndex = groupSubjectBox.count > 0 ? 0 : -1
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("科目（必須）"); color: "#344054" }
                            ComboBox {
                                id: groupSubjectBox
                                Layout.fillWidth: true
                                model: root.groupSubjectsForGrade(groupGradeBox.currentText)
                                textRole: "label"
                                valueRole: "code"
                                Accessible.name: qsTr("集団授業の科目")
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("講師（必須）"); color: "#344054" }
                            ComboBox {
                                id: groupTeacherBox
                                Layout.fillWidth: true
                                model: root.groupViewModel.groupTeachers || []
                                textRole: "label"
                                valueRole: "externalId"
                                Accessible.name: qsTr("集団授業の講師")
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("日付（必須）"); color: "#344054" }
                            ComboBox {
                                id: groupDateBox
                                Layout.fillWidth: true
                                model: root.groupViewModel.groupDates || []
                                textRole: "label"
                                valueRole: "value"
                                Accessible.name: qsTr("集団授業の日付")
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("コマ（必須）"); color: "#344054" }
                            ComboBox {
                                id: groupSlotBox
                                Layout.fillWidth: true
                                model: root.groupViewModel.groupSlots || []
                                textRole: "label"
                                valueRole: "code"
                                Accessible.name: qsTr("集団授業のコマ")
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    TextField {
                        id: noteField
                        Layout.fillWidth: true
                        placeholderText: root.individualMode
                                         ? qsTr("メモ（任意）：保護者と電話で調整済み など")
                                         : qsTr("メモ（任意）：講座名・教室など")
                        Accessible.name: qsTr("事前確定のメモ")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: root.individualMode
                                  ? ((root.viewModel.preconfirmationCandidates || []).length > 0
                                     ? qsTr("未配置のうち、選んだ生徒・科目の次の1回を固定します。")
                                     : qsTr("固定できる未配置授業がありません。先に③回答取込みで受講希望を反映してください。"))
                                  : qsTr("登録した集団授業は時間割の占有枠として保存されます。")
                            color: "#667085"
                            wrapMode: Text.Wrap
                        }
                        AppButton {
                            text: root.individualMode ? qsTr("この個別枠を固定") : qsTr("この集団授業を固定")
                            kind: "primary"
                            enabled: root.individualMode
                                     ? root.selectedIndividualCandidate() !== null
                                       && teacherBox.currentIndex >= 0
                                       && dateBox.currentIndex >= 0
                                       && slotBox.currentIndex >= 0
                                     : groupGradeBox.currentIndex >= 0
                                       && groupSubjectBox.currentIndex >= 0
                                       && groupTeacherBox.currentIndex >= 0
                                       && groupDateBox.currentIndex >= 0
                                       && groupSlotBox.currentIndex >= 0
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
                        text: qsTr("まだ個別指導・集団授業の事前確定枠はありません。")
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

                    Repeater {
                        model: root.groupViewModel.groupLessons || []
                        delegate: Rectangle {
                            id: fixedGroupRow
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: fixedGroupLabel.implicitHeight + 18
                            radius: 6
                            color: "#eef6ff"
                            border.color: "#b9d7f5"
                            Label {
                                id: fixedGroupLabel
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: 9
                                text: qsTr("集団授業｜%1 %2／%3 %4～%5／講師：%6")
                                      .arg(String(root.rowValue(fixedGroupRow.modelData, "grade", "")))
                                      .arg(String(root.rowValue(fixedGroupRow.modelData, "subjectName", "")))
                                      .arg(String(root.rowValue(fixedGroupRow.modelData, "date", "")))
                                      .arg(String(root.rowValue(fixedGroupRow.modelData, "startTime", "")))
                                      .arg(String(root.rowValue(fixedGroupRow.modelData, "endTime", "")))
                                      .arg(String(root.rowValue(fixedGroupRow.modelData, "teacherName", "―")))
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
