pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts
import QtQuick.Pdf

Item {
    id: root

    required property var viewModel
    signal openHomeRequested

    function optionIndex(model, value) {
        for (let index = 0; index < model.length; ++index) {
            if (String(model[index].value) === String(value))
                return index
        }
        return 0
    }

    function outputNameFilters() {
        if (root.viewModel.outputFormat === "pdf")
            return [qsTr("PDF文書 (*.pdf)")]
        if (root.viewModel.outputFormat === "csv")
            return [qsTr("CSVファイル (*.csv)")]
        return [qsTr("Excelブック (*.xlsx)")]
    }

    Component.onCompleted: {
        if (root.viewModel.hasOpenProject)
            root.viewModel.refreshWorkspace()
    }

    Connections {
        target: root.viewModel

        function onOverwriteConfirmationRequested(fileName) {
            overwriteDialog.text = qsTr("「%1」は既に存在します。置き換えますか？").arg(fileName)
            overwriteDialog.open()
        }
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
            width: Math.min(parent.width - 48, 540)
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
                text: qsTr("時間割を出力するには、ホームからプロジェクトを開いてください。")
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
        anchors.margins: 16
        visible: root.viewModel.hasOpenProject
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Label {
                    text: qsTr("時間割・帳票の出力")
                    color: "#18212f"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                }
                Label {
                    text: qsTr("現在のDBを再検査し、Excel・PDF・CSVをローカルへ保存します。")
                    color: "#667085"
                    font.pixelSize: 10
                }
            }

            Label {
                text: root.viewModel.settingsDirty
                      ? qsTr("● 出力設定に未保存の変更")
                      : qsTr("✓ 出力設定を保存済み")
                color: root.viewModel.settingsDirty ? "#9a6700" : "#176b40"
                font.pixelSize: 10
                font.weight: Font.DemiBold
            }

            Button {
                text: qsTr("最新状態を再読込み")
                enabled: !root.viewModel.isBusy && !root.viewModel.settingsDirty
                onClicked: root.viewModel.refreshWorkspace()
            }
        }

        StatusBanner {
            Layout.fillWidth: true
            viewModel: root.viewModel
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: outputControls.implicitHeight + 18
            radius: 8
            color: "#ffffff"
            border.color: "#dce2ea"

            ColumnLayout {
                id: outputControls

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 7

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        text: qsTr("帳票")
                        color: "#344054"
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }
                    ComboBox {
                        id: reportBox

                        Layout.preferredWidth: 200
                        enabled: !root.viewModel.isBusy
                        model: root.viewModel.reportOptions
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: root.optionIndex(model, root.viewModel.reportKind)
                        onActivated: root.viewModel.setReportKind(String(currentValue))
                        Accessible.name: qsTr("出力する帳票")
                    }

                    Label {
                        text: qsTr("形式")
                        color: "#344054"
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }
                    ComboBox {
                        id: formatBox

                        Layout.preferredWidth: 170
                        enabled: !root.viewModel.isBusy
                        model: root.viewModel.formatOptions
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: root.optionIndex(model, root.viewModel.outputFormat)
                        onActivated: root.viewModel.setOutputFormat(String(currentValue))
                        Accessible.name: qsTr("出力ファイル形式")
                    }

                    Button {
                        text: qsTr("印刷プレビューを更新")
                        enabled: root.viewModel.canPreview
                        onClicked: root.viewModel.generatePreview()
                        ToolTip.visible: hovered && !enabled
                        ToolTip.text: root.viewModel.reportKind === "raw"
                                      ? qsTr("CSV生データはプレビュー対象外です。")
                                      : qsTr("生成中は操作できません。")
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    BusyIndicator {
                        visible: root.viewModel.isBusy
                        running: visible
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: 28
                        Accessible.name: root.viewModel.busyText
                    }
                    Label {
                        visible: root.viewModel.isBusy
                        text: root.viewModel.busyText
                        color: "#176b40"
                        font.pixelSize: 10
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        text: qsTr("保存先")
                        color: "#344054"
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }
                    TextField {
                        id: destinationField

                        Layout.fillWidth: true
                        enabled: !root.viewModel.isBusy
                        text: root.viewModel.destinationPath
                        selectByMouse: true
                        placeholderText: qsTr("保存するファイルを選択してください")
                        onEditingFinished: root.viewModel.setDestination(text)
                        Accessible.name: qsTr("出力ファイルの保存先")
                    }
                    Label {
                        visible: root.viewModel.destinationExists
                        text: qsTr("同名あり")
                        color: "#9a6700"
                        font.pixelSize: 9
                        font.weight: Font.DemiBold
                    }
                    Button {
                        text: qsTr("参照…")
                        enabled: !root.viewModel.isBusy
                        onClicked: saveDialog.open()
                    }
                    Button {
                        text: qsTr("ファイルを生成")
                        highlighted: true
                        enabled: root.viewModel.canGenerate
                        onClicked: {
                            destinationField.focus = false
                            root.viewModel.generateOutput(false)
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.viewModel.lastResultSummary.length > 0
                    text: qsTr("直近の出力: %1　%2")
                          .arg(root.viewModel.lastResultSummary)
                          .arg(root.viewModel.lastOutputPath)
                    color: "#475467"
                    font.pixelSize: 9
                    elide: Text.ElideMiddle
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            ScrollView {
                id: settingsPane

                SplitView.minimumWidth: 390
                SplitView.preferredWidth: 455
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                ColumnLayout {
                    width: settingsPane.availableWidth
                    spacing: 8

                    GroupBox {
                        Layout.fillWidth: true
                        title: qsTr("ページ・レイアウト")

                        GridLayout {
                            anchors.fill: parent
                            columns: 4
                            columnSpacing: 7
                            rowSpacing: 6

                            Label {
                                text: qsTr("用紙")
                                color: "#344054"
                            }
                            ComboBox {
                                Layout.fillWidth: true
                                enabled: !root.viewModel.isBusy
                                model: [
                                    {"label": "A3", "value": "A3"},
                                    {"label": "A4", "value": "A4"}
                                ]
                                textRole: "label"
                                valueRole: "value"
                                currentIndex: root.optionIndex(model, root.viewModel.paperSize)
                                onActivated: root.viewModel.setPaperSize(String(currentValue))
                            }
                            Label {
                                text: qsTr("向き")
                                color: "#344054"
                            }
                            ComboBox {
                                Layout.fillWidth: true
                                enabled: !root.viewModel.isBusy
                                model: [
                                    {"label": qsTr("横"), "value": "landscape"},
                                    {"label": qsTr("縦"), "value": "portrait"}
                                ]
                                textRole: "label"
                                valueRole: "value"
                                currentIndex: root.optionIndex(model, root.viewModel.orientation)
                                onActivated: root.viewModel.setOrientation(String(currentValue))
                            }

                            Label {
                                text: qsTr("日数/頁")
                                color: "#344054"
                            }
                            SpinBox {
                                from: 1
                                to: 7
                                value: root.viewModel.daysPerPage
                                editable: true
                                enabled: !root.viewModel.isBusy
                                onValueModified: root.viewModel.setDaysPerPage(value)
                                Accessible.name: qsTr("1ページ当たり日数")
                            }
                            Label {
                                text: qsTr("講師列/頁")
                                color: "#344054"
                            }
                            SpinBox {
                                from: 1
                                to: 20
                                value: root.viewModel.teacherColumnsPerPage
                                editable: true
                                enabled: !root.viewModel.isBusy
                                onValueModified: root.viewModel.setTeacherColumnsPerPage(value)
                                Accessible.name: qsTr("1ページ当たり講師列数")
                            }

                            Label {
                                text: qsTr("文字 pt")
                                color: "#344054"
                            }
                            SpinBox {
                                id: fontSizeBox

                                from: 50
                                to: 180
                                stepSize: 5
                                value: Math.round(root.viewModel.fontSize * 10)
                                editable: true
                                enabled: !root.viewModel.isBusy
                                textFromValue: function (value) {
                                    return (value / 10).toFixed(1)
                                }
                                valueFromText: function (text) {
                                    return Math.round(Number.fromLocaleString(locale, text) * 10)
                                }
                                onValueModified: root.viewModel.setFontSize(value / 10)
                                Accessible.name: qsTr("文字サイズ")
                            }
                            Label {
                                text: qsTr("余白 mm")
                                color: "#344054"
                            }
                            SpinBox {
                                id: marginBox

                                from: 0
                                to: 300
                                stepSize: 5
                                value: Math.round(root.viewModel.marginMm * 10)
                                editable: true
                                enabled: !root.viewModel.isBusy
                                textFromValue: function (value) {
                                    return (value / 10).toFixed(1)
                                }
                                valueFromText: function (text) {
                                    return Math.round(Number.fromLocaleString(locale, text) * 10)
                                }
                                onValueModified: root.viewModel.setMarginMm(value / 10)
                                Accessible.name: qsTr("ページ余白")
                            }
                        }
                    }

                    GroupBox {
                        Layout.fillWidth: true
                        title: qsTr("ファイル・帳票設定")

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 6

                            Label {
                                text: qsTr("ファイル名規則")
                                color: "#344054"
                            }
                            TextField {
                                Layout.fillWidth: true
                                enabled: !root.viewModel.isBusy
                                text: root.viewModel.fileNamePattern
                                placeholderText: qsTr("{project}_{report}_{date}")
                                onEditingFinished: root.viewModel.setFileNamePattern(text)
                                Accessible.name: qsTr("出力ファイル名規則")
                            }
                            Label {
                                Layout.fillWidth: true
                                text: qsTr("{project}、{report}、{date}を使用できます。")
                                color: "#667085"
                                font.pixelSize: 9
                                wrapMode: Text.Wrap
                            }

                            Label {
                                text: qsTr("校舎ロゴ（Campus正本）")
                                color: "#344054"
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                TextField {
                                    Layout.fillWidth: true
                                    enabled: !root.viewModel.isBusy
                                    text: root.viewModel.logoPath
                                    placeholderText: qsTr("PNG・JPEG・GIF・BMP")
                                    selectByMouse: true
                                    onEditingFinished: root.viewModel.setLogoPath(text)
                                    Accessible.name: qsTr("校舎ロゴ画像")
                                }
                                Button {
                                    text: qsTr("参照…")
                                    enabled: !root.viewModel.isBusy
                                    onClicked: logoDialog.open()
                                }
                                ToolButton {
                                    text: qsTr("解除")
                                    enabled: root.viewModel.logoPath.length > 0
                                             && !root.viewModel.isBusy
                                    onClicked: root.viewModel.setLogoPath("")
                                }
                            }

                            Label {
                                text: qsTr("既定出力先")
                                color: "#344054"
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                TextField {
                                    Layout.fillWidth: true
                                    enabled: !root.viewModel.isBusy
                                    text: root.viewModel.defaultOutputDirectory
                                    placeholderText: qsTr("未指定時はドキュメント")
                                    selectByMouse: true
                                    onEditingFinished: root.viewModel.setDefaultOutputDirectory(text)
                                    Accessible.name: qsTr("既定の出力先フォルダー")
                                }
                                Button {
                                    text: qsTr("参照…")
                                    enabled: !root.viewModel.isBusy
                                    onClicked: outputFolderDialog.open()
                                }
                                ToolButton {
                                    text: qsTr("解除")
                                    enabled: root.viewModel.defaultOutputDirectory.length > 0
                                             && !root.viewModel.isBusy
                                    onClicked: root.viewModel.setDefaultOutputDirectory("")
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    text: qsTr("生徒別")
                                    color: "#344054"
                                }
                                ComboBox {
                                    Layout.fillWidth: true
                                    enabled: !root.viewModel.isBusy
                                    model: [
                                        {"label": qsTr("1人1ページ"), "value": "one_per_page"},
                                        {"label": qsTr("複数人をまとめる"), "value": "combined"}
                                    ]
                                    textRole: "label"
                                    valueRole: "value"
                                    currentIndex: root.optionIndex(model, root.viewModel.studentPageMode)
                                    onActivated: root.viewModel.setStudentPageMode(String(currentValue))
                                }
                                CheckBox {
                                    text: qsTr("CSVにBOM")
                                    checked: root.viewModel.csvWithBom
                                    enabled: !root.viewModel.isBusy
                                    onToggled: root.viewModel.setCsvWithBom(checked)
                                }
                            }
                        }
                    }

                    GroupBox {
                        Layout.fillWidth: true
                        title: qsTr("表示項目")

                        GridLayout {
                            anchors.fill: parent
                            columns: 2
                            columnSpacing: 8
                            rowSpacing: 2

                            Repeater {
                                model: root.viewModel.visibleFieldOptions

                                delegate: CheckBox {
                                    required property var modelData

                                    Layout.fillWidth: true
                                    text: String(modelData.label)
                                    checked: Boolean(modelData.selected)
                                    enabled: !root.viewModel.isBusy
                                    onToggled: root.viewModel.setVisibleField(
                                                   String(modelData.value), checked)
                                }
                            }
                        }
                    }

                    GroupBox {
                        Layout.fillWidth: true
                        title: qsTr("色・マーカー（モノクロ識別対応）")

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 5

                            Label {
                                Layout.fillWidth: true
                                text: qsTr("色だけに依存せず、各状態の文字マーカーも必ず出力します。色は#RRGGBB形式です。")
                                color: "#667085"
                                font.pixelSize: 9
                                wrapMode: Text.Wrap
                            }

                            Repeater {
                                model: root.viewModel.styleRules

                                delegate: Rectangle {
                                    id: styleDelegate

                                    required property var modelData

                                    Layout.fillWidth: true
                                    implicitHeight: styleRow.implicitHeight + 8
                                    radius: 4
                                    color: "#f8fafc"
                                    border.color: "#e2e8f0"

                                    function applyRule() {
                                        root.viewModel.setStyleRule(
                                                    String(styleDelegate.modelData.code),
                                                    markerField.text,
                                                    fillField.text,
                                                    textField.text)
                                    }

                                    RowLayout {
                                        id: styleRow

                                        anchors.fill: parent
                                        anchors.margins: 4
                                        spacing: 5

                                        Rectangle {
                                            Layout.preferredWidth: 22
                                            Layout.preferredHeight: 22
                                            radius: 3
                                            color: String(styleDelegate.modelData.fillColor)
                                            border.color: "#98a2b3"
                                        }
                                        Label {
                                            Layout.preferredWidth: 70
                                            text: String(styleDelegate.modelData.label)
                                            color: "#344054"
                                            font.pixelSize: 9
                                            elide: Text.ElideRight
                                        }
                                        TextField {
                                            id: markerField

                                            Layout.fillWidth: true
                                            text: String(styleDelegate.modelData.marker)
                                            enabled: !root.viewModel.isBusy
                                            placeholderText: qsTr("記号")
                                            onEditingFinished: styleDelegate.applyRule()
                                            Accessible.name: qsTr("%1の文字マーカー").arg(styleDelegate.modelData.label)
                                        }
                                        TextField {
                                            id: fillField

                                            Layout.preferredWidth: 80
                                            text: String(styleDelegate.modelData.fillColor)
                                            enabled: !root.viewModel.isBusy
                                            onEditingFinished: styleDelegate.applyRule()
                                            Accessible.name: qsTr("%1の背景色").arg(styleDelegate.modelData.label)
                                        }
                                        TextField {
                                            id: textField

                                            Layout.preferredWidth: 80
                                            text: String(styleDelegate.modelData.textColor)
                                            enabled: !root.viewModel.isBusy
                                            onEditingFinished: styleDelegate.applyRule()
                                            Accessible.name: qsTr("%1の文字色").arg(styleDelegate.modelData.label)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    GroupBox {
                        Layout.fillWidth: true
                        title: qsTr("出力対象")

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 7

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("日付")
                                    color: "#344054"
                                    font.weight: Font.DemiBold
                                }
                                ToolButton {
                                    text: qsTr("すべて選択")
                                    enabled: !root.viewModel.isBusy
                                    onClicked: root.viewModel.selectAllDates()
                                }
                            }
                            ListView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.min(130, contentHeight)
                                clip: true
                                model: root.viewModel.dateOptions

                                delegate: CheckDelegate {
                                    required property var modelData

                                    width: ListView.view.width
                                    text: String(modelData.label)
                                    checked: Boolean(modelData.selected)
                                    enabled: !root.viewModel.isBusy
                                    onToggled: root.viewModel.setDateSelected(
                                                   String(modelData.value), checked)
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("講師")
                                    color: "#344054"
                                    font.weight: Font.DemiBold
                                }
                                ToolButton {
                                    text: qsTr("すべて選択")
                                    enabled: !root.viewModel.isBusy
                                    onClicked: root.viewModel.selectAllTeachers()
                                }
                            }
                            ListView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.min(145, contentHeight)
                                clip: true
                                model: root.viewModel.teacherOptions

                                delegate: CheckDelegate {
                                    required property var modelData

                                    width: ListView.view.width
                                    text: qsTr("%1　%2")
                                          .arg(modelData.label)
                                          .arg(modelData.secondaryText)
                                    checked: Boolean(modelData.selected)
                                    enabled: !root.viewModel.isBusy
                                    onToggled: root.viewModel.setTeacherSelected(
                                                   Number(modelData.id), checked)
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("生徒")
                                    color: "#344054"
                                    font.weight: Font.DemiBold
                                }
                                ToolButton {
                                    text: qsTr("すべて選択")
                                    enabled: !root.viewModel.isBusy
                                    onClicked: root.viewModel.selectAllStudents()
                                }
                            }
                            ListView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.min(160, contentHeight)
                                clip: true
                                model: root.viewModel.studentOptions

                                delegate: CheckDelegate {
                                    required property var modelData

                                    width: ListView.view.width
                                    text: qsTr("%1　%2")
                                          .arg(modelData.label)
                                          .arg(modelData.secondaryText)
                                    checked: Boolean(modelData.selected)
                                    enabled: !root.viewModel.isBusy
                                    onToggled: root.viewModel.setStudentSelected(
                                                   Number(modelData.id), checked)
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.bottomMargin: 8

                        Button {
                            text: qsTr("元に戻す")
                            enabled: root.viewModel.settingsDirty && !root.viewModel.isBusy
                            onClicked: root.viewModel.resetSettings()
                        }
                        Item {
                            Layout.fillWidth: true
                        }
                        Button {
                            text: qsTr("出力設定を保存")
                            highlighted: true
                            enabled: root.viewModel.settingsDirty && !root.viewModel.isBusy
                            onClicked: root.viewModel.saveSettings()
                        }
                    }
                }
            }

            Rectangle {
                id: previewPane

                SplitView.minimumWidth: 420
                SplitView.fillWidth: true
                color: "#e6e9ee"
                border.color: "#cfd6df"

                PdfDocument {
                    id: previewDocument
                    source: root.viewModel.previewUrl
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    ToolBar {
                        Layout.fillWidth: true

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            spacing: 5

                            ToolButton {
                                text: qsTr("‹")
                                enabled: root.viewModel.hasPreview && pdfView.currentPage > 0
                                Accessible.name: qsTr("前のPDFページ")
                                onClicked: pdfView.goToPage(pdfView.currentPage - 1)
                            }
                            Label {
                                text: root.viewModel.hasPreview
                                      ? qsTr("%1 / %2頁")
                                        .arg(Math.max(1, pdfView.currentPage + 1))
                                        .arg(previewDocument.pageCount)
                                      : qsTr("プレビューなし")
                                color: "#344054"
                                font.pixelSize: 10
                            }
                            ToolButton {
                                text: qsTr("›")
                                enabled: root.viewModel.hasPreview
                                         && pdfView.currentPage + 1 < previewDocument.pageCount
                                Accessible.name: qsTr("次のPDFページ")
                                onClicked: pdfView.goToPage(pdfView.currentPage + 1)
                            }
                            ToolSeparator {}
                            Label {
                                text: qsTr("倍率")
                                color: "#344054"
                                font.pixelSize: 10
                            }
                            Slider {
                                id: zoomSlider

                                Layout.preferredWidth: 135
                                from: 0.5
                                to: 3.0
                                stepSize: 0.1
                                value: 1.0
                                enabled: root.viewModel.hasPreview
                                onMoved: pdfView.renderScale = value
                                Accessible.name: qsTr("PDFプレビューの拡大率")
                            }
                            Label {
                                text: qsTr("%1%").arg(Math.round(zoomSlider.value * 100))
                                color: "#344054"
                                font.pixelSize: 10
                            }
                            ToolButton {
                                text: qsTr("幅に合わせる")
                                enabled: root.viewModel.hasPreview
                                onClicked: {
                                    pdfView.scaleToWidth(pdfView.width, pdfView.height)
                                    zoomSlider.value = pdfView.renderScale
                                }
                            }
                            ToolButton {
                                text: qsTr("全体表示")
                                enabled: root.viewModel.hasPreview
                                onClicked: {
                                    pdfView.scaleToPage(pdfView.width, pdfView.height)
                                    zoomSlider.value = pdfView.renderScale
                                }
                            }
                            Item {
                                Layout.fillWidth: true
                            }
                            Label {
                                text: qsTr("%1 %2／%3日・%4講師列")
                                      .arg(root.viewModel.paperSize)
                                      .arg(root.viewModel.orientation === "landscape"
                                           ? qsTr("横") : qsTr("縦"))
                                      .arg(root.viewModel.daysPerPage)
                                      .arg(root.viewModel.teacherColumnsPerPage)
                                color: "#667085"
                                font.pixelSize: 9
                            }
                            ToolButton {
                                text: qsTr("閉じる")
                                enabled: root.viewModel.hasPreview
                                onClicked: root.viewModel.clearPreview()
                            }
                        }
                    }

                    PdfMultiPageView {
                        id: pdfView

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: root.viewModel.hasPreview
                        document: previewDocument
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: !root.viewModel.hasPreview
                        spacing: 8

                        Item {
                            Layout.fillHeight: true
                        }
                        Label {
                            Layout.alignment: Qt.AlignHCenter
                            text: root.viewModel.isBusy
                                  ? qsTr("プレビューを生成しています…")
                                  : qsTr("「印刷プレビューを更新」で一時PDFを表示します")
                            color: "#475467"
                            font.pixelSize: 13
                        }
                        Label {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.maximumWidth: previewPane.width - 60
                            text: qsTr("一時PDFはアプリ終了時に削除され、プロジェクトDBには保存されません。")
                            color: "#667085"
                            font.pixelSize: 10
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Item {
                            Layout.fillHeight: true
                        }
                    }
                }
            }
        }
    }

    Dialogs.FileDialog {
        id: saveDialog

        title: qsTr("出力ファイルの保存先を選択")
        fileMode: Dialogs.FileDialog.SaveFile
        selectedFile: root.viewModel.destinationUrl
        nameFilters: root.outputNameFilters()
        defaultSuffix: root.viewModel.outputFormat
        onAccepted: root.viewModel.setDestination(selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: logoDialog

        title: qsTr("校舎ロゴを選択")
        fileMode: Dialogs.FileDialog.OpenFile
        selectedFile: root.viewModel.logoUrl
        nameFilters: [
            qsTr("画像ファイル (*.png *.jpg *.jpeg *.gif *.bmp)")
        ]
        onAccepted: root.viewModel.setLogoPath(selectedFile.toString())
    }

    Dialogs.FolderDialog {
        id: outputFolderDialog

        title: qsTr("既定の出力先フォルダーを選択")
        selectedFolder: root.viewModel.defaultOutputDirectoryUrl
        onAccepted: root.viewModel.setDefaultOutputDirectory(selectedFolder.toString())
    }

    Dialogs.MessageDialog {
        id: overwriteDialog

        title: qsTr("同名ファイルの上書き確認")
        informativeText: qsTr("元のファイルは、生成が正常に完了した後に置き換えられます。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.generateOutput(true)
            else
                root.viewModel.cancelOverwriteConfirmation()
        }
    }
}
