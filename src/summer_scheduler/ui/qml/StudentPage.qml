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
    readonly property var displayedStudents: sortedStudents()
    readonly property var displayedRequests: requestsForSelectedStudent()

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

    function loadStudent(row) {
        root.loadingStudentDraft = true
        root.selectedStudent = row
        root.editingStudentId = Number(root.rowValue(row, "id", 0))
        studentExternalId.text = root.rowValue(row, "externalId", "")
        studentName.text = root.rowValue(row, "name", "")
        studentGrade.editText = root.rowValue(row, "grade", "")
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
        studentGrade.editText = ""
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
                    text: qsTr("生徒")
                    color: "#18212f"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                }

                Label {
                    text: qsTr("生徒情報と受講希望を登録・編集します")
                    color: "#667085"
                    font.pixelSize: 11
                }
            }

            Button {
                text: qsTr("再読込み")
                enabled: root.viewModel.hasOpenProject
                onClicked: root.viewModel.refreshAll()
            }

            Button {
                text: qsTr("＋ 生徒を追加")
                highlighted: true
                enabled: root.viewModel.hasOpenProject
                onClicked: {
                    root.clearStudent()
                    detailTabs.currentIndex = 0
                }
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
                    text: qsTr("生徒データは.jukuscheduleプロジェクトごとに保存されます。")
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
            visible: root.viewModel.hasOpenProject
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
                            width: ListView.view.width
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
                                            text: qsTr("生徒ID *")
                                            color: "#344054"
                                            font.pixelSize: 11
                                        }
                                        TextField {
                                            id: studentExternalId
                                            Layout.fillWidth: true
                                            placeholderText: qsTr("例：S001")
                                            Accessible.name: qsTr("生徒ID")
                                            onTextEdited: root.viewModel.markDirty()
                                        }
                                        Label {
                                            visible: root.studentSaveAttempted && studentExternalId.text.trim() === ""
                                            text: qsTr("生徒IDを入力してください。")
                                            color: "#a23b3b"
                                            font.pixelSize: 10
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 3
                                        Label {
                                            text: qsTr("氏名 *")
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
                                            text: qsTr("学年 *")
                                            color: "#344054"
                                            font.pixelSize: 11
                                        }
                                        ComboBox {
                                            id: studentGrade
                                            Layout.fillWidth: true
                                            editable: true
                                            model: [
                                                "小1", "小2", "小3", "小4", "小5", "小6",
                                                "中1", "中2", "中3", "高1", "高2", "高3"
                                            ]
                                            Accessible.name: qsTr("学年")
                                            onActivated: root.viewModel.markDirty()
                                            onEditTextChanged: {
                                                if (activeFocus && !root.loadingStudentDraft)
                                                    root.viewModel.markDirty()
                                            }
                                        }
                                        Label {
                                            visible: root.studentSaveAttempted
                                                     && studentGrade.editText.trim() === ""
                                            text: qsTr("学年を入力してください。")
                                            color: "#a23b3b"
                                            font.pixelSize: 10
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
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

                                CheckBox {
                                    id: allowGap
                                    text: qsTr("同じ日の授業間に空きコマを許可する")
                                    Accessible.name: text
                                    onClicked: root.viewModel.markDirty()
                                }

                                CheckBox {
                                    id: studentActive
                                    text: qsTr("在籍中（外すと卒業・退会として末尾に表示）")
                                    checked: true
                                    Accessible.name: text
                                    onClicked: root.viewModel.markDirty()
                                }

                                Label {
                                    text: qsTr("備考")
                                    color: "#344054"
                                    font.pixelSize: 11
                                }
                                TextArea {
                                    id: studentNote
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
                                        onClicked: {
                                            root.studentSaveAttempted = true
                                            if (studentExternalId.text.trim() === ""
                                                    || studentName.text.trim() === ""
                                                    || studentGrade.editText.trim() === "")
                                                return
                                            root.viewModel.saveStudent(
                                                        root.editingStudentId,
                                                        studentExternalId.text.trim(),
                                                        studentName.text.trim(),
                                                        studentGrade.editText.trim(),
                                                        maxConsecutive.value,
                                                        allowGap.checked,
                                                        studentNote.text,
                                                        studentActive.checked)
                                        }
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
