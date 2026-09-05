pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested

    property var selectedStudent: null
    property int editingStudentId: 0
    property int editingRequestId: 0
    property bool studentSaveAttempted: false
    property bool requestSaveAttempted: false
    property bool loadingStudentDraft: false
    property bool loadingRequestDraft: false
    property int sortIndex: 0
    property bool studentAdvancedVisible: false
    property int studentWizardStep: 0
    readonly property var displayedStudents: sortedStudents()
    readonly property var displayedRequests: requestsForSelectedStudent()

    UiTheme { id: theme }

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function asBoolean(value, fallback) {
        if (value === undefined || value === null)
            return fallback
        return Boolean(value)
    }

    function sortedStudents() {
        const rows = []
        const source = root.viewModel.students || []
        for (let i = 0; i < source.length; ++i)
            rows.push(source[i])
        const key = root.sortIndex === 1 ? "name" : root.sortIndex === 2 ? "grade" : "externalId"
        rows.sort(function (left, right) {
            const leftActive = root.asBoolean(root.rowValue(left, "active", true), true)
            const rightActive = root.asBoolean(root.rowValue(right, "active", true), true)
            if (leftActive !== rightActive)
                return leftActive ? -1 : 1
            return String(root.rowValue(left, key, "")).localeCompare(
                        String(root.rowValue(right, key, "")), "ja", {
                            numeric: true,
                            sensitivity: "base"
                        })
        })
        return rows
    }

    function requestsForSelectedStudent() {
        const rows = []
        if (root.editingStudentId <= 0)
            return rows
        const source = root.viewModel.lessonRequests || []
        for (let i = 0; i < source.length; ++i) {
            if (String(root.rowValue(source[i], "studentId", ""))
                    === String(root.editingStudentId))
                rows.push(source[i])
        }
        rows.sort(function (left, right) {
            return String(root.rowValue(left, "subjectName", "")).localeCompare(
                        String(root.rowValue(right, "subjectName", ""), "ja"))
        })
        return rows
    }

    function activeTeacherOptions(keepIds) {
        const options = [{
                             "id": "",
                             "name": qsTr("未設定")
                         }]
        const source = root.viewModel.teachers || []
        for (let i = 0; i < source.length; ++i) {
            const row = source[i]
            const id = root.rowValue(row, "id", "")
            const active = root.asBoolean(root.rowValue(row, "active", true), true)
            let keep = false
            for (let j = 0; j < keepIds.length; ++j) {
                if (String(keepIds[j]) === String(id))
                    keep = true
            }
            if (active || keep) {
                options.push({
                                 "id": id,
                                 "name": root.rowValue(row, "name", "")
                                         + (!active ? qsTr("（停止中・既存）") : "")
                             })
            }
        }
        return options
    }

    function activeSubjectOptions(keepId) {
        const options = []
        const source = root.viewModel.subjects || []
        for (let i = 0; i < source.length; ++i) {
            const row = source[i]
            const id = root.rowValue(row, "id", "")
            const active = root.asBoolean(root.rowValue(row, "active", true), true)
            if (active || String(id) === String(keepId)) {
                options.push({
                                 "id": id,
                                 "displayName": root.rowValue(row, "displayName", "")
                                                + (!active ? qsTr("（停止中・既存）") : "")
                             })
            }
        }
        return options
    }

    function optionIndex(options, id) {
        for (let i = 0; i < options.length; ++i) {
            if (String(options[i].id) === String(id === null ? "" : id))
                return i
        }
        return 0
    }

    function gradeIndex(value) {
        const options = studentGrade.model || []
        for (let i = 0; i < options.length; ++i) {
            if (String(options[i]) === String(value))
                return i
        }
        return 0
    }

    function openStudentWizard() {
        root.studentWizardStep = 0
        wizardFamilyName.text = ""
        wizardGivenName.text = ""
        wizardGrade.currentIndex = 0
        wizardMaxConsecutive.value = 2
        wizardAllowGap.checked = false
        wizardActive.checked = true
        wizardNote.text = ""
        studentWizard.open()
    }

    function saveStudentEditor() {
        root.studentSaveAttempted = true
        if (studentName.text.trim() === "" || studentGrade.currentIndex < 0)
            return false
        return root.viewModel.saveStudent(
                    root.editingStudentId,
                    studentExternalId.text.trim(),
                    studentName.text.trim(),
                    studentGrade.currentText,
                    maxConsecutive.value,
                    allowGap.checked,
                    studentNote.text,
                    studentActive.checked)
    }

    function savePendingChanges() {
        if (!root.viewModel.isDirty)
            return true
        return root.saveStudentEditor()
    }

    function loadStudent(row) {
        root.loadingStudentDraft = true
        root.selectedStudent = row
        root.editingStudentId = Number(root.rowValue(row, "id", 0))
        studentExternalId.text = root.rowValue(row, "externalId", "")
        studentName.text = root.rowValue(row, "name", "")
        studentGrade.currentIndex = root.gradeIndex(root.rowValue(row, "grade", ""))
        maxConsecutive.value = Number(root.rowValue(row, "maxConsecutive", 2))
        allowGap.checked = root.asBoolean(root.rowValue(row, "allowGap", false), false)
        studentNote.text = root.rowValue(row, "note", "")
        studentActive.checked = root.asBoolean(root.rowValue(row, "active", true), true)
        root.studentSaveAttempted = false
        clearRequest()
        root.loadingStudentDraft = false
    }

    function clearStudent() {
        root.loadingStudentDraft = true
        root.selectedStudent = null
        root.editingStudentId = 0
        studentExternalId.text = ""
        studentName.text = ""
        studentGrade.currentIndex = 0
        maxConsecutive.value = 2
        allowGap.checked = false
        studentNote.text = ""
        studentActive.checked = true
        root.studentSaveAttempted = false
        clearRequest()
        root.loadingStudentDraft = false
    }

    function clearRequest() {
        root.loadingRequestDraft = true
        root.editingRequestId = 0
        requestSubject.currentIndex = requestSubject.count > 0 ? 0 : -1
        requiredSessions.value = 1
        regularTeacher.currentIndex = 0
        regularPriority.value = 3
        preferredTeacher1.currentIndex = 0
        preferredTeacher2.currentIndex = 0
        preferredTeacher3.currentIndex = 0
        oneToOne.checked = false
        useMaxOverride.checked = false
        maxOverride.value = 2
        gapOverride.currentIndex = 0
        requestNote.text = ""
        root.requestSaveAttempted = false
        root.loadingRequestDraft = false
    }

    function loadRequest(row) {
        root.loadingRequestDraft = true
        root.editingRequestId = Number(root.rowValue(row, "id", 0))
        const subjectId = root.rowValue(row, "subjectId", "")
        const regularId = root.rowValue(row, "regularTeacherId", "")
        const preferred1 = root.rowValue(row, "preferredTeacher1Id", "")
        const preferred2 = root.rowValue(row, "preferredTeacher2Id", "")
        const preferred3 = root.rowValue(row, "preferredTeacher3Id", "")
        requestSubject.model = root.activeSubjectOptions(subjectId)
        requestSubject.currentIndex = root.optionIndex(requestSubject.model, subjectId)
        const teachers = root.activeTeacherOptions([regularId, preferred1, preferred2, preferred3])
        regularTeacher.model = teachers
        preferredTeacher1.model = teachers
        preferredTeacher2.model = teachers
        preferredTeacher3.model = teachers
        regularTeacher.currentIndex = root.optionIndex(teachers, regularId)
        preferredTeacher1.currentIndex = root.optionIndex(teachers, preferred1)
        preferredTeacher2.currentIndex = root.optionIndex(teachers, preferred2)
        preferredTeacher3.currentIndex = root.optionIndex(teachers, preferred3)
        requiredSessions.value = Number(root.rowValue(row, "requiredSessions", 1))
        regularPriority.value = Number(root.rowValue(row, "regularTeacherPriority", 3))
        oneToOne.checked = root.asBoolean(root.rowValue(row, "oneToOneRequired", false), false)
        const maxValue = root.rowValue(row, "maxConsecutiveOverride", "")
        useMaxOverride.checked = maxValue !== "" && maxValue !== null
        maxOverride.value = useMaxOverride.checked ? Number(maxValue) : 2
        const gapValue = root.rowValue(row, "allowGapOverride", "")
        gapOverride.currentIndex = gapValue === "" || gapValue === null
                                   ? 0
                                   : root.asBoolean(gapValue, false) ? 1 : 2
        requestNote.text = root.rowValue(row, "note", "")
        root.requestSaveAttempted = false
        root.loadingRequestDraft = false
    }

    function teacherValue(comboBox) {
        return comboBox.currentIndex >= 0 && comboBox.currentValue !== undefined
                ? comboBox.currentValue : ""
    }

    function hasDuplicatePreferences() {
        const values = [
            root.teacherValue(preferredTeacher1),
            root.teacherValue(preferredTeacher2),
            root.teacherValue(preferredTeacher3)
        ]
        for (let i = 0; i < values.length; ++i) {
            if (values[i] === "")
                continue
            for (let j = i + 1; j < values.length; ++j) {
                if (String(values[i]) === String(values[j]))
                    return true
            }
        }
        return false
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
                    text: qsTr("生徒の基本情報")
                    color: "#18212f"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                }

                Label {
                    text: qsTr("追加・変更した内容は、ホームの基本情報Excelにも保存されます")
                    color: "#667085"
                    font.pixelSize: 11
                }
            }

            AppButton {
                text: qsTr("再読込み")
                enabled: true
                onClicked: root.viewModel.refreshAll()
            }

            AppButton {
                visible: false
                text: qsTr("Excel一括追加・更新…")
                enabled: root.viewModel.hasOpenProject
                onClicked: rosterImportDialog.open()
            }

            AppButton {
                text: qsTr("＋ 生徒を追加")
                kind: "primary"
                enabled: true
                onClicked: root.openStudentWizard()
            }
        }

        InlineMessage {
            Layout.fillWidth: true
            visible: (root.viewModel.students || []).length === 0
            kind: "info"
            message: qsTr("生徒が未登録です。右上の「生徒を追加」から基本情報を登録できます。")
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: false
            radius: 12
            color: "#ffffff"
            border.color: "#dce2ea"

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 520)
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
                    text: qsTr("先にホームからプロジェクトを開いてください。編集内容は基本情報Excelと同期されます。")
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

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: true
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.preferredWidth: 340
                SplitView.minimumWidth: 285
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 9

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 9

                    TextField {
                        id: studentSearch

                        Layout.fillWidth: true
                        placeholderText: qsTr("ID・氏名を部分一致で検索")
                        Accessible.name: qsTr("生徒検索")
                        onTextEdited: studentFilterDelay.restart()
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        ComboBox {
                            id: gradeFilter

                            Layout.fillWidth: true
                            model: [
                                qsTr("すべての学年"),
                                "小1", "小2", "小3", "小4", "小5", "小6",
                                "中1", "中2", "中3",
                                "高1", "高2", "高3", qsTr("その他")
                            ]
                            Accessible.name: qsTr("学年フィルター")
                            onActivated: root.viewModel.setStudentFilter(
                                             studentSearch.text,
                                             currentIndex === 0 ? "" : currentText)
                        }

                        ComboBox {
                            id: sortControl

                            Layout.preferredWidth: 112
                            model: [qsTr("ID順"), qsTr("氏名順"), qsTr("学年順")]
                            Accessible.name: qsTr("生徒一覧の並べ替え")
                            onActivated: root.sortIndex = currentIndex
                        }
                    }

                    Label {
                        text: qsTr("%1件　（列見出し：ID／氏名／学年／状態）").arg(studentList.count)
                        color: "#667085"
                        font.pixelSize: 10
                    }

                    ListView {
                        id: studentList

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 5
                        model: root.displayedStudents
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: ItemDelegate {
                            id: studentDelegate

                            required property var modelData
                            width: Math.max(0, ListView.view.width - 12)
                            height: 58
                            highlighted: root.editingStudentId
                                         === Number(root.rowValue(modelData, "id", 0))
                            Accessible.name: qsTr("%1 %2 %3")
                                             .arg(root.rowValue(modelData, "externalId", ""))
                                             .arg(root.rowValue(modelData, "name", ""))
                                             .arg(root.rowValue(modelData, "active", true)
                                                  ? qsTr("有効") : qsTr("停止中"))
                            onClicked: root.loadStudent(modelData)

                            background: Rectangle {
                                radius: 6
                                color: !root.rowValue(studentDelegate.modelData, "active", true)
                                       ? "#e7e7e7"
                                       : studentDelegate.highlighted ? "#e8f0ff" : "transparent"
                                border.color: studentDelegate.highlighted ? "#bfd3f5" : "transparent"
                            }

                            contentItem: RowLayout {
                                spacing: 9

                                Rectangle {
                                    Layout.preferredWidth: 38
                                    Layout.preferredHeight: 38
                                    radius: 19
                                    color: studentDelegate.highlighted ? "#2767c5" : "#edf1f6"

                                    Label {
                                        anchors.centerIn: parent
                                        text: String(root.rowValue(studentDelegate.modelData, "name", "?")).slice(0, 1)
                                        color: studentDelegate.highlighted ? "#ffffff" : "#475467"
                                        font.weight: Font.Bold
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1

                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(studentDelegate.modelData, "name", qsTr("氏名未設定"))
                                        color: "#344054"
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("%1　%2")
                                              .arg(root.rowValue(
                                                       studentDelegate.modelData,
                                                       "externalId", qsTr("IDなし")))
                                              .arg(root.rowValue(
                                                       studentDelegate.modelData,
                                                       "grade", qsTr("学年なし")))
                                        color: "#667085"
                                        font.pixelSize: 10
                                        elide: Text.ElideRight
                                    }
                                }

                                Label {
                                    text: root.rowValue(studentDelegate.modelData, "active", true)
                                          ? qsTr("有効") : qsTr("停止中")
                                    color: root.rowValue(studentDelegate.modelData, "active", true)
                                           ? "#176b40" : "#7a8493"
                                    font.pixelSize: 10
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 560
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 9

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    TabBar {
                        id: detailTabs

                        Layout.fillWidth: true
                        visible: false
                        currentIndex: 0

                        TabButton {
                            text: qsTr("基本情報")
                        }
                        TabButton {
                            text: qsTr("受講希望")
                            enabled: root.editingStudentId > 0
                        }
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: detailTabs.currentIndex

                        ScrollView {
                            id: studentEditorScroll

                            clip: true
                            contentWidth: availableWidth
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                            ColumnLayout {
                                width: studentEditorScroll.availableWidth
                                spacing: 9

                                Label {
                                    text: root.editingStudentId > 0 ? qsTr("生徒を編集") : qsTr("新しい生徒")
                                    color: "#344054"
                                    font.pixelSize: 16
                                    font.weight: Font.DemiBold
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 12

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 3
                                        Label {
                                            text: qsTr("生徒ID（自動）")
                                            color: "#344054"
                                            font.pixelSize: 11
                                        }
                                        TextField {
                                            id: studentExternalId
                                            Layout.fillWidth: true
                                            readOnly: true
                                            placeholderText: qsTr("保存時にS-0001形式で自動採番")
                                            Accessible.name: qsTr("生徒ID")
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 3
                                        Label {
                                            text: qsTr("氏名（必須）")
                                            color: "#344054"
                                            font.pixelSize: 11
                                        }
                                        TextField {
                                            id: studentName
                                            Layout.fillWidth: true
                                            placeholderText: qsTr("例：夏目 花子")
                                            Accessible.name: qsTr("生徒氏名")
                                            onTextEdited: root.viewModel.markDirty()
                                        }
                                        Label {
                                            visible: root.studentSaveAttempted && studentName.text.trim() === ""
                                            text: qsTr("氏名を入力してください。")
                                            color: "#a23b3b"
                                            font.pixelSize: 10
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 12

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 3
                                        Label {
                                            text: qsTr("学年（必須）")
                                            color: "#344054"
                                            font.pixelSize: 11
                                        }
                                        ComboBox {
                                            id: studentGrade
                                            Layout.fillWidth: true
                                            editable: false
                                            model: [
                                                "小1", "小2", "小3", "小4", "小5", "小6",
                                                "中1", "中2", "中3", "高1", "高2", "高3"
                                            ]
                                            Accessible.name: qsTr("学年")
                                            onActivated: root.viewModel.markDirty()
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        visible: root.studentAdvancedVisible
                                        spacing: 3
                                        Label {
                                            text: qsTr("標準最大連続コマ数")
                                            color: "#344054"
                                            font.pixelSize: 11
                                        }
                                        SpinBox {
                                            id: maxConsecutive
                                            Layout.fillWidth: true
                                            from: 1
                                            to: 10
                                            value: 2
                                            editable: true
                                            Accessible.name: qsTr("標準最大連続コマ数")
                                            onValueModified: root.viewModel.markDirty()
                                        }
                                        Label {
                                            text: qsTr("通常は2。必要に応じて上書きできます。")
                                            color: "#7a8493"
                                            font.pixelSize: 9
                                        }
                                    }
                                }

                                AppButton {
                                    text: root.studentAdvancedVisible
                                          ? qsTr("詳細設定を閉じる")
                                          : qsTr("詳細設定を表示")
                                    onClicked: root.studentAdvancedVisible = !root.studentAdvancedVisible
                                }

                                CheckBox {
                                    id: allowGap
                                    visible: root.studentAdvancedVisible
                                    text: qsTr("同じ日の授業間に空きコマを許可する")
                                    Accessible.name: text
                                    onClicked: root.viewModel.markDirty()
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    visible: root.editingStudentId > 0
                                    spacing: 6

                                    Label {
                                        text: qsTr("通常授業")
                                        color: "#344054"
                                        font.pixelSize: 13
                                        font.weight: Font.DemiBold
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        visible: root.rowValue(root.selectedStudent,
                                                               "regularLessons", []).length === 0
                                        text: qsTr("通常授業の科目・担当講師は登録されていません。")
                                        color: "#7a8493"
                                        font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                    }

                                    Repeater {
                                        model: root.rowValue(root.selectedStudent,
                                                             "regularLessons", [])

                                        delegate: Rectangle {
                                            id: regularLessonCard
                                            required property var modelData
                                            Layout.fillWidth: true
                                            implicitHeight: regularLessonContent.implicitHeight + 16
                                            radius: 6
                                            color: "#f5f8fc"
                                            border.color: "#d9e1ec"

                                            RowLayout {
                                                id: regularLessonContent
                                                anchors.left: parent.left
                                                anchors.right: parent.right
                                                anchors.verticalCenter: parent.verticalCenter
                                                anchors.margins: 8
                                                spacing: 12

                                                Label {
                                                    Layout.fillWidth: true
                                                    text: root.rowValue(regularLessonCard.modelData,
                                                                        "subjectName", "")
                                                    color: "#344054"
                                                    font.pixelSize: 11
                                                    font.weight: Font.DemiBold
                                                    elide: Text.ElideRight
                                                }
                                                Label {
                                                    Layout.preferredWidth: 190
                                                    text: qsTr("担当：%1").arg(
                                                              root.rowValue(
                                                                  regularLessonCard.modelData,
                                                                  "teacherName", qsTr("未設定")))
                                                    color: "#475467"
                                                    font.pixelSize: 11
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                    }
                                }

                                CheckBox {
                                    id: studentActive
                                    text: qsTr("在籍中（外すと卒業・退会として末尾に表示）")
                                    checked: true
                                    Accessible.name: text
                                    onClicked: root.viewModel.markDirty()
                                }

                                Label {
                                    visible: root.studentAdvancedVisible
                                    text: qsTr("備考")
                                    color: "#344054"
                                    font.pixelSize: 11
                                }
                                TextArea {
                                    id: studentNote
                                    visible: root.studentAdvancedVisible
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 100
                                    placeholderText: qsTr("校内で共有する注意事項（任意）")
                                    wrapMode: TextEdit.Wrap
                                    Accessible.name: qsTr("生徒備考")
                                    onTextChanged: {
                                        if (activeFocus && !root.loadingStudentDraft)
                                            root.viewModel.markDirty()
                                    }
                                }

                                Label {
                                    visible: root.studentSaveAttempted && root.viewModel.errorMessage
                                    Layout.fillWidth: true
                                    text: root.viewModel.errorMessage
                                    color: "#a23b3b"
                                    font.pixelSize: 10
                                    wrapMode: Text.Wrap
                                }

                                RowLayout {
                                    Layout.fillWidth: true

                                    Button {
                                        visible: root.editingStudentId > 0
                                        text: qsTr("使用停止")
                                        enabled: studentActive.checked
                                        onClicked: deactivateStudentDialog.open()
                                    }

                                    Button {
                                        visible: root.editingStudentId > 0
                                        text: qsTr("削除…")
                                        onClicked: deleteStudentDialog.open()
                                    }

                                    Item {
                                        Layout.fillWidth: true
                                    }

                                    Button {
                                        text: qsTr("キャンセル")
                                        onClicked: {
                                            if (root.selectedStudent)
                                                root.loadStudent(root.selectedStudent)
                                            else
                                                root.clearStudent()
                                            root.viewModel.discardDraft()
                                        }
                                    }

                                    Button {
                                        text: qsTr("保存")
                                        highlighted: true
                                        onClicked: root.saveStudentEditor()
                                    }
                                }
                            }
                        }

                        SplitView {
                            orientation: Qt.Horizontal

                            Rectangle {
                                SplitView.preferredWidth: 250
                                SplitView.minimumWidth: 210
                                color: "#f8fafc"
                                border.color: "#e2e7ee"
                                radius: 7

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 9
                                    spacing: 7

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Label {
                                            Layout.fillWidth: true
                                            text: qsTr("登録済み受講希望")
                                            color: "#344054"
                                            font.pixelSize: 12
                                            font.weight: Font.DemiBold
                                        }
                                        Button {
                                            text: qsTr("＋ 追加")
                                            onClicked: root.clearRequest()
                                        }
                                    }

                                    Label {
                                        visible: requestList.count === 0
                                        Layout.fillWidth: true
                                        text: qsTr("受講希望はまだありません。")
                                        color: "#7a8493"
                                        font.pixelSize: 10
                                        wrapMode: Text.Wrap
                                    }

                                    ListView {
                                        id: requestList

                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        clip: true
                                        spacing: 4
                                        model: root.displayedRequests
                                        boundsBehavior: Flickable.StopAtBounds

                                        ScrollBar.vertical: ScrollBar {
                                            policy: ScrollBar.AsNeeded
                                        }

                                        delegate: ItemDelegate {
                                            id: requestDelegate

                                            required property var modelData
                                            width: ListView.view.width
                                            height: 54
                                            highlighted: root.editingRequestId
                                                         === Number(root.rowValue(modelData, "id", 0))
                                            onClicked: root.loadRequest(modelData)

                                            contentItem: ColumnLayout {
                                                spacing: 1
                                                Label {
                                                    Layout.fillWidth: true
                                                    text: root.rowValue(requestDelegate.modelData, "subjectName", qsTr("科目"))
                                                    color: "#344054"
                                                    font.pixelSize: 11
                                                    font.weight: Font.DemiBold
                                                    elide: Text.ElideRight
                                                }
                                                Label {
                                                    Layout.fillWidth: true
                                                    text: qsTr("%1回／担当優先度%2").arg(
                                                              root.rowValue(requestDelegate.modelData, "requiredSessions", 1))
                                                          .arg(root.rowValue(requestDelegate.modelData, "regularTeacherPriority", 3))
                                                    color: "#667085"
                                                    font.pixelSize: 9
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            ScrollView {
                                id: requestEditorScroll

                                SplitView.fillWidth: true
                                SplitView.minimumWidth: 360
                                clip: true
                                contentWidth: availableWidth
                                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                                ColumnLayout {
                                    width: requestEditorScroll.availableWidth
                                    spacing: 8

                                    Label {
                                        text: root.editingRequestId > 0
                                              ? qsTr("受講希望を編集")
                                              : qsTr("新しい受講希望")
                                        color: "#344054"
                                        font.pixelSize: 15
                                        font.weight: Font.DemiBold
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 10

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 3
                                            Label {
                                                text: qsTr("科目 *")
                                                color: "#344054"
                                                font.pixelSize: 10
                                            }
                                            ComboBox {
                                                id: requestSubject
                                                Layout.fillWidth: true
                                                model: root.activeSubjectOptions("")
                                                textRole: "displayName"
                                                valueRole: "id"
                                                Accessible.name: qsTr("受講科目")
                                                onActivated: root.viewModel.markDirty()
                                            }
                                            Label {
                                                visible: root.requestSaveAttempted && requestSubject.currentIndex < 0
                                                text: qsTr("科目を選択してください。")
                                                color: "#a23b3b"
                                                font.pixelSize: 9
                                            }
                                        }

                                        ColumnLayout {
                                            Layout.preferredWidth: 130
                                            spacing: 3
                                            Label {
                                                text: qsTr("必要授業回数 *")
                                                color: "#344054"
                                                font.pixelSize: 10
                                            }
                                            SpinBox {
                                                id: requiredSessions
                                                Layout.fillWidth: true
                                                from: 1
                                                to: 100
                                                value: 1
                                                editable: true
                                                Accessible.name: qsTr("必要授業回数")
                                                onValueModified: root.viewModel.markDirty()
                                            }
                                        }
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 10

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 3
                                            Label {
                                                text: qsTr("通常担当講師")
                                                color: "#344054"
                                                font.pixelSize: 10
                                            }
                                            ComboBox {
                                                id: regularTeacher
                                                Layout.fillWidth: true
                                                model: root.activeTeacherOptions([])
                                                textRole: "name"
                                                valueRole: "id"
                                                Accessible.name: qsTr("通常担当講師")
                                                onActivated: root.viewModel.markDirty()
                                            }
                                        }

                                        ColumnLayout {
                                            Layout.preferredWidth: 130
                                            spacing: 3
                                            Label {
                                                text: qsTr("担当優先度")
                                                color: "#344054"
                                                font.pixelSize: 10
                                            }
                                            SpinBox {
                                                id: regularPriority
                                                Layout.fillWidth: true
                                                from: 1
                                                to: 5
                                                value: 3
                                                editable: true
                                                Accessible.name: qsTr("通常担当講師優先度")
                                                onValueModified: root.viewModel.markDirty()
                                            }
                                        }
                                    }

                                    Label {
                                        visible: root.requestSaveAttempted && regularPriority.value === 5
                                                 && root.teacherValue(regularTeacher) === ""
                                        Layout.fillWidth: true
                                        text: qsTr("優先度5は通常担当講師の選択が必須です。")
                                        color: "#a23b3b"
                                        font.pixelSize: 9
                                        wrapMode: Text.Wrap
                                    }

                                    Label {
                                        text: qsTr("希望講師（同じ講師を重複して選ばないでください）")
                                        color: "#344054"
                                        font.pixelSize: 10
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        ComboBox {
                                            id: preferredTeacher1
                                            Layout.fillWidth: true
                                            model: root.activeTeacherOptions([])
                                            textRole: "name"
                                            valueRole: "id"
                                            Accessible.name: qsTr("第1希望講師")
                                            onActivated: root.viewModel.markDirty()
                                        }
                                        ComboBox {
                                            id: preferredTeacher2
                                            Layout.fillWidth: true
                                            model: root.activeTeacherOptions([])
                                            textRole: "name"
                                            valueRole: "id"
                                            Accessible.name: qsTr("第2希望講師")
                                            onActivated: root.viewModel.markDirty()
                                        }
                                        ComboBox {
                                            id: preferredTeacher3
                                            Layout.fillWidth: true
                                            model: root.activeTeacherOptions([])
                                            textRole: "name"
                                            valueRole: "id"
                                            Accessible.name: qsTr("第3希望講師")
                                            onActivated: root.viewModel.markDirty()
                                        }
                                    }

                                    Label {
                                        visible: root.hasDuplicatePreferences()
                                        Layout.fillWidth: true
                                        text: qsTr("警告：希望講師が重複しています。")
                                        color: "#8a5a00"
                                        font.pixelSize: 9
                                    }

                                    CheckBox {
                                        id: oneToOne
                                        text: qsTr("1対1指導を必須にする")
                                        onClicked: root.viewModel.markDirty()
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        CheckBox {
                                            id: useMaxOverride
                                            text: qsTr("最大連続コマ数を上書き")
                                            onClicked: root.viewModel.markDirty()
                                        }

                                        SpinBox {
                                            id: maxOverride
                                            enabled: useMaxOverride.checked
                                            from: 1
                                            to: 10
                                            value: 2
                                            editable: true
                                            Accessible.name: qsTr("最大連続コマ数上書き")
                                            onValueModified: root.viewModel.markDirty()
                                        }

                                        Label {
                                            text: qsTr("空きコマ上書き")
                                            color: "#344054"
                                            font.pixelSize: 10
                                        }

                                        ComboBox {
                                            id: gapOverride
                                            Layout.fillWidth: true
                                            model: [
                                                {"label": qsTr("生徒の標準設定"), "value": ""},
                                                {"label": qsTr("許可"), "value": true},
                                                {"label": qsTr("禁止"), "value": false}
                                            ]
                                            textRole: "label"
                                            valueRole: "value"
                                            Accessible.name: qsTr("空きコマ許可上書き")
                                            onActivated: root.viewModel.markDirty()
                                        }
                                    }

                                    Label {
                                        text: qsTr("備考")
                                        color: "#344054"
                                        font.pixelSize: 10
                                    }
                                    TextArea {
                                        id: requestNote
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 72
                                        wrapMode: TextEdit.Wrap
                                        Accessible.name: qsTr("受講希望備考")
                                        onTextChanged: {
                                            if (activeFocus && !root.loadingRequestDraft)
                                                root.viewModel.markDirty()
                                        }
                                    }

                                    Label {
                                        visible: root.requestSaveAttempted && root.viewModel.errorMessage
                                        Layout.fillWidth: true
                                        text: root.viewModel.errorMessage
                                        color: "#a23b3b"
                                        font.pixelSize: 9
                                        wrapMode: Text.Wrap
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true

                                        Button {
                                            visible: root.editingRequestId > 0
                                            text: qsTr("削除…")
                                            onClicked: deleteRequestDialog.open()
                                        }

                                        Item {
                                            Layout.fillWidth: true
                                        }

                                        Button {
                                            text: qsTr("キャンセル")
                                            onClicked: {
                                                root.clearRequest()
                                                root.viewModel.discardDraft()
                                            }
                                        }

                                        Button {
                                            text: qsTr("保存")
                                            highlighted: true
                                            onClicked: {
                                                root.requestSaveAttempted = true
                                                if (requestSubject.currentIndex < 0
                                                        || (regularPriority.value === 5
                                                            && root.teacherValue(regularTeacher) === ""))
                                                    return
                                                root.viewModel.saveLessonRequest(
                                                            root.editingRequestId,
                                                            root.editingStudentId,
                                                            requestSubject.currentValue,
                                                            requiredSessions.value,
                                                            root.teacherValue(regularTeacher),
                                                            regularPriority.value,
                                                            root.teacherValue(preferredTeacher1),
                                                            root.teacherValue(preferredTeacher2),
                                                            root.teacherValue(preferredTeacher3),
                                                            oneToOne.checked,
                                                            useMaxOverride.checked ? String(maxOverride.value) : "",
                                                            gapOverride.currentValue,
                                                            requestNote.text)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Timer {
        id: studentFilterDelay
        interval: 250
        repeat: false
        onTriggered: root.viewModel.setStudentFilter(
                         studentSearch.text,
                         gradeFilter.currentIndex === 0 ? "" : gradeFilter.currentText)
    }

    Dialogs.FileDialog {
        id: rosterImportDialog
        title: qsTr("初期名簿・マスターデータExcelを選択")
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: [qsTr("Excelブック (*.xlsx)")]
        onAccepted: {
            if (root.viewModel.previewMasterImport(selectedFile.toString()))
                rosterPreviewDialog.open()
        }
    }

    Dialogs.FileDialog {
        id: rosterTemplateDialog
        title: qsTr("初期名簿テンプレートを保存")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("Excelブック (*.xlsx)")]
        onAccepted: root.viewModel.exportMasterData(selectedFile.toString())
    }

    Dialog {
        id: rosterPreviewDialog
        anchors.centerIn: Overlay.overlay
        width: Math.min(620, root.width - 48)
        modal: true
        title: qsTr("Excel一括登録の確認")
        standardButtons: Dialog.NoButton

        ColumnLayout {
            width: parent.width
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: qsTr("既存のDBはまだ変更されていません。件数とエラーを確認してから反映してください。")
                color: theme.textSecondary
                wrapMode: Text.Wrap
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("追加 %1件／更新 %2件／エラー %3件／警告 %4件")
                      .arg(root.rowValue(root.viewModel.excelPreviewSummary, "newCount", 0))
                      .arg(root.rowValue(root.viewModel.excelPreviewSummary, "updateCount", 0))
                      .arg(root.rowValue(root.viewModel.excelPreviewSummary, "errorCount", 0))
                      .arg(root.rowValue(root.viewModel.excelPreviewSummary, "warningCount", 0))
                color: theme.textPrimary
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
            InlineMessage {
                Layout.fillWidth: true
                kind: (root.viewModel.excelIssues || []).length > 0 ? "warning" : "success"
                message: (root.viewModel.excelIssues || []).length > 0
                         ? qsTr("確認事項が%1件あります。エラーがある場合は反映できません。")
                           .arg((root.viewModel.excelIssues || []).length)
                         : qsTr("検証エラーはありません。")
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton {
                    text: qsTr("テンプレートを保存")
                    onClicked: rosterTemplateDialog.open()
                }
                AppButton {
                    text: qsTr("キャンセル")
                    onClicked: rosterPreviewDialog.close()
                }
                AppButton {
                    text: qsTr("検証済み内容を反映")
                    kind: "primary"
                    enabled: Number(root.rowValue(
                                        root.viewModel.excelPreviewSummary,
                                        "errorCount", 0)) === 0
                    onClicked: {
                        if (root.viewModel.applyMasterImport())
                            rosterPreviewDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: studentWizard
        anchors.centerIn: Overlay.overlay
        width: Math.min(650, root.width - 48)
        height: Math.min(560, root.height - 48)
        modal: true
        title: qsTr("生徒を追加　%1/3").arg(root.studentWizardStep + 1)
        closePolicy: Popup.CloseOnEscape

        contentItem: ColumnLayout {
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: [qsTr("基本情報"), qsTr("授業上の設定"), qsTr("確認")]
                    delegate: StatusBadge {
                        id: wizardStepBadge
                        required property int index
                        required property string modelData
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.preferredWidth: 1
                        status: index < root.studentWizardStep ? "complete"
                                : index === root.studentWizardStep ? "current" : "neutral"
                        symbol: index < root.studentWizardStep ? "✓" : String(index + 1)
                        label: modelData
                    }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.studentWizardStep

                GridLayout {
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 8
                    Label { text: qsTr("苗字（必須）") }
                    TextField {
                        id: wizardFamilyName
                        Layout.fillWidth: true
                        placeholderText: qsTr("例：夏目")
                        Accessible.name: qsTr("追加する生徒の苗字")
                    }
                    Label { text: qsTr("名前（必須）") }
                    TextField {
                        id: wizardGivenName
                        Layout.fillWidth: true
                        placeholderText: qsTr("例：花子")
                        Accessible.name: qsTr("追加する生徒の名前")
                    }
                    Label { text: qsTr("学年（必須）") }
                    ComboBox {
                        id: wizardGrade
                        Layout.fillWidth: true
                        model: [
                            "小1", "小2", "小3", "小4", "小5", "小6",
                            "中1", "中2", "中3", "高1", "高2", "高3"
                        ]
                    }
                }

                ColumnLayout {
                    spacing: 10
                    Label {
                        text: qsTr("通常は初期値のままで登録できます。")
                        color: theme.textSecondary
                    }
                    RowLayout {
                        Label { text: qsTr("標準最大連続コマ数") }
                        SpinBox {
                            id: wizardMaxConsecutive
                            from: 1
                            to: 10
                            value: 2
                        }
                    }
                    CheckBox {
                        id: wizardAllowGap
                        text: qsTr("同じ日の授業間に空きコマを許可する")
                        checked: false
                    }
                    CheckBox {
                        id: wizardActive
                        text: qsTr("有効（在籍中）")
                        checked: true
                    }
                    Label { text: qsTr("備考") }
                    TextArea {
                        id: wizardNote
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        wrapMode: TextEdit.Wrap
                        placeholderText: qsTr("体験生などのラベルや注意事項（任意）")
                    }
                }

                ColumnLayout {
                    spacing: 12
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("%1 %2　%3")
                              .arg(wizardFamilyName.text.trim())
                              .arg(wizardGivenName.text.trim())
                              .arg(wizardGrade.currentText)
                        color: theme.textPrimary
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("ID: 保存時に自動採番\n最大連続: %1コマ\n空きコマ: %2\n状態: %3")
                              .arg(wizardMaxConsecutive.value)
                              .arg(wizardAllowGap.checked ? qsTr("許可") : qsTr("不許可"))
                              .arg(wizardActive.checked ? qsTr("有効") : qsTr("停止"))
                        color: theme.textSecondary
                        wrapMode: Text.Wrap
                    }
                    InlineMessage {
                        Layout.fillWidth: true
                        kind: "info"
                        message: qsTr("保存後、受講希望タブで科目・回数・通常担当講師を追加できます。")
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            InlineMessage {
                Layout.fillWidth: true
                kind: "error"
                message: root.viewModel.errorMessage
            }

            RowLayout {
                Layout.fillWidth: true
                AppButton {
                    text: qsTr("キャンセル")
                    onClicked: studentWizard.close()
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    visible: root.studentWizardStep > 0
                    text: qsTr("戻る")
                    onClicked: root.studentWizardStep -= 1
                }
                AppButton {
                    text: root.studentWizardStep < 2 ? qsTr("次へ") : qsTr("登録")
                    kind: "primary"
                    enabled: root.studentWizardStep > 0
                             || (wizardFamilyName.text.trim().length > 0
                                 && wizardGivenName.text.trim().length > 0)
                    onClicked: {
                        if (root.studentWizardStep < 2) {
                            root.studentWizardStep += 1
                            return
                        }
                        const fullName = wizardFamilyName.text.trim()
                                         + " " + wizardGivenName.text.trim()
                        if (root.viewModel.saveStudent(
                                    0,
                                    "",
                                    fullName,
                                    wizardGrade.currentText,
                                    wizardMaxConsecutive.value,
                                    wizardAllowGap.checked,
                                    wizardNote.text,
                                    wizardActive.checked))
                            studentWizard.close()
                    }
                }
            }
        }
    }

    Dialogs.MessageDialog {
        id: deactivateStudentDialog

        title: qsTr("生徒を使用停止")
        text: qsTr("%1を使用停止にしますか？").arg(studentName.text || qsTr("選択中の生徒"))
        informativeText: qsTr("過去の参照を保つためデータは削除されません。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.deactivateStudent(root.editingStudentId)
        }
    }

    Dialogs.MessageDialog {
        id: deleteStudentDialog

        title: qsTr("生徒を削除")
        text: qsTr("%1を削除しますか？").arg(studentName.text || qsTr("選択中の生徒"))
        informativeText: qsTr("関連する受講希望も同時に削除されます。この操作は元に戻せません。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.deleteStudent(root.editingStudentId)
        }
    }

    Dialogs.MessageDialog {
        id: deleteRequestDialog

        title: qsTr("受講希望を削除")
        text: qsTr("選択中の受講希望を削除しますか？")
        informativeText: qsTr("この操作は元に戻せません。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.deleteLessonRequest(root.editingRequestId)
        }
    }
}
