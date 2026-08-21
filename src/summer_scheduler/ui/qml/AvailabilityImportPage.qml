pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    required property var workspace
    signal openHomeRequested
    property bool mappingExpanded: false
    property bool scriptGeneratorExpanded: true

    UiTheme { id: theme }

    readonly property bool hasValidatedPreview: summaryValue("addCount") > 0
                                                 || summaryValue("changeCount") > 0
                                                 || summaryValue("unchangedCount") > 0
                                                 || summaryValue("deleteCandidateCount") > 0
                                                 || summaryValue("errorCount") > 0
                                                 || summaryValue("warningCount") > 0
    readonly property bool justApplied: String(viewModel.statusMessage || "")
                                        .indexOf("アンケートを反映しました") >= 0
    readonly property int currentImportStep: justApplied ? 2
                                             : Boolean(viewModel.sourcePath) ? 1 : 0
    readonly property int configuredOpenDateCount: countOpenDates()
    readonly property int configuredTimeSlotCount: countEnabledTimeSlots()

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function summaryValue(key) {
        return Number(root.rowValue(root.viewModel.importSummary, key, 0))
    }

    function headerOptions() {
        const options = [qsTr("未選択")]
        const headers = root.viewModel.sourceHeaders || []
        for (let i = 0; i < headers.length; ++i)
            options.push(String(headers[i]))
        return options
    }

    function headerIndex(sourceHeader) {
        const options = root.headerOptions()
        for (let i = 1; i < options.length; ++i) {
            if (String(options[i]) === String(sourceHeader))
                return i
        }
        return 0
    }

    function sheetIndex(sheetName) {
        const sheets = root.viewModel.sourceSheets || []
        for (let i = 0; i < sheets.length; ++i) {
            if (String(sheets[i]) === String(sheetName))
                return i
        }
        return sheets.length > 0 ? 0 : -1
    }

    function encodingIndex(encoding) {
        if (encoding === "utf-8-sig")
            return 1
        if (encoding === "cp932")
            return 2
        return 0
    }

    function previewRowText(row) {
        if (!row)
            return ""
        const parts = []
        const keys = Object.keys(row)
        for (let i = 0; i < keys.length; ++i) {
            if (i >= 8) {
                parts.push(qsTr("…ほか%1列").arg(keys.length - i))
                break
            }
            parts.push(qsTr("%1=%2").arg(keys[i]).arg(String(row[keys[i]])))
        }
        return parts.join("  /  ")
    }

    function countOpenDates() {
        const rows = root.workspace.openDates || []
        let count = 0
        for (let i = 0; i < rows.length; ++i) {
            if (Boolean(root.rowValue(rows[i], "isOpen", false)))
                count += 1
        }
        return count
    }

    function countEnabledTimeSlots() {
        const rows = root.workspace.timeSlots || []
        let count = 0
        for (let i = 0; i < rows.length; ++i) {
            if (Boolean(root.rowValue(rows[i], "enabled", false)))
                count += 1
        }
        return count
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
                text: qsTr("アンケート回答はプロジェクト単位で検証・保存します。先にホームからプロジェクトを開いてください。")
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
                    text: qsTr("アンケート取込み")
                    color: theme.textPrimary
                    font.pixelSize: theme.titleSize
                    font.weight: Font.Bold
                }
                Label {
                    text: qsTr("xlsx／CSVを列マッピングし、0=不可・1=可能・2=希望として安全に反映します。")
                    color: "#667085"
                    font.pixelSize: 10
                }
            }

            AppButton {
                text: root.scriptGeneratorExpanded
                      ? qsTr("フォーム作成を閉じる")
                      : qsTr("Googleフォームを作る")
                onClicked: root.scriptGeneratorExpanded = !root.scriptGeneratorExpanded
            }

            AppButton {
                text: root.viewModel.importKind === "teacher"
                      ? qsTr("講師テンプレートを保存…")
                      : qsTr("生徒テンプレートを保存…")
                onClicked: templateDialog.open()
            }

            AppButton {
                text: qsTr("取込みをクリア")
                enabled: Boolean(root.viewModel.sourcePath)
                onClicked: {
                    includeDeletes.checked = false
                    root.viewModel.clearImport()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: root.scriptGeneratorExpanded
            implicitHeight: formGeneratorContent.implicitHeight + 20
            radius: 8
            color: "#f7f9fc"
            border.color: "#cfd9e8"

            ColumnLayout {
                id: formGeneratorContent

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 7

                RowLayout {
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1

                        Label {
                            text: qsTr("Googleフォーム作成キット")
                            color: "#344054"
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Label {
                            text: qsTr("生徒用／講師勤務日時用／講師指導可能科目用のApps Scriptをまとめて作ります。")
                            color: "#667085"
                            font.pixelSize: 9
                        }
                    }

                    StatusBadge {
                        status: root.configuredOpenDateCount > 0
                                && root.configuredTimeSlotCount > 0
                                ? "complete" : "warning"
                        symbol: root.configuredOpenDateCount > 0
                                && root.configuredTimeSlotCount > 0 ? "✓" : "!"
                        label: qsTr("開校日 %1日／有効コマ %2件")
                               .arg(root.configuredOpenDateCount)
                               .arg(root.configuredTimeSlotCount)
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 4
                    columnSpacing: 8
                    rowSpacing: 5

                    Label {
                        text: qsTr("生徒用フォーム名（必須）")
                        color: "#344054"
                        font.pixelSize: 9
                    }
                    TextField {
                        id: studentFormTitle
                        Layout.fillWidth: true
                        text: qsTr("%1 個別指導受講申込")
                              .arg(root.workspace.currentProjectTitle || qsTr("講習"))
                        Accessible.name: qsTr("生徒用Googleフォーム名")
                    }
                    Label {
                        text: qsTr("講師用フォーム名（必須）")
                        color: "#344054"
                        font.pixelSize: 9
                    }
                    TextField {
                        id: teacherFormTitle
                        Layout.fillWidth: true
                        text: qsTr("%1 非常勤勤務アンケート")
                              .arg(root.workspace.currentProjectTitle || qsTr("講習"))
                        Accessible.name: qsTr("講師用Googleフォーム名")
                    }

                    Label {
                        text: qsTr("回答締切（必須）")
                        color: "#344054"
                        font.pixelSize: 9
                    }
                    TextField {
                        id: questionnaireDeadline
                        Layout.fillWidth: true
                        placeholderText: qsTr("例：2026年6月25日（木）")
                        Accessible.name: qsTr("Googleフォーム回答締切")
                    }
                    Label {
                        text: qsTr("問い合わせ先（必須）")
                        color: "#344054"
                        font.pixelSize: 9
                    }
                    TextField {
                        id: questionnaireContact
                        Layout.fillWidth: true
                        text: qsTr("校舎へお問い合わせください")
                        Accessible.name: qsTr("Googleフォーム問い合わせ先")
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        Layout.fillWidth: true
                        text: root.viewModel.lastQuestionnaireScriptDirectory
                              ? qsTr("保存済み：%1")
                                .arg(root.viewModel.lastQuestionnaireScriptDirectory)
                              : qsTr("3つの.gsと、貼り付け・実行手順書を同じフォルダーへ保存します。")
                        color: root.viewModel.lastQuestionnaireScriptDirectory
                               ? "#176b40" : "#667085"
                        font.pixelSize: 9
                        elide: Text.ElideMiddle
                    }

                    AppButton {
                        text: qsTr("保存先を開く")
                        visible: Boolean(root.viewModel.lastQuestionnaireScriptDirectory)
                        onClicked: root.viewModel.openQuestionnaireScriptDirectory()
                    }

                    AppButton {
                        text: qsTr("画像つき手順を見る")
                        onClicked: googleFormsGuideDialog.open()
                    }

                    AppButton {
                        text: qsTr("3種類のフォームをまとめて作成…")
                        kind: "primary"
                        enabled: root.configuredOpenDateCount > 0
                                 && root.configuredTimeSlotCount > 0
                                 && studentFormTitle.text.trim().length > 0
                                 && teacherFormTitle.text.trim().length > 0
                                 && questionnaireDeadline.text.trim().length > 0
                                 && questionnaireContact.text.trim().length > 0
                        ToolTip.visible: hovered && !enabled
                        ToolTip.text: qsTr("①の開校日・有効コマと、すべての必須欄を設定してください。")
                        onClicked: questionnaireFolderDialog.open()
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: [
                    {"label": qsTr("1　回答ファイルを選ぶ")},
                    {"label": qsTr("2　内容を確認する")},
                    {"label": qsTr("3　反映完了")}
                ]

                delegate: StatusBadge {
                    id: importStepBadge
                    required property int index
                    required property var modelData
                    Layout.fillWidth: true
                    status: index < root.currentImportStep ? "complete"
                            : index === root.currentImportStep ? "current" : "neutral"
                    symbol: index < root.currentImportStep ? "✓" : String(index + 1)
                    label: String(modelData.label)
                }
            }
        }

        InlineMessage {
            Layout.fillWidth: true
            visible: root.justApplied
            kind: "success"
            message: qsTr("回答をプロジェクトへ反映し、原本を.jukuschedule内に保管しました。再取込み時は新しい原本へ差し替えます。")
        }

        Rectangle {
            Layout.fillWidth: true
            visible: Boolean(root.viewModel.errorMessage)
                     || Boolean(root.viewModel.statusMessage)
            implicitHeight: importMessage.implicitHeight + 16
            radius: 6
            color: root.viewModel.errorMessage ? "#fff6f5" : "#ecfdf3"
            border.color: root.viewModel.errorMessage ? "#e5aaa6" : "#a9dec0"

            Label {
                id: importMessage

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

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: combinedContent.implicitHeight + 20
            radius: 9
            color: "#f5f9ff"
            border.color: "#9fc5e8"

            ColumnLayout {
                id: combinedContent

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 7

                RowLayout {
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Label {
                            text: qsTr("おすすめ：生徒・講師回答をまとめて取り込む")
                            color: "#183b59"
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("アプリから作成したGoogleフォームのCSV／xlsxを2つ選ぶだけで、氏名照合・受講希望・不可時間をまとめて検証します。")
                            color: "#52647d"
                            font.pixelSize: 9
                            wrapMode: Text.Wrap
                        }
                    }

                    AppButton {
                        text: qsTr("まとめて検証")
                        kind: "primary"
                        enabled: root.viewModel.canValidateCombinedSurvey
                        onClicked: root.viewModel.validateCombinedSurvey()
                    }

                    AppButton {
                        text: qsTr("検証済み内容を反映…")
                        enabled: root.viewModel.canApplyCombinedSurvey
                        onClicked: combinedApplyConfirmation.open()
                    }

                    AppButton {
                        text: qsTr("統合xlsxを保存…")
                        onClicked: combinedExportDialog.open()
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 8

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 58
                        radius: 6
                        color: "#ffffff"
                        border.color: "#cfd9e8"
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Label { text: qsTr("生徒回答"); color: "#344054"; font.weight: Font.DemiBold; font.pixelSize: 10 }
                                Label {
                                    Layout.fillWidth: true
                                    text: root.viewModel.combinedStudentPath || qsTr("未選択")
                                    color: root.viewModel.combinedStudentPath ? "#475467" : "#a23b3b"
                                    font.pixelSize: 9
                                    elide: Text.ElideMiddle
                                }
                            }
                            AppButton { text: qsTr("選択…"); onClicked: combinedStudentDialog.open() }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 58
                        radius: 6
                        color: "#ffffff"
                        border.color: "#cfd9e8"
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Label { text: qsTr("講師回答"); color: "#344054"; font.weight: Font.DemiBold; font.pixelSize: 10 }
                                Label {
                                    Layout.fillWidth: true
                                    text: root.viewModel.combinedTeacherPath || qsTr("未選択")
                                    color: root.viewModel.combinedTeacherPath ? "#475467" : "#a23b3b"
                                    font.pixelSize: 9
                                    elide: Text.ElideMiddle
                                }
                            }
                            AppButton { text: qsTr("選択…"); onClicked: combinedTeacherDialog.open() }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    visible: Number(root.rowValue(root.viewModel.combinedSummary, "studentCount", 0)) > 0
                             || Number(root.rowValue(root.viewModel.combinedSummary, "errorCount", 0)) > 0
                    spacing: 12
                    Label {
                        text: qsTr("生徒 %1名　講師 %2名")
                              .arg(root.rowValue(root.viewModel.combinedSummary, "studentCount", 0))
                              .arg(root.rowValue(root.viewModel.combinedSummary, "teacherCount", 0))
                        color: "#344054"
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }
                    Label {
                        text: qsTr("エラー %1件　警告 %2件")
                              .arg(root.rowValue(root.viewModel.combinedSummary, "errorCount", 0))
                              .arg(root.rowValue(root.viewModel.combinedSummary, "warningCount", 0))
                        color: Number(root.rowValue(root.viewModel.combinedSummary, "errorCount", 0)) > 0 ? "#a23b3b" : "#176b40"
                        font.pixelSize: 10
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("基本情報にない在籍生・講師は赤、体験生は黄で表示します。")
                        color: "#667085"
                        font.pixelSize: 9
                        horizontalAlignment: Text.AlignRight
                    }
                }

                ListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(contentHeight, 92)
                    visible: count > 0
                    clip: true
                    spacing: 3
                    model: root.viewModel.combinedIssues || []
                    delegate: Rectangle {
                        id: combinedIssueRow
                        required property var modelData
                        width: ListView.view.width
                        height: 38
                        radius: 4
                        color: root.rowValue(modelData, "severity", "") === "error" ? "#fff0ef" : "#fff9e8"
                        border.color: root.rowValue(modelData, "severity", "") === "error" ? "#e5aaa6" : "#e6c777"
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 6

                            Label {
                                Layout.fillWidth: true
                                text: qsTr("%1 %2行 %3：%4　→ %5")
                                      .arg(root.rowValue(combinedIssueRow.modelData, "source", ""))
                                      .arg(root.rowValue(combinedIssueRow.modelData, "row", ""))
                                      .arg(root.rowValue(combinedIssueRow.modelData, "personName", ""))
                                      .arg(root.rowValue(combinedIssueRow.modelData, "message", ""))
                                      .arg(root.rowValue(combinedIssueRow.modelData, "resolution", ""))
                                color: "#6a3430"
                                font.pixelSize: 9
                                elide: Text.ElideRight
                            }

                            ComboBox {
                                visible: Boolean(root.rowValue(combinedIssueRow.modelData, "canMarkTrial", false))
                                Layout.preferredWidth: 154
                                model: [qsTr("名簿と照合"), qsTr("体験生として登録")]
                                currentIndex: Boolean(root.rowValue(combinedIssueRow.modelData, "markedTrial", false)) ? 1 : 0
                                font.pixelSize: 9
                                onActivated: root.viewModel.setCombinedStudentTrialResolution(
                                                 Number(root.rowValue(combinedIssueRow.modelData, "row", 0)),
                                                 currentIndex === 1)
                            }
                        }
                    }
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: sourceControls.implicitHeight + 18
            radius: 8
            color: "#ffffff"
            border.color: "#dce2ea"

            ColumnLayout {
                id: sourceControls

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        text: qsTr("対象")
                        color: "#344054"
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }

                    AppButton {
                        Layout.preferredWidth: 110
                        text: qsTr("生徒回答")
                        checkable: true
                        checked: root.viewModel.importKind === "student"
                        kind: checked ? "primary" : "secondary"
                        onClicked: {
                            includeDeletes.checked = false
                            root.viewModel.setImportKind("student")
                        }
                    }
                    AppButton {
                        Layout.preferredWidth: 110
                        text: qsTr("講師回答")
                        checkable: true
                        checked: root.viewModel.importKind === "teacher"
                        kind: checked ? "primary" : "secondary"
                        onClicked: {
                            includeDeletes.checked = false
                            root.viewModel.setImportKind("teacher")
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 1
                        Layout.preferredHeight: 28
                        color: "#dce2ea"
                    }

                    ComboBox {
                        id: encodingBox

                        Layout.preferredWidth: 150
                        model: [
                            {"label": qsTr("CSV: 自動判定"), "value": "auto"},
                            {"label": "CSV: UTF-8", "value": "utf-8-sig"},
                            {"label": "CSV: CP932", "value": "cp932"}
                        ]
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: root.encodingIndex(
                                          root.viewModel.sourceEncoding)
                        Accessible.name: qsTr("CSV文字コード")
                        onActivated: root.viewModel.setSourceEncoding(currentValue)
                    }

                    AppButton {
                        text: qsTr("回答ファイルを選択…")
                        kind: "primary"
                        onClicked: sourceDialog.open()
                    }

                    Label {
                        Layout.fillWidth: true
                        text: root.viewModel.sourcePath || qsTr("ファイル未選択")
                        color: root.viewModel.sourcePath ? "#475467" : "#7a8493"
                        font.pixelSize: 9
                        elide: Text.ElideMiddle
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        text: qsTr("シート")
                        color: "#344054"
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }
                    ComboBox {
                        Layout.preferredWidth: 210
                        model: root.viewModel.sourceSheets || []
                        currentIndex: root.sheetIndex(
                                          root.viewModel.selectedSheet)
                        enabled: count > 0
                        Accessible.name: qsTr("取込み対象シート")
                        onActivated: root.viewModel.selectSourceSheet(currentText)
                    }

                    Label {
                        Layout.fillWidth: true
                        text: root.viewModel.sourceSheets.length > 0
                              ? qsTr("選択中：%1／文字コード：%2")
                                .arg(root.viewModel.selectedSheet || qsTr("未選択"))
                                .arg(root.viewModel.sourceEncoding || "auto")
                              : qsTr("xlsxはシート選択、CSVは文字コード判定後に列を対応付けます。")
                        color: "#667085"
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }

                    AppButton {
                        text: qsTr("検証して差分を作成")
                        kind: "primary"
                        enabled: Boolean(root.viewModel.sourcePath)
                        onClicked: {
                            includeDeletes.checked = false
                            root.viewModel.validateAvailabilityImport()
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    text: root.viewModel.storedSourceName
                          ? qsTr("プロジェクト内に保管済み：%1（次回反映時に差し替えます）")
                            .arg(root.viewModel.storedSourceName)
                          : qsTr("反映した回答原本は.jukuschedule内に保管され、元ファイルを移動しても失われません。")
                    color: root.viewModel.storedSourceName ? "#176b40" : "#667085"
                    font.pixelSize: 9
                    wrapMode: Text.Wrap
                }

                AppButton {
                    text: root.mappingExpanded
                          ? qsTr("列マッピングを閉じる")
                          : qsTr("列名が合わない場合の設定")
                    enabled: Boolean(root.viewModel.sourcePath)
                    onClicked: root.mappingExpanded = !root.mappingExpanded
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            Rectangle {
                visible: root.mappingExpanded
                SplitView.preferredWidth: visible ? 390 : 0
                SplitView.minimumWidth: visible ? 320 : 0
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 7

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 9
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("列マッピング")
                            color: "#344054"
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Label {
                            text: qsTr("* 必須")
                            color: "#a23b3b"
                            font.pixelSize: 9
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: mappingHelp.implicitHeight + 12
                        color: "#f5f8fc"
                        border.color: "#d9e1ec"
                        radius: 5

                        Label {
                            id: mappingHelp
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.margins: 7
                            text: qsTr("通常は自動判定されます。入力列名が異なる場合だけ、保存先の項目ごとに元の列を選択してください。")
                            color: "#52647d"
                            font.pixelSize: 9
                            wrapMode: Text.Wrap
                        }
                    }

                    ListView {
                        id: mappingList

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 4
                        model: root.viewModel.mappingRows || []
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: RowLayout {
                            id: mappingDelegate

                            required property var modelData
                            width: ListView.view.width
                            spacing: 7

                            Label {
                                Layout.preferredWidth: 142
                                text: root.rowValue(mappingDelegate.modelData, "label", "")
                                      + (root.rowValue(mappingDelegate.modelData,
                                                       "required", false) ? " *" : "")
                                color: root.rowValue(mappingDelegate.modelData,
                                                     "required", false)
                                       ? "#344054" : "#667085"
                                font.pixelSize: 9
                                elide: Text.ElideRight
                            }

                            ComboBox {
                                Layout.fillWidth: true
                                model: root.headerOptions()
                                currentIndex: root.headerIndex(
                                                  root.rowValue(
                                                      mappingDelegate.modelData,
                                                      "sourceHeader", ""))
                                Accessible.name: qsTr("%1の入力列")
                                                 .arg(root.rowValue(
                                                          mappingDelegate.modelData,
                                                          "label", ""))
                                onActivated: root.viewModel.setColumnMapping(
                                                 root.rowValue(
                                                     mappingDelegate.modelData,
                                                     "canonicalKey", ""),
                                                 currentIndex > 0 ? currentText : "")
                            }
                        }
                    }
                }
            }

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 420
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 7

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 9
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("先頭行プレビュー")
                            color: "#344054"
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Label {
                            text: qsTr("%1行").arg(previewList.count)
                            color: "#667085"
                            font.pixelSize: 9
                        }
                    }

                    ListView {
                        id: previewList

                        Layout.fillWidth: true
                        Layout.preferredHeight: 92
                        clip: true
                        spacing: 1
                        model: root.viewModel.sourcePreviewRows || []
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            id: previewDelegate

                            required property int index
                            required property var modelData
                            width: ListView.view.width
                            height: 27
                            color: index % 2 === 0 ? "#f8fafc" : "#ffffff"
                            border.color: "#edf0f4"

                            Label {
                                anchors.fill: parent
                                anchors.leftMargin: 7
                                anchors.rightMargin: 7
                                text: root.previewRowText(previewDelegate.modelData)
                                color: "#475467"
                                font.pixelSize: 8
                                elide: Text.ElideRight
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }

                    TabBar {
                        id: resultTabs
                        Layout.fillWidth: true

                        TabButton {
                            text: qsTr("差分（%1）")
                                  .arg((root.viewModel.importDiffs || []).length)
                        }
                        TabButton {
                            text: qsTr("エラー・警告（%1）")
                                  .arg((root.viewModel.importIssues || []).length)
                        }
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: resultTabs.currentIndex

                        Phase3DiffList {
                            rows: root.viewModel.importDiffs
                            emptyText: qsTr("検証すると、追加・変更・変更なし・削除候補を表示します。")
                        }

                        Phase3IssueList {
                            rows: root.viewModel.importIssues
                            emptyText: qsTr("検証エラー・警告はありません。")
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: [
                    {"label": qsTr("追加"), "key": "addCount"},
                    {"label": qsTr("変更"), "key": "changeCount"},
                    {"label": qsTr("変更なし"), "key": "unchangedCount"},
                    {"label": qsTr("削除候補"), "key": "deleteCandidateCount"},
                    {"label": qsTr("エラー"), "key": "errorCount"},
                    {"label": qsTr("警告"), "key": "warningCount"}
                ]

                delegate: Rectangle {
                    id: summaryDelegate

                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    radius: 6
                    color: root.rowValue(summaryDelegate.modelData, "key", "")
                           === "errorCount" && root.summaryValue("errorCount") > 0
                           ? "#fff6f5" : "#ffffff"
                    border.color: "#dce2ea"

                    Column {
                        anchors.centerIn: parent
                        spacing: 0
                        Label {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: root.rowValue(summaryDelegate.modelData, "label", "")
                            color: "#667085"
                            font.pixelSize: 8
                        }
                        Label {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: root.summaryValue(
                                      root.rowValue(summaryDelegate.modelData, "key", ""))
                            color: "#344054"
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }

            CheckBox {
                id: includeDeletes

                visible: root.summaryValue("deleteCandidateCount") > 0
                text: qsTr("削除候補も反映")
                Accessible.description: qsTr("チェックした場合のみ既存データの削除候補を反映します")
            }

            AppButton {
                text: qsTr("検証済み差分を反映…")
                kind: "primary"
                enabled: root.viewModel.canApplyImport
                ToolTip.visible: hovered && !enabled
                ToolTip.text: qsTr("エラーがある場合は反映できません。")
                onClicked: applyConfirmation.open()
            }
        }
    }

    Dialogs.FileDialog {
        id: combinedStudentDialog
        title: qsTr("生徒アンケート回答を選択")
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: [qsTr("対応ファイル (*.xlsx *.csv)")]
        onAccepted: root.viewModel.setCombinedStudentSource(selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: combinedTeacherDialog
        title: qsTr("講師アンケート回答を選択")
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: [qsTr("対応ファイル (*.xlsx *.csv)")]
        onAccepted: root.viewModel.setCombinedTeacherSource(selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: combinedExportDialog
        title: qsTr("統合アンケートを保存")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("Excelブック (*.xlsx)")]
        onAccepted: root.viewModel.exportCombinedSurvey(selectedFile.toString())
    }

    Dialogs.MessageDialog {
        id: combinedApplyConfirmation
        title: qsTr("2つの回答をまとめて反映")
        text: qsTr("検証済みの生徒回答・講師回答を現在の講習へ反映しますか？")
        informativeText: qsTr("回答原本と赤・黄の確認結果を含む統合xlsxは、.jukuschedule内へ保存されます。体験生以外の赤いエラーがある場合は反映できません。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.applyCombinedSurvey()
        }
    }

    Dialogs.FileDialog {
        id: sourceDialog
        title: qsTr("アンケート回答を選択")
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: [
            qsTr("対応ファイル (*.xlsx *.csv)"),
            qsTr("Excelブック (*.xlsx)"),
            qsTr("CSVファイル (*.csv)")
        ]
        onAccepted: {
            includeDeletes.checked = false
            root.viewModel.inspectAvailabilitySource(
                        selectedFile.toString(), encodingBox.currentValue)
        }
    }

    GoogleFormsGuideDialog {
        id: googleFormsGuideDialog
    }

    Dialogs.FolderDialog {
        id: questionnaireFolderDialog
        title: qsTr("Googleフォーム作成キットの保存先")
        currentFolder: root.viewModel.defaultQuestionnaireDirectoryUrl
        onAccepted: root.viewModel.exportGoogleFormsScripts(
                        selectedFolder.toString(),
                        studentFormTitle.text,
                        teacherFormTitle.text,
                        questionnaireDeadline.text,
                        questionnaireContact.text)
    }

    Dialogs.FileDialog {
        id: templateDialog
        title: qsTr("アンケートテンプレートを保存")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("Excelブック (*.xlsx)")]
        onAccepted: {
            if (root.viewModel.importKind === "teacher")
                root.viewModel.exportTeacherTemplate(selectedFile.toString())
            else
                root.viewModel.exportStudentTemplate(selectedFile.toString())
        }
    }

    Dialogs.MessageDialog {
        id: applyConfirmation
        title: qsTr("アンケート差分を反映")
        text: includeDeletes.checked
              ? qsTr("追加・変更に加えて、削除候補も反映しますか？")
              : qsTr("追加・変更を反映しますか？")
        informativeText: includeDeletes.checked
                         ? qsTr("削除候補%1件は明示的な選択により削除されます。処理全体は1トランザクションで保存されます。")
                           .arg(root.summaryValue("deleteCandidateCount"))
                         : qsTr("削除候補は反映せず保持します。処理全体は1トランザクションで保存されます。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.applyAvailabilityImport(includeDeletes.checked)
        }
    }
}
