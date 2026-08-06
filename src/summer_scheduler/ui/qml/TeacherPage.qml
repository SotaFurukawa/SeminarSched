pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested

    property var selectedTeacher: null
    property int editingTeacherId: 0
    property bool teacherSaveAttempted: false
    property bool loadingTeacherDraft: false
    property int sortIndex: 0
    property var qualificationDraft: ({})
    property int qualificationRevision: 0
    property bool qualificationsDirty: false
    readonly property var displayedTeachers: sortedTeachers()
    readonly property var qualificationRows: buildQualificationRows()

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

    function sortedTeachers() {
        const rows = []
        const source = root.viewModel.teachers || []
        for (let i = 0; i < source.length; ++i)
            rows.push(source[i])
        const key = root.sortIndex === 1 ? "name" : "externalId"
        rows.sort(function (left, right) {
            return String(root.rowValue(left, key, "")).localeCompare(
                        String(root.rowValue(right, key, "")), "ja", {
                            numeric: true,
                            sensitivity: "base"
                        })
        })
        return rows
    }

    function activeTeacherOptions() {
        const options = [{
                             "id": "",
                             "name": qsTr("コピー元を選択")
                         }]
        const source = root.viewModel.teachers || []
        for (let i = 0; i < source.length; ++i) {
            const row = source[i]
            const id = root.rowValue(row, "id", "")
            if (Number(id) !== root.editingTeacherId
                    && root.asBoolean(root.rowValue(row, "active", true), true)) {
                options.push({
                                 "id": id,
                                 "name": root.rowValue(row, "name", "")
                             })
            }
        }
        return options
    }

    function normalizedLevel(row) {
        const raw = String(root.rowValue(row, "schoolLevel", "")).toLowerCase()
        if (raw.indexOf("element") >= 0 || raw.indexOf("primary") >= 0
                || raw.indexOf("小") >= 0)
            return "elementary"
        if (raw.indexOf("middle") >= 0 || raw.indexOf("junior") >= 0
                || raw.indexOf("中") >= 0)
            return "middle"
        if (raw.indexOf("high") >= 0 || raw.indexOf("高校") >= 0
                || raw.indexOf("高") === 0)
            return "high"
        return raw
    }

    function levelLabel(level) {
        if (level === "elementary")
            return qsTr("小学校")
        if (level === "middle")
            return qsTr("中学校")
        if (level === "high")
            return qsTr("高校")
        return qsTr("その他")
    }

    function loadTeacher(row) {
        root.loadingTeacherDraft = true
        root.selectedTeacher = row
        root.editingTeacherId = Number(root.rowValue(row, "id", 0))
        teacherExternalId.text = root.rowValue(row, "externalId", "")
        teacherName.text = root.rowValue(row, "name", "")
        teacherAllowGap.checked = root.asBoolean(root.rowValue(row, "allowGap", false), false)
        teacherNote.text = root.rowValue(row, "note", "")
        teacherActive.checked = root.asBoolean(root.rowValue(row, "active", true), true)
        root.teacherSaveAttempted = false
        root.viewModel.selectTeacher(root.editingTeacherId)
        qualificationReloadDelay.restart()
        root.loadingTeacherDraft = false
    }

    function clearTeacher() {
        root.loadingTeacherDraft = true
        root.selectedTeacher = null
        root.editingTeacherId = 0
        teacherExternalId.text = ""
        teacherName.text = ""
        teacherAllowGap.checked = false
        teacherNote.text = ""
        teacherActive.checked = true
        root.teacherSaveAttempted = false
        root.qualificationDraft = ({})
        root.qualificationRevision += 1
        root.qualificationsDirty = false
        teacherTabs.currentIndex = 0
        root.loadingTeacherDraft = false
    }

    function reloadQualifications() {
        const next = ({})
        const source = root.viewModel.currentTeacherQualifications || []
        for (let i = 0; i < source.length; ++i) {
            const row = source[i]
            next[String(root.rowValue(row, "subjectId", ""))]
                    = root.asBoolean(root.rowValue(row, "canTeach", false), false)
        }
        root.qualificationDraft = next
        root.qualificationRevision += 1
        root.qualificationsDirty = false
    }

    function buildQualificationRows() {
        // Reading the revision makes in-place draft updates observable.
        const revision = root.qualificationRevision
        const rows = []
        const source = root.viewModel.subjects || []
        const selectedLevel = qualificationLevel.currentIndex === 0
                              ? "" : qualificationLevel.currentValue
        for (let i = 0; i < source.length; ++i) {
            const subject = source[i]
            const level = root.normalizedLevel(subject)
            if (selectedLevel !== "" && level !== selectedLevel)
                continue
            if ((level === "elementary" && !elementaryExpanded.checked)
                    || (level === "middle" && !middleExpanded.checked)
                    || (level === "high" && !highExpanded.checked))
                continue
            const id = root.rowValue(subject, "id", "")
            rows.push({
                          "id": id,
                          "code": root.rowValue(subject, "code", ""),
                          "displayName": root.rowValue(subject, "displayName", ""),
                          "schoolLevel": level,
                          "levelLabel": root.levelLabel(level),
                          "active": root.asBoolean(root.rowValue(subject, "active", true), true),
                          "canTeach": Boolean(root.qualificationDraft[String(id)]),
                          "revision": revision
                      })
        }
        rows.sort(function (left, right) {
            if (left.schoolLevel !== right.schoolLevel)
                return left.schoolLevel.localeCompare(right.schoolLevel)
            return left.displayName.localeCompare(right.displayName, "ja")
        })
        return rows
    }

    function setQualificationDraft(subjectId, checked) {
        const next = ({})
        const keys = Object.keys(root.qualificationDraft)
        for (let i = 0; i < keys.length; ++i)
            next[keys[i]] = root.qualificationDraft[keys[i]]
        next[String(subjectId)] = checked
        root.qualificationDraft = next
        root.qualificationRevision += 1
        root.qualificationsDirty = true
        root.viewModel.markDirty()
    }

    function setVisibleQualifications(checked) {
        const rows = root.qualificationRows
        for (let i = 0; i < rows.length; ++i)
            root.setQualificationDraft(rows[i].id, checked)
    }

    function saveQualifications() {
        if (root.viewModel.saveQualifications(root.qualificationDraft))
            root.qualificationsDirty = false
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
                    text: qsTr("講師")
                    color: "#18212f"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                }

                Label {
                    text: qsTr("講師情報と指導可能科目を登録・編集します")
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
                text: qsTr("＋ 講師を追加")
                highlighted: true
                enabled: root.viewModel.hasOpenProject
                onClicked: root.clearTeacher()
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
                    text: qsTr("講師データと資格は.jukuscheduleプロジェクトごとに保存されます。")
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
                SplitView.preferredWidth: 330
                SplitView.minimumWidth: 280
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 9

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 9

                    TextField {
                        id: teacherSearch

                        Layout.fillWidth: true
                        placeholderText: qsTr("ID・氏名を部分一致で検索")
                        Accessible.name: qsTr("講師検索")
                        onTextEdited: teacherFilterDelay.restart()
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("%1件　ID／氏名／状態").arg(teacherList.count)
                            color: "#667085"
                            font.pixelSize: 10
                        }

                        ComboBox {
                            Layout.preferredWidth: 110
                            model: [qsTr("ID順"), qsTr("氏名順")]
                            Accessible.name: qsTr("講師一覧の並べ替え")
                            onActivated: root.sortIndex = currentIndex
                        }
                    }

                    ListView {
                        id: teacherList

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 5
                        model: root.displayedTeachers
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: ItemDelegate {
                            id: teacherDelegate

                            required property var modelData
                            width: ListView.view.width
                            height: 58
                            highlighted: root.editingTeacherId
                                         === Number(root.rowValue(modelData, "id", 0))
                            Accessible.name: qsTr("%1 %2 %3")
                                             .arg(root.rowValue(modelData, "externalId", ""))
                                             .arg(root.rowValue(modelData, "name", ""))
                                             .arg(root.rowValue(modelData, "active", true)
                                                  ? qsTr("有効") : qsTr("停止中"))
                            onClicked: root.loadTeacher(modelData)

                            background: Rectangle {
                                radius: 6
                                color: !root.rowValue(teacherDelegate.modelData, "active", true)
                                       ? "#e7e7e7"
                                       : teacherDelegate.highlighted ? "#e8f0ff" : "transparent"
                                border.color: teacherDelegate.highlighted ? "#bfd3f5" : "transparent"
                            }

                            contentItem: RowLayout {
                                spacing: 9

                                Rectangle {
                                    Layout.preferredWidth: 38
                                    Layout.preferredHeight: 38
                                    radius: 9
                                    color: teacherDelegate.highlighted ? "#2767c5" : "#edf1f6"

                                    Label {
                                        anchors.centerIn: parent
                                        text: String(root.rowValue(teacherDelegate.modelData, "name", "?")).slice(0, 1)
                                        color: teacherDelegate.highlighted ? "#ffffff" : "#475467"
                                        font.weight: Font.Bold
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1

                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(teacherDelegate.modelData, "name", qsTr("氏名未設定"))
                                        color: "#344054"
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(teacherDelegate.modelData, "externalId", qsTr("IDなし"))
                                        color: "#667085"
                                        font.pixelSize: 10
                                        elide: Text.ElideRight
                                    }
                                }

                                Label {
                                    text: root.rowValue(teacherDelegate.modelData, "active", true)
                                          ? qsTr("有効") : qsTr("停止中")
                                    color: root.rowValue(teacherDelegate.modelData, "active", true)
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
                SplitView.minimumWidth: 580
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 9

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8

                    TabBar {
                        id: teacherTabs

                        Layout.fillWidth: true

                        TabButton {
                            text: qsTr("基本情報")
                        }
                        TabButton {
                            text: root.qualificationsDirty
                                  ? qsTr("指導可能科目 ● 未保存")
                                  : qsTr("指導可能科目")
                            enabled: root.editingTeacherId > 0
                        }
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: teacherTabs.currentIndex

                        ScrollView {
                            id: teacherEditorScroll

                            clip: true
                            contentWidth: availableWidth
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                            ColumnLayout {
                                width: teacherEditorScroll.availableWidth
                                spacing: 10

                                Label {
                                    text: root.editingTeacherId > 0 ? qsTr("講師を編集") : qsTr("新しい講師")
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
                                            text: qsTr("講師ID *")
                                            color: "#344054"
                                            font.pixelSize: 11
                                        }
                                        TextField {
                                            id: teacherExternalId
                                            Layout.fillWidth: true
                                            placeholderText: qsTr("例：T001")
                                            Accessible.name: qsTr("講師ID")
                                            onTextEdited: root.viewModel.markDirty()
                                        }
                                        Label {
                                            visible: root.teacherSaveAttempted
                                                     && teacherExternalId.text.trim() === ""
                                            text: qsTr("講師IDを入力してください。")
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
                                            id: teacherName
                                            Layout.fillWidth: true
                                            placeholderText: qsTr("例：講師 太郎")
                                            Accessible.name: qsTr("講師氏名")
                                            onTextEdited: root.viewModel.markDirty()
                                        }
                                        Label {
                                            visible: root.teacherSaveAttempted && teacherName.text.trim() === ""
                                            text: qsTr("氏名を入力してください。")
                                            color: "#a23b3b"
                                            font.pixelSize: 10
                                        }
                                    }
                                }

                                CheckBox {
                                    id: teacherAllowGap
                                    text: qsTr("同じ日の担当間に空きコマを許可する")
                                    Accessible.name: text
                                    onClicked: root.viewModel.markDirty()
                                }

                                CheckBox {
                                    id: teacherActive
                                    text: qsTr("在籍中（外すと退職・休止として末尾に表示）")
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
                                    id: teacherNote
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 120
                                    placeholderText: qsTr("校内で共有する注意事項（任意）")
                                    wrapMode: TextEdit.Wrap
                                    Accessible.name: qsTr("講師備考")
                                    onTextChanged: {
                                        if (activeFocus && !root.loadingTeacherDraft)
                                            root.viewModel.markDirty()
                                    }
                                }

                                Label {
                                    visible: root.teacherSaveAttempted && root.viewModel.errorMessage
                                    Layout.fillWidth: true
                                    text: root.viewModel.errorMessage
                                    color: "#a23b3b"
                                    font.pixelSize: 10
                                    wrapMode: Text.Wrap
                                }

                                RowLayout {
                                    Layout.fillWidth: true

                                    Button {
                                        visible: root.editingTeacherId > 0
                                        text: qsTr("使用停止")
                                        enabled: teacherActive.checked
                                        onClicked: deactivateTeacherDialog.open()
                                    }

                                    Button {
                                        visible: root.editingTeacherId > 0
                                        text: qsTr("削除…")
                                        onClicked: deleteTeacherDialog.open()
                                    }

                                    Item {
                                        Layout.fillWidth: true
                                    }

                                    Button {
                                        text: qsTr("キャンセル")
                                        onClicked: {
                                            if (root.selectedTeacher)
                                                root.loadTeacher(root.selectedTeacher)
                                            else
                                                root.clearTeacher()
                                            root.viewModel.discardDraft()
                                            if (root.qualificationsDirty)
                                                root.viewModel.markDirty()
                                        }
                                    }

                                    Button {
                                        text: qsTr("保存")
                                        highlighted: true
                                        onClicked: {
                                            root.teacherSaveAttempted = true
                                            if (teacherExternalId.text.trim() === ""
                                                    || teacherName.text.trim() === "")
                                                return
                                            root.viewModel.saveTeacher(
                                                        root.editingTeacherId,
                                                        teacherExternalId.text.trim(),
                                                        teacherName.text.trim(),
                                                        teacherAllowGap.checked,
                                                        teacherNote.text,
                                                        teacherActive.checked)
                                        }
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            spacing: 9

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: matrixHelp.implicitHeight + 22
                                radius: 7
                                color: root.qualificationsDirty ? "#fff8e8" : "#f5f8fc"
                                border.color: root.qualificationsDirty ? "#e4c16f" : "#d9e1ec"

                                Label {
                                    id: matrixHelp
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    text: root.qualificationsDirty
                                          ? qsTr("● 未保存の変更があります。「変更を保存」を押してください。")
                                          : qsTr("科目ごとのチェックは独立しています。高校数学一般から数学IIIを推定しません。")
                                    color: root.qualificationsDirty ? "#7a5710" : "#52647d"
                                    font.pixelSize: 10
                                    wrapMode: Text.Wrap
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                ComboBox {
                                    id: qualificationLevel

                                    Layout.preferredWidth: 140
                                    model: [
                                        {"label": qsTr("全学校段階"), "value": ""},
                                        {"label": qsTr("小学校"), "value": "elementary"},
                                        {"label": qsTr("中学校"), "value": "middle"},
                                        {"label": qsTr("高校"), "value": "high"}
                                    ]
                                    textRole: "label"
                                    valueRole: "value"
                                    Accessible.name: qsTr("学校段階フィルター")
                                    onActivated: root.qualificationRevision += 1
                                }

                                Button {
                                    text: qsTr("表示中を全選択")
                                    onClicked: root.setVisibleQualifications(true)
                                }

                                Button {
                                    text: qsTr("表示中を全解除")
                                    onClicked: root.setVisibleQualifications(false)
                                }

                                Item {
                                    Layout.fillWidth: true
                                }

                                ComboBox {
                                    id: copySource

                                    Layout.preferredWidth: 190
                                    model: root.activeTeacherOptions()
                                    textRole: "name"
                                    valueRole: "id"
                                    Accessible.name: qsTr("資格コピー元講師")
                                }

                                Button {
                                    text: qsTr("資格をコピー")
                                    enabled: copySource.currentIndex > 0
                                    onClicked: {
                                        root.viewModel.copyQualifications(copySource.currentValue)
                                        qualificationReloadDelay.restart()
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Label {
                                    text: qsTr("学校段階を折りたたむ:")
                                    color: "#667085"
                                    font.pixelSize: 10
                                }

                                ToolButton {
                                    id: elementaryExpanded

                                    checkable: true
                                    checked: true
                                    text: checked ? qsTr("▼ 小学校") : qsTr("▶ 小学校")
                                    Accessible.name: text
                                    onToggled: root.qualificationRevision += 1
                                }

                                ToolButton {
                                    id: middleExpanded

                                    checkable: true
                                    checked: true
                                    text: checked ? qsTr("▼ 中学校") : qsTr("▶ 中学校")
                                    Accessible.name: text
                                    onToggled: root.qualificationRevision += 1
                                }

                                ToolButton {
                                    id: highExpanded

                                    checkable: true
                                    checked: true
                                    text: checked ? qsTr("▼ 高校") : qsTr("▶ 高校")
                                    Accessible.name: text
                                    onToggled: root.qualificationRevision += 1
                                }

                                Item {
                                    Layout.fillWidth: true
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 30
                                color: "#eef2f6"
                                border.color: "#dce2ea"

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12

                                    Label {
                                        Layout.preferredWidth: 92
                                        text: qsTr("学校段階")
                                        color: "#475467"
                                        font.pixelSize: 10
                                        font.weight: Font.DemiBold
                                    }
                                    Label {
                                        Layout.preferredWidth: 100
                                        text: qsTr("科目コード")
                                        color: "#475467"
                                        font.pixelSize: 10
                                        font.weight: Font.DemiBold
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("科目名")
                                        color: "#475467"
                                        font.pixelSize: 10
                                        font.weight: Font.DemiBold
                                    }
                                    Label {
                                        Layout.preferredWidth: 96
                                        text: qsTr("指導可否")
                                        color: "#475467"
                                        font.pixelSize: 10
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }

                            ListView {
                                id: qualificationList

                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 2
                                model: root.qualificationRows
                                boundsBehavior: Flickable.StopAtBounds

                                ScrollBar.vertical: ScrollBar {
                                    policy: ScrollBar.AsNeeded
                                }

                                delegate: Rectangle {
                                    id: qualificationDelegate

                                    required property int index
                                    required property var modelData
                                    width: ListView.view.width
                                    height: 38
                                    color: index % 2 === 0 ? "#ffffff" : "#f8fafc"
                                    border.color: "#edf0f4"

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12

                                        Label {
                                            Layout.preferredWidth: 92
                                            text: root.rowValue(qualificationDelegate.modelData, "levelLabel", "")
                                            color: "#667085"
                                            font.pixelSize: 10
                                        }
                                        Label {
                                            Layout.preferredWidth: 100
                                            text: root.rowValue(qualificationDelegate.modelData, "code", "")
                                            color: "#475467"
                                            font.pixelSize: 10
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: root.rowValue(qualificationDelegate.modelData, "displayName", "")
                                            color: "#344054"
                                            font.pixelSize: 11
                                            elide: Text.ElideRight
                                        }
                                        CheckBox {
                                            Layout.preferredWidth: 96
                                            text: checked ? qsTr("担当可") : qsTr("担当不可")
                                            checked: root.asBoolean(
                                                         root.rowValue(qualificationDelegate.modelData, "canTeach", false),
                                                         false)
                                            enabled: root.rowValue(qualificationDelegate.modelData, "active", true)
                                            Accessible.name: qsTr("%1 %2")
                                                             .arg(root.rowValue(
                                                                      qualificationDelegate.modelData,
                                                                      "displayName", ""))
                                                             .arg(text)
                                            onClicked: root.setQualificationDraft(
                                                           root.rowValue(qualificationDelegate.modelData, "id", ""),
                                                           checked)
                                        }
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true

                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("%1科目を表示").arg(qualificationList.count)
                                    color: "#667085"
                                    font.pixelSize: 10
                                }

                                Button {
                                    text: qsTr("キャンセル")
                                    enabled: root.qualificationsDirty
                                    onClicked: {
                                        root.reloadQualifications()
                                        root.viewModel.discardDraft()
                                    }
                                }

                                Button {
                                    text: qsTr("変更を保存")
                                    highlighted: true
                                    enabled: root.qualificationsDirty
                                    onClicked: root.saveQualifications()
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Timer {
        id: teacherFilterDelay
        interval: 250
        repeat: false
        onTriggered: root.viewModel.setTeacherFilter(teacherSearch.text)
    }

    Timer {
        id: qualificationReloadDelay
        interval: 0
        repeat: false
        onTriggered: root.reloadQualifications()
    }

    Connections {
        target: root.viewModel
        ignoreUnknownSignals: true
        function onCurrentTeacherQualificationsChanged() {
            root.reloadQualifications()
        }
    }

    Dialogs.MessageDialog {
        id: deactivateTeacherDialog

        title: qsTr("講師を使用停止")
        text: qsTr("%1を使用停止にしますか？").arg(teacherName.text || qsTr("選択中の講師"))
        informativeText: qsTr("過去の参照を保つためデータは削除されません。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.deactivateTeacher(root.editingTeacherId)
        }
    }

    Dialogs.MessageDialog {
        id: deleteTeacherDialog

        title: qsTr("講師を削除")
        text: qsTr("%1を削除しますか？").arg(teacherName.text || qsTr("選択中の講師"))
        informativeText: qsTr("指導資格は削除され、受講希望の講師欄は未設定になります。この操作は元に戻せません。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.deleteTeacher(root.editingTeacherId)
        }
    }
}
