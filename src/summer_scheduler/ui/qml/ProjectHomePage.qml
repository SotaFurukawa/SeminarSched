pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs as Dialogs
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    property var phase3ViewModel: null
    property var scheduleViewModel: null
    property var outputViewModel: null
    signal openSettingsRequested
    signal navigateRequested(int pageIndex)
    property string pendingSwitchAction: ""
    property string pendingRecentPath: ""
    property string pendingRestorePath: ""

    UiTheme { id: theme }

    readonly property bool basicSetupComplete: collectionCount(viewModel.openDates) > 0
                                                   && collectionCount(viewModel.timeSlots) > 0
                                                   && collectionCount(viewModel.students) > 0
                                                   && collectionCount(viewModel.teachers) > 0
    readonly property bool questionnaireComplete: phase3ViewModel
                                                   && Boolean(rowValue(
                                                                  phase3ViewModel.validationSummary,
                                                                  "canOptimize", false))
    readonly property bool scheduleComplete: outputViewModel
                                              && Number(outputViewModel.assignmentCount || 0) > 0
    readonly property bool outputComplete: outputViewModel
                                            && String(outputViewModel.lastOutputPath || "").length > 0

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function collectionCount(rows) {
        return rows && rows.length !== undefined ? rows.length : 0
    }

    function nextStepNumber() {
        if (!root.basicSetupComplete)
            return 1
        if (!root.questionnaireComplete)
            return 2
        if (!root.scheduleComplete)
            return 3
        return 4
    }

    function stepStatus(step) {
        const complete = step === 1 ? root.basicSetupComplete
                       : step === 2 ? root.questionnaireComplete
                       : step === 3 ? root.scheduleComplete
                       : root.outputComplete
        if (complete)
            return "complete"
        return step === root.nextStepNumber() ? "current" : "pending"
    }

    function stepStatusText(step) {
        if (root.stepStatus(step) === "complete")
            return qsTr("完了")
        if (root.stepStatus(step) === "current")
            return qsTr("次に行う")
        return qsTr("未着手")
    }

    function openNewProjectDialog() {
        newProjectTitle.text = ""
        newProjectStart.text = ""
        newProjectEnd.text = ""
        newProjectValidation.visible = false
        newProjectDialog.open()
    }

    function requestProjectSwitch(action, path) {
        if (root.viewModel.isDirty) {
            root.pendingSwitchAction = action
            root.pendingRecentPath = path || ""
            switchDirtyDialog.open()
            return
        }
        root.executeProjectSwitch(action, path || "")
    }

    function executeProjectSwitch(action, path) {
        if (action === "new")
            root.openNewProjectDialog()
        else if (action === "open")
            openProjectDialog.open()
        else if (action === "recent")
            root.viewModel.openRecent(path)
    }

    ScrollView {
        id: homeScroll

        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        Item {
            width: homeScroll.availableWidth
            height: Math.max(homeScroll.availableHeight, homeContent.implicitHeight + 48)

            ColumnLayout {
                id: homeContent

                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 24
                spacing: 16

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Label {
                            text: qsTr("ホーム")
                            color: theme.textPrimary
                            font.pixelSize: theme.titleSize
                            font.weight: Font.Bold
                        }

                        Label {
                            text: root.viewModel.hasOpenProject
                                  ? qsTr("時間割完成までの進み具合と、次に行う作業")
                                  : qsTr("作業するプロジェクトを選択してください")
                            color: "#667085"
                            font.pixelSize: 12
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: phaseText.implicitWidth + 20
                        Layout.preferredHeight: 28
                        radius: 14
                        color: theme.accentSoft
                        border.color: "#B2D7F0"

                        Label {
                            id: phaseText

                            anchors.centerIn: parent
                            text: qsTr("4ステップで完成")
                            color: theme.accent
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: sharedRosterContent.implicitHeight + 30
                    radius: 12
                    color: "#f5f9ff"
                    border.color: "#b9d4ee"

                    ColumnLayout {
                        id: sharedRosterContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 18
                        anchors.rightMargin: 18
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Label {
                                    text: qsTr("生徒・講師の基本情報（共通）")
                                    color: "#183b59"
                                    font.pixelSize: 16
                                    font.weight: Font.DemiBold
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("講習ごとに作り直さない在籍情報・指導可能科目・通常授業の担当を、1つのExcelで管理します。")
                                    color: "#52647d"
                                    font.pixelSize: 11
                                    wrapMode: Text.Wrap
                                }
                            }

                            AppButton {
                                text: qsTr("Excelを開いて編集")
                                kind: "primary"
                                onClicked: root.viewModel.openSharedRoster()
                            }

                            AppButton {
                                visible: root.viewModel.hasOpenProject
                                text: qsTr("この講習へ反映")
                                onClicked: root.viewModel.applySharedRoster()
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("保存先: %1").arg(root.viewModel.sharedRosterPath)
                            color: "#667085"
                            font.pixelSize: 9
                            elide: Text.ElideMiddle
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("在籍のチェックを外した人は削除せず退籍扱いとなり、Excelでは灰色で表示されます。Excelを保存してから「この講習へ反映」を押してください。")
                            color: "#52647d"
                            font.pixelSize: 10
                            wrapMode: Text.Wrap
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: !root.viewModel.hasOpenProject
                    implicitHeight: startContent.implicitHeight + 34
                    radius: 12
                    color: "#ffffff"
                    border.color: "#dce2ea"

                    ColumnLayout {
                        id: startContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 20
                        anchors.rightMargin: 20
                        spacing: 12

                        Label {
                            text: qsTr("プロジェクトを開始")
                            color: "#18212f"
                            font.pixelSize: 17
                            font.weight: Font.DemiBold
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr(".jukuscheduleファイルには、講習期間・生徒・講師・科目・アンケート原本などが保存されます。")
                            color: "#667085"
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }

                        RowLayout {
                            spacing: 10

                            AppButton {
                                text: qsTr("＋ 新規プロジェクト")
                                kind: "primary"
                                onClicked: root.requestProjectSwitch("new", "")
                            }

                            AppButton {
                                text: qsTr("既存プロジェクトを開く…")
                                onClicked: root.requestProjectSwitch("open", "")
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: root.viewModel.hasOpenProject
                    implicitHeight: projectContent.implicitHeight + 32
                    radius: 12
                    color: "#ffffff"
                    border.color: "#dce2ea"

                    ColumnLayout {
                        id: projectContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 20
                        anchors.rightMargin: 20
                        spacing: 12

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Label {
                                    text: root.viewModel.currentProjectTitle || qsTr("名称未設定")
                                    color: "#18212f"
                                    font.pixelSize: 18
                                    font.weight: Font.DemiBold
                                }

                                Label {
                                    text: qsTr("%1 ～ %2")
                                          .arg(root.viewModel.currentStartDate || "----/--/--")
                                          .arg(root.viewModel.currentEndDate || "----/--/--")
                                    color: "#667085"
                                    font.pixelSize: 11
                                }
                            }

                            Label {
                                text: root.viewModel.isDirty ? qsTr("● 未保存の変更があります") : qsTr("✓ すべて保存されています")
                                color: root.viewModel.isDirty ? "#7a5710" : "#176b40"
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                            }
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 8

                            Button {
                                text: qsTr("設定を編集")
                                highlighted: true
                                onClicked: root.openSettingsRequested()
                            }

                            Button {
                                text: qsTr("名前を付けて保存…")
                                onClicked: saveAsDialog.open()
                            }

                            Button {
                                text: qsTr("複製…")
                                onClicked: duplicateDialog.open()
                            }

                            Button {
                                text: qsTr("バックアップ…")
                                onClicked: backupDialog.open()
                            }

                            Button {
                                text: qsTr("別のファイルを開く…")
                                onClicked: root.requestProjectSwitch("open", "")
                            }

                            Button {
                                text: qsTr("閉じる")
                                onClicked: {
                                    if (root.viewModel.isDirty)
                                        closeDirtyDialog.open()
                                    else
                                        root.viewModel.closeProject(false)
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: root.viewModel.recoveryTargetPath.length > 0
                    implicitHeight: recoveryContent.implicitHeight + 32
                    radius: 12
                    color: "#fffaf0"
                    border.color: "#e6c777"

                    ColumnLayout {
                        id: recoveryContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 20
                        anchors.rightMargin: 20
                        spacing: 9

                        Label {
                            Layout.fillWidth: true
                            text: root.viewModel.hasOpenProject
                                  ? qsTr("バックアップとデータ整合性")
                                  : qsTr("前回正常終了を確認できないプロジェクトがあります")
                            color: "#5f4300"
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }

                        Label {
                            Layout.fillWidth: true
                            text: root.viewModel.recoveryTargetPath
                            color: "#6f5a24"
                            font.pixelSize: 10
                            elide: Text.ElideMiddle
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("バックアップにも、生徒名・講師名・希望日時などの個人情報が含まれます。取扱いと保存先に注意してください。")
                            color: "#7a5710"
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 8

                            Button {
                                visible: root.viewModel.hasOpenProject
                                text: qsTr("DB整合性を確認")
                                onClicked: root.viewModel.checkCurrentProjectIntegrity()
                            }

                            Button {
                                text: qsTr("別のバックアップを選んで復元…")
                                onClicked: restoreBackupDialog.open()
                            }

                            Button {
                                text: qsTr("候補を再確認")
                                onClicked: root.viewModel.refreshRecoveryCandidates()
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: recoveryList.count === 0
                            text: qsTr("このプロジェクトに紐づく自動バックアップは見つかりません。")
                            color: "#7a6a42"
                            font.pixelSize: 11
                        }

                        ListView {
                            id: recoveryList

                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.min(contentHeight, 190)
                            visible: count > 0
                            clip: true
                            spacing: 6
                            boundsBehavior: Flickable.StopAtBounds
                            model: root.viewModel.recoveryCandidates

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }

                            delegate: Rectangle {
                                id: recoveryDelegate

                                required property var modelData
                                width: ListView.view.width
                                height: 62
                                radius: 7
                                color: "#ffffff"
                                border.color: root.rowValue(
                                                  recoveryDelegate.modelData,
                                                  "isValid",
                                                  false) ? "#d8c38b" : "#d9a0a0"

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 8
                                    spacing: 10

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2

                                        Label {
                                            Layout.fillWidth: true
                                            text: qsTr("%1　%2")
                                                  .arg(root.rowValue(
                                                           recoveryDelegate.modelData,
                                                           "kindLabel",
                                                           qsTr("バックアップ")))
                                                  .arg(root.rowValue(
                                                           recoveryDelegate.modelData,
                                                           "createdAt",
                                                           ""))
                                            color: "#4b3b14"
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                        }

                                        Label {
                                            Layout.fillWidth: true
                                            text: root.rowValue(
                                                      recoveryDelegate.modelData,
                                                      "integrityMessage",
                                                      "")
                                            color: root.rowValue(
                                                       recoveryDelegate.modelData,
                                                       "isValid",
                                                       false) ? "#52624c" : "#a23b3b"
                                            font.pixelSize: 10
                                            elide: Text.ElideRight
                                        }
                                    }

                                    Button {
                                        text: qsTr("復元")
                                        enabled: root.rowValue(
                                                     recoveryDelegate.modelData,
                                                     "isValid",
                                                     false)
                                        onClicked: {
                                            root.pendingRestorePath = root.rowValue(
                                                        recoveryDelegate.modelData,
                                                        "path",
                                                        "")
                                            restoreConfirmDialog.open()
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: root.viewModel.hasOpenProject
                    implicitHeight: workflowContent.implicitHeight + 32
                    radius: 12
                    color: "#ffffff"
                    border.color: "#cfd9e8"

                    ColumnLayout {
                        id: workflowContent
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 18
                        anchors.rightMargin: 18
                        spacing: 12

                        Label {
                            text: qsTr("時間割完成までの4ステップ")
                            color: "#18212f"
                            font.pixelSize: 17
                            font.weight: Font.DemiBold
                        }
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("上から順に進めれば、必要な作業を迷わず完了できます。")
                            color: "#667085"
                            font.pixelSize: 10
                        }

                        InlineMessage {
                            Layout.fillWidth: true
                            kind: root.nextStepNumber() === 4 && root.scheduleComplete
                                  ? "success" : "info"
                            message: root.nextStepNumber() === 1
                                     ? qsTr("次に行うこと：共通名簿を確認し、授業日・コマをまとめて設定します。")
                                     : root.nextStepNumber() === 2
                                       ? qsTr("次に行うこと：生徒・講師アンケートを取り込み、入力を検証します。")
                                       : root.nextStepNumber() === 3
                                         ? qsTr("次に行うこと：入力を確認して自動配置し、時間割を調整します。")
                                         : qsTr("次に行うこと：全体・生徒別・講師別の時間割を確認して出力します。")
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: width >= 900 ? 4 : 2
                            columnSpacing: 10
                            rowSpacing: 10

                            Repeater {
                                model: [
                                    {"number": "1", "title": qsTr("授業日を決める"),
                                     "detail": qsTr("講習期間・開校日・コマ"),
                                     "button": qsTr("授業日を設定"), "page": 8},
                                    {"number": "2", "title": qsTr("アンケートを取込む"),
                                     "detail": qsTr("生徒・講師の回答を検証"),
                                     "button": qsTr("アンケート取込み"), "page": 4},
                                    {"number": "3", "title": qsTr("時間割を配置する"),
                                     "detail": qsTr("集団授業確認・自動配置・編集"),
                                     "button": qsTr("時間割を作成"), "page": 5},
                                    {"number": "4", "title": qsTr("個人時間割を作る"),
                                     "detail": qsTr("生徒別Excel・PDFを出力"),
                                     "button": qsTr("出力へ進む"), "page": 7}
                                ]

                                delegate: StepCard {
                                    id: workflowStep
                                    required property var modelData
                                    Layout.fillWidth: true
                                    stepNumber: String(modelData.number)
                                    title: String(modelData.title)
                                    description: String(modelData.detail)
                                    actionText: String(modelData.button)
                                    status: root.stepStatus(Number(modelData.number))
                                    statusText: root.stepStatusText(Number(modelData.number))
                                    primaryAction: Number(modelData.number) === root.nextStepNumber()
                                    onActionRequested: root.navigateRequested(
                                                           Number(modelData.page))
                                }
                            }
                        }
                    }
                }

                GridLayout {
                    Layout.fillWidth: true
                    visible: root.viewModel.hasOpenProject
                    columns: width >= 900 ? 4 : 2
                    columnSpacing: 12
                    rowSpacing: 12

                    DashboardCard {
                        Layout.fillWidth: true
                        cardTitle: qsTr("生徒")
                        value: String(root.collectionCount(root.viewModel.students))
                        markerText: qsTr("登録済み")
                        description: qsTr("受講希望は生徒画面で編集")
                    }

                    DashboardCard {
                        Layout.fillWidth: true
                        cardTitle: qsTr("講師")
                        value: String(root.collectionCount(root.viewModel.teachers))
                        markerText: qsTr("登録済み")
                        description: qsTr("指導可能科目を設定できます")
                    }

                    DashboardCard {
                        Layout.fillWidth: true
                        cardTitle: qsTr("科目")
                        value: String(root.collectionCount(root.viewModel.subjects))
                        markerText: qsTr("マスター")
                        description: qsTr("小・中・高の科目区分")
                    }

                    DashboardCard {
                        Layout.fillWidth: true
                        cardTitle: qsTr("受講希望")
                        value: String(root.collectionCount(root.viewModel.lessonRequests))
                        markerText: qsTr("登録済み")
                        description: qsTr("生徒×科目単位")
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: recentContent.implicitHeight + 30
                    radius: 12
                    color: "#ffffff"
                    border.color: "#dce2ea"

                    ColumnLayout {
                        id: recentContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 20
                        anchors.rightMargin: 20
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true

                            Label {
                                Layout.fillWidth: true
                                text: qsTr("最近使用したプロジェクト")
                                color: "#344054"
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }

                            Button {
                                text: qsTr("新規作成")
                                flat: true
                                onClicked: root.requestProjectSwitch("new", "")
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: recentList.count === 0
                            text: qsTr("最近使用したプロジェクトはありません。")
                            color: "#7a8493"
                            font.pixelSize: 11
                        }

                        ListView {
                            id: recentList

                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.min(contentHeight, 220)
                            visible: count > 0
                            clip: true
                            spacing: 6
                            boundsBehavior: Flickable.StopAtBounds
                            model: root.viewModel.recentProjects

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }

                            delegate: Rectangle {
                                id: recentDelegate

                                required property var modelData
                                width: ListView.view.width
                                height: 54
                                radius: 7
                                color: recentMouse.containsMouse ? "#f3f6fa" : "#f8fafc"
                                border.color: "#e2e7ee"

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 8
                                    spacing: 12

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2

                                        Label {
                                            Layout.fillWidth: true
                                            text: root.rowValue(recentDelegate.modelData, "title", qsTr("名称未設定"))
                                            color: "#344054"
                                            font.pixelSize: 12
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }

                                        Label {
                                            Layout.fillWidth: true
                                            text: root.rowValue(recentDelegate.modelData, "path", "")
                                            color: "#7a8493"
                                            font.pixelSize: 10
                                            elide: Text.ElideMiddle
                                        }
                                    }

                                    Button {
                                        text: qsTr("開く")
                                        onClicked: root.requestProjectSwitch(
                                                       "recent",
                                                       root.rowValue(recentDelegate.modelData,
                                                                     "path", ""))
                                    }
                                }

                                MouseArea {
                                    id: recentMouse

                                    anchors.fill: parent
                                    acceptedButtons: Qt.NoButton
                                    hoverEnabled: true
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Dialog {
        id: newProjectDialog

        anchors.centerIn: Overlay.overlay
        width: Math.min(560, root.width - 48)
        modal: true
        title: qsTr("新規プロジェクト")
        closePolicy: Popup.CloseOnEscape

        contentItem: ColumnLayout {
            spacing: 9

            Label {
                text: qsTr("プロジェクト名 *")
                color: "#344054"
                font.pixelSize: 11
            }
            TextField {
                id: newProjectTitle
                Layout.fillWidth: true
                placeholderText: qsTr("例：2026年度 夏期講習")
                Accessible.name: qsTr("プロジェクト名")
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Label {
                        text: qsTr("開始日 *")
                        color: "#344054"
                        font.pixelSize: 11
                    }
                    TextField {
                        id: newProjectStart
                        Layout.fillWidth: true
                        placeholderText: "2026-07-20"
                        Accessible.name: qsTr("講習開始日")
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Label {
                        text: qsTr("終了日 *")
                        color: "#344054"
                        font.pixelSize: 11
                    }
                    TextField {
                        id: newProjectEnd
                        Layout.fillWidth: true
                        placeholderText: "2026-08-31"
                        Accessible.name: qsTr("講習終了日")
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: storageNotice.implicitHeight + 18
                radius: 6
                color: "#f5f8fc"
                border.color: "#d9e1ec"

                Label {
                    id: storageNotice
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    text: qsTr("保存先はアプリが自動管理します。生徒・講師・指導可能科目・通常授業は、ホームの共通名簿から新しい講習へ自動反映します。")
                    color: "#52647d"
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }
            }

            Label {
                id: newProjectValidation
                Layout.fillWidth: true
                visible: false
                text: qsTr("プロジェクト名、開始日、終了日を入力してください。")
                color: "#a23b3b"
                font.pixelSize: 10
                wrapMode: Text.Wrap
            }
        }

        footer: DialogButtonBox {
            Button {
                text: qsTr("キャンセル")
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole
            }
            Button {
                text: qsTr("作成")
                highlighted: true
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
            }
            onRejected: newProjectDialog.close()
            onAccepted: {
                const complete = newProjectTitle.text.trim().length > 0
                                 && newProjectStart.text.trim().length > 0
                                 && newProjectEnd.text.trim().length > 0
                newProjectValidation.visible = !complete
                if (complete) {
                    if (root.viewModel.createProjectInWorkspace(
                                newProjectTitle.text.trim(),
                                newProjectStart.text.trim(),
                                newProjectEnd.text.trim()))
                        newProjectDialog.close()
                }
            }
        }
    }

    Dialogs.FileDialog {
        id: openProjectDialog

        title: qsTr("プロジェクトを開く")
        fileMode: Dialogs.FileDialog.OpenFile
        currentFolder: root.viewModel.projectsDirectoryUrl
        nameFilters: [qsTr("塾時間割プロジェクト (*.jukuschedule)")]
        onAccepted: root.viewModel.openProject(selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: saveAsDialog

        title: qsTr("名前を付けて保存")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("塾時間割プロジェクト (*.jukuschedule)")]
        onAccepted: root.viewModel.saveAs(selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: duplicateDialog

        title: qsTr("プロジェクトを複製")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("塾時間割プロジェクト (*.jukuschedule)")]
        onAccepted: root.viewModel.duplicateProject(selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: backupDialog

        title: qsTr("バックアップの保存先")
        fileMode: Dialogs.FileDialog.SaveFile
        nameFilters: [qsTr("塾時間割プロジェクト (*.jukuschedule)")]
        onAccepted: root.viewModel.backupProject(selectedFile.toString())
    }

    Dialogs.FileDialog {
        id: restoreBackupDialog

        title: qsTr("復元するバックアップを選択")
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: [qsTr("塾時間割プロジェクト (*.jukuschedule)")]
        onAccepted: {
            root.pendingRestorePath = selectedFile.toString()
            restoreConfirmDialog.open()
        }
    }

    Dialogs.MessageDialog {
        id: restoreConfirmDialog

        title: qsTr("バックアップから復元")
        text: qsTr("現在の復元対象を、選択したバックアップの内容へ置き換えますか？")
        informativeText: qsTr("置換前に現在のファイルを必ず「復元前バックアップ」へ退避します。バックアップにも個人情報が含まれます。")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes
                    && root.pendingRestorePath.length > 0)
                root.viewModel.restoreProject(root.pendingRestorePath)
            root.pendingRestorePath = ""
        }
    }

    Dialogs.MessageDialog {
        id: closeDirtyDialog

        title: qsTr("未保存の変更")
        text: qsTr("保存されていない変更があります。")
        informativeText: qsTr("変更を破棄してプロジェクトを閉じますか？")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes)
                root.viewModel.closeProject(true)
        }
    }

    Dialogs.MessageDialog {
        id: switchDirtyDialog

        title: qsTr("未保存の変更")
        text: qsTr("保存されていない変更があります。")
        informativeText: qsTr("変更を破棄して別のプロジェクトへ切り替えますか？")
        buttons: Dialogs.MessageDialog.Yes | Dialogs.MessageDialog.No
        onButtonClicked: function (button) {
            if (button === Dialogs.MessageDialog.Yes) {
                root.viewModel.discardDraft()
                root.executeProjectSwitch(root.pendingSwitchAction,
                                          root.pendingRecentPath)
            }
            root.pendingSwitchAction = ""
            root.pendingRecentPath = ""
        }
    }
}
