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
    signal openSettingsRequested

    UiTheme { id: theme }

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
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

    readonly property int configuredOpenDateCount: countOpenDates()
    readonly property int configuredTimeSlotCount: countEnabledTimeSlots()

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
            description: qsTr("フォームの日付・コマはプロジェクト設定から作ります。先にホームからプロジェクトを開いてください。")
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
                        text: qsTr("アンケート作成")
                        color: theme.textPrimary
                        font.pixelSize: theme.titleSize
                        font.weight: Font.Bold
                    }
                    Label {
                        text: qsTr("設定済みの開校日・コマから、生徒用と講師用のGoogleフォーム作成キットを生成します。")
                        color: theme.textSecondary
                        font.pixelSize: theme.captionSize
                    }
                }

                StatusBadge {
                    status: root.configuredOpenDateCount > 0
                            && root.configuredTimeSlotCount > 0 ? "complete" : "warning"
                    symbol: root.configuredOpenDateCount > 0
                            && root.configuredTimeSlotCount > 0 ? "✓" : "!"
                    label: qsTr("開校日 %1日／有効コマ %2件")
                           .arg(root.configuredOpenDateCount)
                           .arg(root.configuredTimeSlotCount)
                }
            }

            InlineMessage {
                Layout.fillWidth: true
                kind: root.configuredOpenDateCount > 0
                      && root.configuredTimeSlotCount > 0 ? "info" : "warning"
                message: root.configuredOpenDateCount > 0
                         && root.configuredTimeSlotCount > 0
                         ? qsTr("フォームでは、生徒・講師とも『参加／出勤できない日時』を同じ日付×コマ表で回答できます。生徒用には学年別科目、回数、特記事項、学力テストも含まれます。")
                         : qsTr("先に①基本設定で開校日と有効コマを設定してください。設定内容がそのままフォームへ反映されます。")
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: formContent.implicitHeight + 32
                radius: 10
                color: "#ffffff"
                border.color: "#cfd9e8"

                ColumnLayout {
                    id: formContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 16
                    spacing: 12

                    SectionHeader {
                        Layout.fillWidth: true
                        title: qsTr("フォームの表示内容")
                        description: qsTr("名称と締切だけ確認すれば、質問・科目・日時表はアプリが自動構成します。")
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 16
                        rowSpacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("生徒用フォーム名（必須）"); color: "#344054" }
                            TextField {
                                id: studentFormTitle
                                Layout.fillWidth: true
                                text: qsTr("%1 個別指導受講申込")
                                      .arg(root.workspace.currentProjectTitle || qsTr("講習"))
                                Accessible.name: qsTr("生徒用Googleフォーム名")
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("講師用フォーム名（必須）"); color: "#344054" }
                            TextField {
                                id: teacherFormTitle
                                Layout.fillWidth: true
                                text: qsTr("%1 非常勤勤務アンケート")
                                      .arg(root.workspace.currentProjectTitle || qsTr("講習"))
                                Accessible.name: qsTr("講師用Googleフォーム名")
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("回答締切（必須）"); color: "#344054" }
                            TextField {
                                id: questionnaireDeadline
                                Layout.fillWidth: true
                                placeholderText: qsTr("例：2026年6月25日（木）")
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: qsTr("問い合わせ先（必須）"); color: "#344054" }
                            TextField {
                                id: questionnaireContact
                                Layout.fillWidth: true
                                text: qsTr("校舎へお問い合わせください")
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Label {
                            Layout.fillWidth: true
                            text: root.viewModel.lastQuestionnaireScriptDirectory
                                  ? qsTr("保存済み：%1").arg(root.viewModel.lastQuestionnaireScriptDirectory)
                                  : qsTr("生徒用・講師勤務日時用・講師指導可能科目用の3つのApps Scriptと手順書を保存します。")
                            color: root.viewModel.lastQuestionnaireScriptDirectory
                                   ? "#176b40" : "#667085"
                            font.pixelSize: 10
                            elide: Text.ElideMiddle
                        }

                        AppButton {
                            visible: Boolean(root.viewModel.lastQuestionnaireScriptDirectory)
                            text: qsTr("保存先を開く")
                            onClicked: root.viewModel.openQuestionnaireScriptDirectory()
                        }
                        AppButton {
                            text: qsTr("画像つき手順")
                            onClicked: guideDialog.open()
                        }
                        AppButton {
                            text: qsTr("フォーム作成キットを保存…")
                            kind: "primary"
                            enabled: root.configuredOpenDateCount > 0
                                     && root.configuredTimeSlotCount > 0
                                     && studentFormTitle.text.trim().length > 0
                                     && teacherFormTitle.text.trim().length > 0
                                     && questionnaireDeadline.text.trim().length > 0
                                     && questionnaireContact.text.trim().length > 0
                            onClicked: questionnaireFolderDialog.open()
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: nextContent.implicitHeight + 26
                radius: 9
                color: "#f5f9ff"
                border.color: "#b9d4ee"

                RowLayout {
                    id: nextContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 13

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("作成したフォームを配布し、回答が集まったら③「回答取込み」で生徒回答と講師回答を選択します。")
                        color: "#344054"
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }

    GoogleFormsGuideDialog { id: guideDialog }

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
}
