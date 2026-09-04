pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested
    signal navigateRequested(int pageIndex)

    readonly property var filteredIssues: buildFilteredIssues()

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function summaryValue(key) {
        return Number(root.rowValue(root.viewModel.validationSummary, key, 0))
    }

    function severityLabel(value) {
        const severity = String(value).toLowerCase()
        if (severity === "error")
            return qsTr("✕ エラー")
        if (severity === "warning")
            return qsTr("△ 警告")
        return qsTr("ⓘ 情報")
    }

    function severityColor(value) {
        const severity = String(value).toLowerCase()
        if (severity === "error")
            return "#a23b3b"
        if (severity === "warning")
            return "#8a5a00"
        return "#174f9e"
    }

    function detailsText(row) {
        const details = root.rowValue(row, "details", null)
        if (!details)
            return ""
        const parts = []
        const keys = Object.keys(details)
        for (let i = 0; i < keys.length; ++i)
            parts.push(qsTr("%1=%2").arg(keys[i]).arg(String(details[keys[i]])))
        return parts.join(" / ")
    }

    function targetPageForIssue(row) {
        const entity = String(root.rowValue(row, "entityType", ""))
                          .toLocaleLowerCase()
        if (entity === "student")
            return 1
        if (entity === "teacher")
            return 2
        if (entity.indexOf("availability") >= 0 || entity === "import_batch")
            return 3
        if (entity === "lesson_request" || entity === "assignment"
                || entity === "assignmentsession")
            return 4
        if (entity === "project" || entity === "open_date"
                || entity === "time_slot" || entity === "subject")
            return 7
        return 5
    }

    function buildFilteredIssues() {
        const rows = []
        const source = root.viewModel.validationIssues || []
        const severity = severityFilter.currentValue || ""
        const query = validationSearch.text.trim().toLocaleLowerCase()
        for (let i = 0; i < source.length; ++i) {
            const row = source[i]
            if (severity !== ""
                    && String(root.rowValue(row, "severity", "")) !== severity)
                continue
            const haystack = [
                root.rowValue(row, "message", ""),
                root.rowValue(row, "type", ""),
                root.rowValue(row, "entityType", ""),
                root.rowValue(row, "entityId", "")
            ].join(" ").toLocaleLowerCase()
            if (query !== "" && haystack.indexOf(query) < 0)
                continue
            rows.push(row)
        }
        return rows
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 20
        visible: !root.viewModel.hasOpenProject
        radius: 10
        color: "#ffffff"
        border.color: "#dce2ea"

        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(parent.width - 48, 520)
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: qsTr("プロジェクトが開かれていません")
                color: "#344054"
                font.pixelSize: 18
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("入力検証はプロジェクト全体を対象にします。先にホームからプロジェクトを開いてください。")
                color: "#667085"
                font.pixelSize: 11
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
            }
            Button {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("ホームへ移動")
                onClicked: root.openHomeRequested()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        visible: root.viewModel.hasOpenProject
        spacing: 9

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Label {
                    text: qsTr("入力検証・警告")
                    color: "#18212f"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                }
                Label {
                    text: qsTr("プロジェクト全体を再検証し、エラー・警告・情報を区別して表示します。")
                    color: "#667085"
                    font.pixelSize: 10
                }
            }

            Button {
                text: qsTr("匿名サンプルを作成…")
                onClicked: anonymousSampleDialog.open()
            }
            Button {
                text: qsTr("表示を再読込み")
                onClicked: root.viewModel.refreshPhase3()
            }
            Button {
                text: qsTr("プロジェクト全体を検証")
                highlighted: true
                onClicked: root.viewModel.runProjectValidation()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: Boolean(root.viewModel.errorMessage)
                     || Boolean(root.viewModel.statusMessage)
            implicitHeight: validationMessage.implicitHeight + 16
            radius: 6
            color: root.viewModel.errorMessage ? "#fff6f5" : "#ecfdf3"
            border.color: root.viewModel.errorMessage ? "#e5aaa6" : "#a9dec0"

            Label {
                id: validationMessage

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                text: root.viewModel.errorMessage
                      ? qsTr("✕ %1").arg(root.viewModel.errorMessage)
                      : qsTr("✓ %1").arg(root.viewModel.statusMessage)
                color: root.viewModel.errorMessage ? "#a23b3b" : "#176b40"
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: [
                    {
                        "label": qsTr("エラー"),
                        "key": "errorCount",
                        "symbol": "✕",
                        "color": "#a23b3b",
                        "background": "#fff6f5"
                    },
                    {
                        "label": qsTr("警告"),
                        "key": "warningCount",
                        "symbol": "△",
                        "color": "#8a5a00",
                        "background": "#fff8e8"
                    },
                    {
                        "label": qsTr("情報"),
                        "key": "infoCount",
                        "symbol": "ⓘ",
                        "color": "#174f9e",
                        "background": "#eef5ff"
                    }
                ]

                delegate: Rectangle {
                    id: validationSummaryDelegate

                    required property var modelData
                    Layout.preferredWidth: 146
                    Layout.preferredHeight: 58
                    radius: 7
                    color: root.rowValue(validationSummaryDelegate.modelData,
                                         "background", "#ffffff")
                    border.color: root.rowValue(validationSummaryDelegate.modelData,
                                                "color", "#dce2ea")

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: 8

                        Label {
                            text: root.rowValue(validationSummaryDelegate.modelData,
                                                "symbol", "")
                            color: root.rowValue(validationSummaryDelegate.modelData,
                                                "color", "#475467")
                            font.pixelSize: 18
                            font.weight: Font.Bold
                        }
                        ColumnLayout {
                            spacing: 0
                            Label {
                                text: root.rowValue(validationSummaryDelegate.modelData,
                                                    "label", "")
                                color: "#667085"
                                font.pixelSize: 9
                            }
                            Label {
                                text: root.summaryValue(
                                          root.rowValue(
                                              validationSummaryDelegate.modelData,
                                              "key", ""))
                                color: root.rowValue(
                                           validationSummaryDelegate.modelData,
                                           "color", "#344054")
                                font.pixelSize: 20
                                font.weight: Font.Bold
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 58
                radius: 7
                color: root.rowValue(root.viewModel.validationSummary,
                                     "canOptimize", false)
                       ? "#ecfdf3" : "#fff6f5"
                border.color: root.rowValue(root.viewModel.validationSummary,
                                            "canOptimize", false)
                              ? "#a9dec0" : "#e5aaa6"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: 1

                    Label {
                        Layout.alignment: Qt.AlignVCenter
                        text: root.rowValue(root.viewModel.validationSummary,
                                            "canOptimize", false)
                              ? qsTr("✓ Phase 3で扱う入力範囲にエラーはありません")
                              : qsTr("✕ エラーを解消するまで最適化を開始できません")
                        color: root.rowValue(root.viewModel.validationSummary,
                                             "canOptimize", false)
                               ? "#176b40" : "#a23b3b"
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Assignment依存の検証、OR-Tools実行、未配置理由はPhase 4で扱います。")
                        color: "#667085"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: filterRow.implicitHeight + 16
            radius: 7
            color: "#ffffff"
            border.color: "#dce2ea"

            RowLayout {
                id: filterRow

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 9
                anchors.rightMargin: 9
                spacing: 8

                Label {
                    text: qsTr("絞込み")
                    color: "#344054"
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                }

                ComboBox {
                    id: severityFilter

                    Layout.preferredWidth: 150
                    model: [
                        {"label": qsTr("すべての重要度"), "value": ""},
                        {"label": qsTr("エラーのみ"), "value": "error"},
                        {"label": qsTr("警告のみ"), "value": "warning"},
                        {"label": qsTr("情報のみ"), "value": "info"}
                    ]
                    textRole: "label"
                    valueRole: "value"
                    Accessible.name: qsTr("重要度フィルター")
                }

                TextField {
                    id: validationSearch

                    Layout.fillWidth: true
                    placeholderText: qsTr("メッセージ、検証種別、対象IDを部分検索")
                    Accessible.name: qsTr("入力検証検索")
                }

                Label {
                    text: qsTr("%1件表示").arg(validationIssueList.count)
                    color: "#667085"
                    font.pixelSize: 9
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 8
            color: "#ffffff"
            border.color: "#dce2ea"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 9
                spacing: 0

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 31
                    color: "#eef2f6"
                    border.color: "#dce2ea"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 9
                        anchors.rightMargin: 9
                        spacing: 8

                        Label {
                            Layout.preferredWidth: 82
                            text: qsTr("重要度")
                            color: "#475467"
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                        }
                        Label {
                            Layout.preferredWidth: 150
                            text: qsTr("検証種別／対象")
                            color: "#475467"
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                        }
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("内容／詳細")
                            color: "#475467"
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                        }
                        Label {
                            Layout.preferredWidth: 116
                            text: qsTr("修正先")
                            color: "#475467"
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }

                ListView {
                    id: validationIssueList

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 1
                    model: root.filteredIssues
                    boundsBehavior: Flickable.StopAtBounds

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    delegate: Rectangle {
                        id: validationIssueDelegate

                        required property int index
                        required property var modelData
                        width: ListView.view.width
                        height: 54
                        color: index % 2 === 0 ? "#ffffff" : "#f8fafc"
                        border.color: "#edf0f4"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 9
                            anchors.rightMargin: 9
                            spacing: 8

                            Label {
                                Layout.preferredWidth: 82
                                text: root.severityLabel(
                                          root.rowValue(
                                              validationIssueDelegate.modelData,
                                              "severity", "info"))
                                color: root.severityColor(
                                           root.rowValue(
                                               validationIssueDelegate.modelData,
                                               "severity", "info"))
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }

                            ColumnLayout {
                                Layout.preferredWidth: 150
                                spacing: 0
                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(
                                              validationIssueDelegate.modelData,
                                              "type", "")
                                    color: "#344054"
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: {
                                        const entity = root.rowValue(
                                                         validationIssueDelegate.modelData,
                                                         "entityType", "")
                                        const id = root.rowValue(
                                                       validationIssueDelegate.modelData,
                                                       "entityId", "")
                                        return id === "" ? entity
                                                         : qsTr("%1 / ID:%2").arg(entity).arg(id)
                                    }
                                    color: "#7a8493"
                                    font.pixelSize: 8
                                    elide: Text.ElideRight
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(
                                              validationIssueDelegate.modelData,
                                              "message", "")
                                    color: "#344054"
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: root.detailsText(
                                              validationIssueDelegate.modelData)
                                    visible: text !== ""
                                    color: "#7a8493"
                                    font.pixelSize: 8
                                    elide: Text.ElideRight
                                }
                            }
                            AppButton {
                                Layout.preferredWidth: 116
                                text: qsTr("該当画面を開く")
                                Accessible.name: qsTr("この問題の修正画面を開く")
                                onClicked: root.navigateRequested(
                                               root.targetPageForIssue(
                                                   validationIssueDelegate.modelData))
                            }
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: validationIssueList.count === 0
                    text: (root.viewModel.validationIssues || []).length === 0
                          ? qsTr("まだ検証されていません。「プロジェクト全体を検証」を実行してください。")
                          : qsTr("現在の絞込み条件に一致する項目はありません。")
                    color: "#7a8493"
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    Dialogs.FileDialog {
        id: anonymousSampleDialog
        title: qsTr("匿名サンプルプロジェクトを作成")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("塾時間割プロジェクト (*.jukuschedule)")]
        onAccepted: root.viewModel.createAnonymousSample(selectedFile.toString())
    }
}
