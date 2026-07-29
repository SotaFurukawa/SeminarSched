pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    property bool hasPreview: false
    property string previewFile: ""

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function summaryValue(summary, keys, fallback) {
        for (let i = 0; i < keys.length; ++i) {
            if (summary && summary[keys[i]] !== undefined && summary[keys[i]] !== null)
                return summary[keys[i]]
        }
        return fallback
    }

    function summaryText() {
        const summary = root.viewModel.excelPreviewSummary
        if (!summary)
            return qsTr("取込みファイルを選択すると、反映前に件数と検証結果を表示します。")
        if (typeof summary === "string")
            return summary
        return qsTr("新規 %1件／更新 %2件／変更なし %3件／警告 %4件／エラー %5件")
                .arg(root.summaryValue(summary, ["newCount", "createCount"], 0))
                .arg(root.summaryValue(summary, ["updateCount"], 0))
                .arg(root.summaryValue(summary, ["unchangedCount", "skipCount"], 0))
                .arg(root.summaryValue(summary, ["warningCount"], 0))
                .arg(root.summaryValue(summary, ["errorCount"], 0))
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: exportContent.implicitHeight + 26
                radius: 8
                color: "#f8fafc"
                border.color: "#e2e7ee"

                ColumnLayout {
                    id: exportContent

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 7

                    Label {
                        text: qsTr("Excelテンプレート出力")
                        color: "#344054"
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("現在のマスターをmaster_data.xlsx形式で出力します。")
                        color: "#667085"
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
                    }

                    Button {
                        Layout.alignment: Qt.AlignLeft
                        text: qsTr("master_data.xlsxを保存…")
                        highlighted: true
                        onClicked: exportDialog.open()
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: importContent.implicitHeight + 26
                radius: 8
                color: "#f8fafc"
                border.color: "#e2e7ee"

                ColumnLayout {
                    id: importContent

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 7

                    Label {
                        text: qsTr("Excel基本取込み")
                        color: "#344054"
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("ファイルを検証し、プレビュー確認後に一括反映します。")
                        color: "#667085"
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
                    }

                    Button {
                        Layout.alignment: Qt.AlignLeft
                        text: qsTr("取込みファイルを選択…")
                        highlighted: true
                        onClicked: importDialog.open()
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: sheetContent.implicitHeight + 22
            radius: 7
            color: "#f5f8fc"
            border.color: "#d9e1ec"

            ColumnLayout {
                id: sheetContent

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 3

                Label {
                    text: qsTr("テンプレートのシート")
                    color: "#344054"
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                }

                Label {
                    Layout.fillWidth: true
                    text: qsTr("生徒／講師／科目／講師対応科目／受講希望")
                    color: "#52647d"
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: previewHeader.implicitHeight + 26
            radius: 8
            color: root.viewModel.errorMessage ? "#fff6f5" : "#ffffff"
            border.color: root.viewModel.errorMessage ? "#e5aaa6" : "#dce2ea"

            ColumnLayout {
                id: previewHeader

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                spacing: 5

                RowLayout {
                    Layout.fillWidth: true

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("取込みプレビュー")
                        color: "#344054"
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }

                    Label {
                        visible: root.hasPreview
                        text: root.viewModel.errorMessage ? qsTr("✕ エラーあり") : qsTr("✓ 検証済み")
                        color: root.viewModel.errorMessage ? "#a23b3b" : "#176b40"
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.previewFile.length > 0
                    text: root.previewFile
                    color: "#7a8493"
                    font.pixelSize: 9
                    elide: Text.ElideMiddle
                }

                Label {
                    Layout.fillWidth: true
                    text: root.summaryText()
                    color: "#475467"
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }

                Label {
                    Layout.fillWidth: true
                    visible: Boolean(root.viewModel.errorMessage)
                    text: root.viewModel.errorMessage
                    color: "#a23b3b"
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true

            Label {
                Layout.fillWidth: true
                text: qsTr("行単位の検証結果（行番号／列名／内容）")
                color: "#344054"
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }

            Label {
                text: qsTr("%1件").arg(issueList.count)
                color: "#667085"
                font.pixelSize: 10
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 29
            color: "#eef2f6"
            border.color: "#dce2ea"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10

                Label {
                    Layout.preferredWidth: 65
                    text: qsTr("状態")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.preferredWidth: 70
                    text: qsTr("行番号")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.preferredWidth: 150
                    text: qsTr("列名")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.fillWidth: true
                    text: qsTr("検証内容")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
            }
        }

        ListView {
            id: issueList

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 2
            model: root.viewModel.excelIssues
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            delegate: Rectangle {
                id: issueDelegate

                required property int index
                required property var modelData
                width: ListView.view.width
                height: 36
                color: index % 2 === 0 ? "#ffffff" : "#f8fafc"
                border.color: "#edf0f4"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10

                    Label {
                        Layout.preferredWidth: 65
                        text: {
                            const severity = String(root.rowValue(
                                                        issueDelegate.modelData, "severity", "error")).toLowerCase()
                            return severity.indexOf("warn") >= 0 ? qsTr("警告") : qsTr("エラー")
                        }
                        color: {
                            const severity = String(root.rowValue(
                                                        issueDelegate.modelData, "severity", "error")).toLowerCase()
                            return severity.indexOf("warn") >= 0 ? "#8a5a00" : "#a23b3b"
                        }
                        font.pixelSize: 9
                        font.weight: Font.DemiBold
                    }
                    Label {
                        Layout.preferredWidth: 70
                        text: root.rowValue(issueDelegate.modelData, "row", "")
                        color: "#475467"
                        font.pixelSize: 9
                    }
                    Label {
                        Layout.preferredWidth: 150
                        text: root.rowValue(issueDelegate.modelData, "column", "")
                        color: "#475467"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.rowValue(issueDelegate.modelData, "message", "")
                        color: "#344054"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Label {
            Layout.fillWidth: true
            visible: issueList.count === 0
            text: root.hasPreview
                  ? qsTr("行単位の警告・エラーはありません。")
                  : qsTr("まだプレビューされていません。")
            color: root.hasPreview ? "#176b40" : "#7a8493"
            font.pixelSize: 10
            horizontalAlignment: Text.AlignHCenter
        }

        RowLayout {
            Layout.fillWidth: true

            Label {
                Layout.fillWidth: true
                text: qsTr("反映はトランザクションで行い、エラー時はロールバックされます。")
                color: "#667085"
                font.pixelSize: 9
            }

            Button {
                text: qsTr("プレビュー内容を反映")
                highlighted: true
                enabled: root.hasPreview
                         && root.summaryValue(root.viewModel.excelPreviewSummary,
                                              ["errorCount"], 1) === 0
                onClicked: applyConfirmDialog.open()
            }
        }
    }

    Dialogs.FileDialog {
        id: exportDialog

        title: qsTr("マスターデータをExcelへ出力")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("Excelブック (*.xlsx)")]
        onAccepted: root.viewModel.exportMasterData(selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: importDialog

        title: qsTr("マスターデータを取込み")
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: [qsTr("Excelブック (*.xlsx)")]
        onAccepted: {
            root.hasPreview = true
            root.previewFile = selectedFile.toString()
            root.viewModel.previewMasterImport(selectedFile.toString())
        }
    }

    Dialogs.MessageDialog {
        id: applyConfirmDialog

        title: qsTr("マスターデータを反映")
        text: root.summaryText()
        informativeText: qsTr("プレビュー済みの5シートを1つのトランザクションで反映します。続行しますか？")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes
                    && root.viewModel.applyMasterImport())
                root.hasPreview = false
        }
    }
}
