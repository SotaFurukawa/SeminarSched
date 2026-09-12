pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root

    UiTheme { id: theme }

    // Python registers these objects as context properties. Static QML tooling
    // cannot discover context properties, so access is isolated here.
    // qmllint disable unqualified
    readonly property var viewModel: appViewModel
    readonly property var workspace: workspaceViewModel
    readonly property var phase3: phase3ViewModel
    readonly property var optimization: optimizationViewModel
    readonly property var scheduleEditor: scheduleEditorViewModel
    readonly property var output: outputViewModel
    // qmllint enable unqualified
    property int currentPageIndex: 0
    readonly property var activePage: navigationModel.get(currentPageIndex)
    readonly property string applicationDisplayName: qsTr("季節講習 時間割作成 v%1 (%2)")
                                                     .arg(root.viewModel.appVersion)
                                                     .arg(root.viewModel.releaseChannel)

    visible: true
    width: 1366
    height: 768
    minimumWidth: 1040
    minimumHeight: 640
    // Windowsはアプリ表示名をタイトル末尾へ自動付加するため、ここでは重複させない。
    title: workspace.hasOpenProject && workspace.currentProjectTitle
           ? workspace.currentProjectTitle : ""
    color: theme.appBackground

    function selectPage(index) {
        if (index !== 0 && index !== 1 && index !== 2 && !workspace.hasOpenProject)
            return
        if (index >= 0 && index < navigationModel.count)
            currentPageIndex = index
    }

    // Loader.itemの具体型は実行時に決まるため、ページ共通の保存hookは動的に呼ぶ。
    // qmllint disable missing-property
    function saveEverything() {
        const activeItem = pageLoader.item
        const savePendingChanges = activeItem
                                   ? activeItem["savePendingChanges"] : null
        if (typeof savePendingChanges === "function"
                && savePendingChanges.call(activeItem) === false)
            return false
        if (root.output.settingsDirty && !root.output.saveSettings())
            return false
        return root.workspace.saveAllData()
    }
    // qmllint enable missing-property

    ListModel {
        id: navigationModel

        ListElement {
            title: "ホーム"
            shortLabel: "H"
            phaseLabel: "全体"
            description: "プロジェクトの作成・読込みと、次に行う作業を確認します。"
        }
        ListElement {
            title: "生徒の基本情報"
            shortLabel: "生"
            phaseLabel: "Phase 2"
            description: "生徒情報と、生徒×科目単位の受講希望を管理します。"
        }
        ListElement {
            title: "講師の基本情報"
            shortLabel: "講"
            phaseLabel: "Phase 2"
            description: "講師情報と、科目ごとの指導可否を管理します。"
        }
        ListElement {
            title: "アンケート取込"
            shortLabel: "取"
            phaseLabel: "Phase 3"
            description: "生徒・講師アンケートの列マッピングと検証を行う画面です。"
        }
        ListElement {
            title: "時間割編集"
            shortLabel: "時"
            phaseLabel: "Phase 5"
            description: "時間割の確認・手動編集・固定・再最適化を安全に行います。"
        }
        ListElement {
            title: "未配置・警告"
            shortLabel: "警"
            phaseLabel: "Phase 3"
            description: "入力エラー、未配置、警告を作業リストとして確認します。"
        }
        ListElement {
            title: "出力"
            shortLabel: "出"
            phaseLabel: "Phase 6"
            description: "時間割や警告一覧をExcel・PDFへ出力する画面です。"
        }
        ListElement {
            title: "設定"
            shortLabel: "設"
            phaseLabel: "Phase 2"
            description: "プロジェクト、コマ、開校日、科目を設定します。"
        }
        ListElement {
            title: "アンケート作成"
            shortLabel: "作"
            phaseLabel: "入力準備"
            description: "設定した開校日・コマから、生徒用・講師用Googleフォーム作成キットを生成します。"
        }
        ListElement {
            title: "時間割自動作成"
            shortLabel: "自"
            phaseLabel: "Phase 5"
            description: "未配置の授業を条件に沿って自動配置します。"
        }
        ListElement {
            title: "配布物確認"
            shortLabel: "配"
            phaseLabel: "Phase 6"
            description: "個別・講師・生徒向けの配布時間割を確認して出力します。"
        }
    }

    header: Rectangle {
        implicitHeight: 64
        color: theme.surface
        border.color: theme.border
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: theme.spacingXl
            anchors.rightMargin: theme.spacingXl
            spacing: theme.spacingLg

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Label {
                    text: root.workspace.hasOpenProject
                          ? root.workspace.currentProjectTitle
                          : root.applicationDisplayName
                    color: theme.textPrimary
                    font.pixelSize: 19
                    font.weight: Font.DemiBold
                }

                Label {
                    text: root.workspace.hasOpenProject
                          ? qsTr("%1　›　%2 ～ %3")
                            .arg(root.activePage.title)
                            .arg(root.workspace.currentStartDate || "----/--/--")
                            .arg(root.workspace.currentEndDate || "----/--/--")
                          : root.currentPageIndex === 1 || root.currentPageIndex === 2
                            ? qsTr("%1　›　共通基本情報").arg(root.activePage.title)
                            : qsTr("ホーム　›　プロジェクトを選択")
                    color: theme.textSecondary
                    font.pixelSize: theme.captionSize
                    elide: Text.ElideRight
                }
            }

            StatusBadge {
                visible: root.workspace.hasOpenProject
                status: root.workspace.isDirty ? "warning" : "complete"
                symbol: root.workspace.isDirty ? "●" : "✓"
                label: root.workspace.isDirty ? qsTr("未保存の変更") : qsTr("保存済み")
            }

            StatusBadge {
                status: root.viewModel.databaseReady ? "complete" : "warning"
                symbol: root.viewModel.databaseReady ? "✓" : "…"
                label: root.viewModel.databaseStatusText
            }

            Label {
                text: qsTr("v%1 (%2)")
                      .arg(root.viewModel.appVersion)
                      .arg(root.viewModel.releaseChannel)
                color: theme.textSecondary
                font.pixelSize: theme.captionSize
            }

            AppButton {
                text: qsTr("すべて保存")
                kind: "primary"
                Accessible.name: qsTr("アプリ内の変更をすべて保存")
                onClicked: root.saveEverything()
            }

            ToolButton {
                text: qsTr("このアプリについて")
                Accessible.name: qsTr("アプリ情報を表示")
                onClicked: aboutDialog.open()
            }
        }
    }

    Dialog {
        id: aboutDialog

        anchors.centerIn: parent
        width: Math.min(520, root.width - 48)
        modal: true
        title: qsTr("このアプリについて")
        standardButtons: Dialog.Ok

        ColumnLayout {
            width: parent.width
            spacing: 10

            Label {
                text: qsTr("季節講習 時間割作成 v%1 (%2)")
                      .arg(root.viewModel.appVersion)
                      .arg(root.viewModel.releaseChannel)
                color: "#18212f"
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }

            Label {
                text: qsTr("アプリバージョン: %1 (%2)")
                      .arg(root.viewModel.appVersion)
                      .arg(root.viewModel.releaseChannel)
                color: "#344054"
            }

            Label {
                text: qsTr("対応DBスキーマ: %1").arg(root.viewModel.schemaVersion)
                color: "#344054"
            }

            Label {
                Layout.fillWidth: true
                text: qsTr("アプリの版とDBスキーマの版は別々に管理されます。"
                           + "すべてのデータ処理はローカルPC内で行い、"
                           + "テレメトリや外部送信は行いません。")
                color: "#475467"
                wrapMode: Text.WordWrap
            }

            Label {
                Layout.fillWidth: true
                text: qsTr("このv1系はBeta版です。正式リリースへ移行するまで、"
                           + "GitHub ReleaseはPre-releaseとして配布します。")
                color: "#7a5710"
                wrapMode: Text.WordWrap
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            Layout.preferredWidth: 248
            Layout.minimumWidth: 224
            Layout.maximumWidth: 248
            Layout.fillHeight: true
            itemsModel: navigationModel
            projectOpen: root.workspace.hasOpenProject
            currentIndex: root.currentPageIndex
            onPageSelected: index => root.selectPage(index)
        }

        Rectangle {
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            color: theme.border
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            StatusBanner {
                Layout.fillWidth: true
                viewModel: root.workspace
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: theme.appBackground

                Loader {
                    id: pageLoader
                    anchors.fill: parent
                    active: true
                    asynchronous: false
                    sourceComponent: root.currentPageIndex === 0
                                     ? homeComponent
                                     : root.currentPageIndex === 1
                                       ? studentComponent
                                     : root.currentPageIndex === 2
                                         ? teacherComponent
                                         : root.currentPageIndex === 3
                                           ? availabilityImportComponent
                                           : root.currentPageIndex === 4
                                             ? editingComponent
                                             : root.currentPageIndex === 5
                                               ? validationIssuesComponent
                                               : root.currentPageIndex === 6
                                                 ? outputComponent
                                               : root.currentPageIndex === 7
                                                 ? settingsComponent
                                                 : root.currentPageIndex === 8
                                                   ? questionnaireCreationComponent
                                                   : root.currentPageIndex === 9
                                                     ? optimizationComponent
                                                   : root.currentPageIndex === 10
                                                     ? distributionReviewComponent
                                                 : placeholderComponent
                }
            }
        }
    }

    Component {
        id: homeComponent

        ProjectHomePage {
            viewModel: root.workspace
            phase3ViewModel: root.phase3
            scheduleViewModel: root.scheduleEditor
            outputViewModel: root.output
            onOpenSettingsRequested: root.selectPage(7)
            onNavigateRequested: pageIndex => root.selectPage(pageIndex)
        }
    }

    Component {
        id: studentComponent

        StudentPage {
            viewModel: root.workspace
            onOpenHomeRequested: root.selectPage(0)
        }
    }

    Component {
        id: teacherComponent

        TeacherPage {
            viewModel: root.workspace
            onOpenHomeRequested: root.selectPage(0)
        }
    }

    Component {
        id: availabilityImportComponent

        AvailabilityImportPage {
            viewModel: root.phase3
            onOpenHomeRequested: root.selectPage(0)
        }
    }

    Component {
        id: questionnaireCreationComponent

        QuestionnaireCreationPage {
            viewModel: root.phase3
            workspace: root.workspace
            onOpenHomeRequested: root.selectPage(0)
            onOpenSettingsRequested: root.selectPage(7)
        }
    }

    Component {
        id: editingComponent

        ColumnLayout {
            spacing: 0

            TabBar {
                id: editingTabs
                Layout.fillWidth: true

                TabButton { text: qsTr("時間割編集") }
                TabButton { text: qsTr("先に確定するコマ") }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: editingTabs.currentIndex

                ScheduleEditorPage {
                    viewModel: root.scheduleEditor
                    onOpenHomeRequested: root.selectPage(0)
                    onOpenOptimizationRequested: root.selectPage(9)
                }

                PreconfirmationPage {
                    viewModel: root.scheduleEditor
                    onOpenHomeRequested: root.selectPage(0)
                    onOpenTimetableRequested: editingTabs.currentIndex = 0
                    onOpenOptimizationRequested: root.selectPage(9)
                }
            }
        }
    }

    Component {
        id: optimizationComponent

        OptimizationPage {
            viewModel: root.optimization
            onOpenHomeRequested: root.selectPage(0)
            onOpenIssuesRequested: {
                root.phase3.refreshPhase3()
                root.selectPage(5)
            }
        }
    }

    Component {
        id: validationIssuesComponent

        ValidationIssuesPage {
            viewModel: root.phase3
            Component.onCompleted: root.phase3.refreshPhase3()
            onOpenHomeRequested: root.selectPage(0)
            onNavigateRequested: function (pageIndex) {
                root.selectPage(pageIndex)
            }
        }
    }

    Component {
        id: outputComponent

        OutputPage {
            viewModel: root.output
            onOpenHomeRequested: root.selectPage(0)
            onOpenIssuesRequested: root.selectPage(5)
        }
    }

    Component {
        id: distributionReviewComponent

        OutputPage {
            viewModel: root.output
            distributionReviewMode: true
            onOpenHomeRequested: root.selectPage(0)
            onOpenIssuesRequested: root.selectPage(5)
        }
    }

    Component {
        id: settingsComponent

        SettingsPage {
            viewModel: root.workspace
            onOpenHomeRequested: root.selectPage(0)
        }
    }

    Component {
        id: placeholderComponent

        PlaceholderPage {
            pageTitle: root.activePage.title
            phaseLabel: root.activePage.phaseLabel
            description: root.activePage.description
        }
    }
}
