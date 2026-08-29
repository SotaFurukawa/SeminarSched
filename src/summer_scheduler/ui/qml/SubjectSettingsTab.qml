pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    property int editingId: 0
    property var selectedRow: null
    property bool saveAttempted: false
    property int sortIndex: 0
    readonly property var sortedSubjects: buildSortedSubjects()

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function normalizedLevel(value) {
        const raw = String(value).toLowerCase()
        if (raw.indexOf("element") >= 0 || raw.indexOf("primary") >= 0
                || raw.indexOf("小") >= 0)
            return "elementary"
        if (raw.indexOf("middle") >= 0 || raw.indexOf("junior") >= 0
                || raw.indexOf("中") >= 0)
            return "middle"
        if (raw.indexOf("high") >= 0 || raw.indexOf("高") >= 0)
            return "high"
        return raw
    }

    function levelLabel(value) {
        const normalized = root.normalizedLevel(value)
        if (normalized === "elementary")
            return qsTr("小学校")
        if (normalized === "middle")
            return qsTr("中学校")
        if (normalized === "high")
            return qsTr("高校")
        return qsTr("その他")
    }

    function levelIndex(value) {
        const normalized = root.normalizedLevel(value)
        if (normalized === "elementary")
            return 0
        if (normalized === "middle")
            return 1
        if (normalized === "high")
            return 2
        return 0
    }

    function buildSortedSubjects() {
        const rows = []
        const source = root.viewModel.subjects || []
        for (let i = 0; i < source.length; ++i)
            rows.push(source[i])
        rows.sort(function (left, right) {
            if (root.sortIndex === 1)
                return String(root.rowValue(left, "code", "")).localeCompare(
                            String(root.rowValue(right, "code", "")), "ja", {numeric: true})
            if (root.sortIndex === 2)
                return String(root.rowValue(left, "displayName", "")).localeCompare(
                            String(root.rowValue(right, "displayName", "")), "ja")
            const levelCompare = root.normalizedLevel(root.rowValue(left, "schoolLevel", ""))
                    .localeCompare(root.normalizedLevel(
                                       root.rowValue(right, "schoolLevel", "")))
            if (levelCompare !== 0)
                return levelCompare
            return Number(root.rowValue(left, "sortOrder", 0))
                    - Number(root.rowValue(right, "sortOrder", 0))
        })
        return rows
    }

    function loadSubject(row) {
        root.selectedRow = row
        root.editingId = Number(root.rowValue(row, "id", 0))
        subjectCode.text = root.rowValue(row, "code", "")
        subjectName.text = root.rowValue(row, "displayName", "")
        subjectLevel.currentIndex = root.levelIndex(root.rowValue(row, "schoolLevel", ""))
        subjectOrder.value = Number(root.rowValue(row, "sortOrder", 1))
        subjectActive.checked = Boolean(root.rowValue(row, "active", true))
        root.saveAttempted = false
    }

    function clearSubject() {
        root.selectedRow = null
        root.editingId = 0
        subjectCode.text = ""
        subjectName.text = ""
        subjectLevel.currentIndex = 0
        subjectOrder.value = Math.max(1, subjectList.count + 1)
        subjectActive.checked = true
        root.saveAttempted = false
    }

    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal
        handle: Rectangle {
            implicitWidth: 16
            color: "transparent"

            Rectangle {
                anchors.centerIn: parent
                width: 1
                height: parent.height - 16
                color: "#d5dce6"
            }
        }

        Rectangle {
            SplitView.preferredWidth: 430
            SplitView.minimumWidth: 340
            color: "#f8fafc"
            border.color: "#e2e7ee"
            radius: 8

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1

                        Label {
                            text: qsTr("科目マスター")
                            color: "#344054"
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }

                        Label {
                            text: qsTr("%1件　学校段階／コード／科目名／状態").arg(subjectList.count)
                            color: "#667085"
                            font.pixelSize: 9
                        }
                    }

                    Button {
                        text: qsTr("＋ 追加")
                        onClicked: root.clearSubject()
                    }
                }

                ComboBox {
                    Layout.fillWidth: true
                    model: [qsTr("学校段階・表示順"), qsTr("コード順"), qsTr("科目名順")]
                    Accessible.name: qsTr("科目一覧の並べ替え")
                    onActivated: root.sortIndex = currentIndex
                }

                ListView {
                    id: subjectList

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 4
                    model: root.sortedSubjects
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: ItemDelegate {
                        id: subjectDelegate

                        required property var modelData
                        width: ListView.view.width
                        height: 52
                        highlighted: root.editingId
                                     === Number(root.rowValue(modelData, "id", 0))
                        Accessible.name: qsTr("%1 %2 %3 %4")
                                         .arg(root.levelLabel(root.rowValue(modelData, "schoolLevel", "")))
                                         .arg(root.rowValue(modelData, "code", ""))
                                         .arg(root.rowValue(modelData, "displayName", ""))
                                         .arg(root.rowValue(modelData, "active", true)
                                              ? qsTr("使用中") : qsTr("停止中"))
                        onClicked: root.loadSubject(modelData)

                        contentItem: RowLayout {
                            spacing: 8

                            Rectangle {
                                Layout.preferredWidth: 52
                                Layout.preferredHeight: 28
                                radius: 14
                                color: subjectDelegate.highlighted ? "#2767c5" : "#e8edf4"

                                Label {
                                    anchors.centerIn: parent
                                    text: root.levelLabel(
                                              root.rowValue(subjectDelegate.modelData, "schoolLevel", ""))
                                    color: subjectDelegate.highlighted ? "#ffffff" : "#475467"
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1

                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(subjectDelegate.modelData, "displayName", "")
                                    color: "#344054"
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("%1　表示順 %2").arg(
                                              root.rowValue(subjectDelegate.modelData, "code", ""))
                                          .arg(root.rowValue(subjectDelegate.modelData, "sortOrder", ""))
                                    color: "#667085"
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                            }

                            Label {
                                text: root.rowValue(subjectDelegate.modelData, "active", true)
                                      ? qsTr("使用中") : qsTr("停止中")
                                color: root.rowValue(subjectDelegate.modelData, "active", true)
                                       ? "#176b40" : "#7a8493"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }
            }
        }

        ScrollView {
            id: subjectEditorScroll

            SplitView.fillWidth: true
            SplitView.minimumWidth: 420
            clip: true
            leftPadding: 10
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: subjectEditorScroll.availableWidth
                spacing: 10

                Label {
                    text: root.editingId > 0 ? qsTr("科目を編集") : qsTr("新しい科目")
                    color: "#344054"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }

                Label {
                    Layout.fillWidth: true
                    text: qsTr("科目コードはExcel取込みや講師資格で使う安定したIDです。高校数学一般と高校数学IIIは別々に管理してください。")
                    color: "#667085"
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: qsTr("科目コード *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: subjectCode
                            Layout.fillWidth: true
                            placeholderText: qsTr("例：H_MATH_III")
                            Accessible.name: qsTr("科目コード")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && subjectCode.text.trim() === ""
                            text: qsTr("科目コードを入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 9
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: qsTr("表示名 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        TextField {
                            id: subjectName
                            Layout.fillWidth: true
                            placeholderText: qsTr("例：高校・数学III")
                            Accessible.name: qsTr("科目表示名")
                            onTextEdited: root.viewModel.markDirty()
                        }
                        Label {
                            visible: root.saveAttempted && subjectName.text.trim() === ""
                            text: qsTr("表示名を入力してください。")
                            color: "#a23b3b"
                            font.pixelSize: 9
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
                            text: qsTr("学校段階 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        ComboBox {
                            id: subjectLevel
                            Layout.fillWidth: true
                            model: [
                                {"label": qsTr("小学校"), "value": "elementary"},
                                {"label": qsTr("中学校"), "value": "junior_high"},
                                {"label": qsTr("高校"), "value": "high_school"}
                            ]
                            textRole: "label"
                            valueRole: "value"
                            Accessible.name: qsTr("学校段階")
                            onActivated: root.viewModel.markDirty()
                        }
                    }

                    ColumnLayout {
                        Layout.preferredWidth: 150
                        spacing: 3
                        Label {
                            text: qsTr("表示順 *")
                            color: "#344054"
                            font.pixelSize: 11
                        }
                        SpinBox {
                            id: subjectOrder
                            Layout.fillWidth: true
                            from: 1
                            to: 999
                            value: 1
                            editable: true
                            Accessible.name: qsTr("科目表示順")
                            onValueModified: root.viewModel.markDirty()
                        }
                    }
                }

                CheckBox {
                    id: subjectActive
                    text: qsTr("この科目を新規登録・時間割作成で使用する")
                    checked: true
                    onClicked: root.viewModel.markDirty()
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: subjectValidationHelp.implicitHeight + 22
                    radius: 7
                    color: "#f5f8fc"
                    border.color: "#d9e1ec"

                    Label {
                        id: subjectValidationHelp
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        text: qsTr("保存時に科目コードの重複を検証します。使用停止しても、既存の受講希望・資格との参照は保持されます。")
                        color: "#52647d"
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
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

                    Button {
                        visible: root.editingId > 0
                        text: qsTr("使用停止")
                        enabled: subjectActive.checked
                        onClicked: deactivateSubjectDialog.open()
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    Button {
                        text: qsTr("キャンセル")
                        onClicked: {
                            if (root.selectedRow)
                                root.loadSubject(root.selectedRow)
                            else
                                root.clearSubject()
                            root.viewModel.discardDraft()
                        }
                    }

                    Button {
                        text: qsTr("保存")
                        highlighted: true
                        onClicked: {
                            root.saveAttempted = true
                            if (subjectCode.text.trim() === ""
                                    || subjectName.text.trim() === "")
                                return
                            root.viewModel.saveSubject(
                                        root.editingId,
                                        subjectCode.text.trim(),
                                        subjectName.text.trim(),
                                        subjectLevel.currentValue,
                                        subjectOrder.value,
                                        subjectActive.checked)
                        }
                    }
                }
            }
        }
    }

    Dialogs.MessageDialog {
        id: deactivateSubjectDialog

        title: qsTr("科目を使用停止")
        text: qsTr("%1を使用停止にしますか？").arg(subjectName.text || qsTr("選択中の科目"))
        informativeText: qsTr("既存の受講希望と講師資格は削除されません。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.deactivateSubject(root.editingId)
        }
    }
}
