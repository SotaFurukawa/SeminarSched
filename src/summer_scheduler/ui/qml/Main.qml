pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root

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

    visible: true
    width: 1366
    height: 768
    minimumWidth: 1040
    minimumHeight: 640
    title: workspace.hasOpenProject && workspace.currentProjectTitle
           ? qsTr("%1 - 夏期講習時間割作成").arg(workspace.currentProjectTitle)
           : qsTr("夏期講習時間割作成")
    color: "#f4f6f8"

    function selectPage(index) {
        if (index >= 0 && index < navigationModel.count)
            currentPageIndex = index
    }

    ListModel {
        id: navigationModel

        ListElement {
            title: "ホーム"
            shortLabel: "H"
            phaseLabel: "Phase 2"
            description: "プロジェクトの作成・読込みと、講習準備の状況を確認します。"
        }
        ListElement {
            title: "生徒"
            shortLabel: "生"
            phaseLabel: "Phase 2"
            description: "生徒情報と、生徒×科目単位の受講希望を管理します。"
        }
        ListElement {
            title: "講師"
            shortLabel: "講"
            phaseLabel: "Phase 2"
            description: "講師情報と、科目ごとの指導可否を管理します。"
        }
        ListElement {
            title: "集団授業"
            shortLabel: "集"
            phaseLabel: "Phase 3"
            description: "集団授業の取込み、受講者、担当講師、衝突を管理する画面です。"
        }
        ListElement {
            title: "アンケート取込み"
            shortLabel: "取"
            phaseLabel: "Phase 3"
            description: "生徒・講師アンケートの列マッピングと検証を行う画面です。"
        }
        ListElement {
            title: "時間割"
            shortLabel: "時"
            phaseLabel: "Phase 5"
            description: "時間割の確認・手動編集・固定・再最適化を安全に行います。"
        }
        ListElement {
            title: "未配置・警告"
            shortLabel: "警"
            phaseLabel: "Phase 3"
            description: "最適化前の入力エラー、警告、情報をプロジェクト全体で確認します。"
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
            description: "プロジェクト、コマ、開校日、科目、Excel入出力を設定します。"
        }
    }

    header: Rectangle {
        implicitHeight: 70
        color: "#ffffff"
        border.color: "#dce2ea"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 22
            anchors.rightMargin: 22
            spacing: 16

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Label {
                    text: qsTr("夏期講習時間割作成")
                    color: "#18212f"
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }

                Label {
                    text: root.workspace.hasOpenProject
                          ? qsTr("%1 ～ %2")
                            .arg(root.workspace.currentStartDate || "----/--/--")
                            .arg(root.workspace.currentEndDate || "----/--/--")
                          : qsTr("プロジェクトを作成するか、既存ファイルを開いてください")
                    color: "#667085"
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }

            Rectangle {
                visible: root.workspace.hasOpenProject
                Layout.preferredWidth: dirtyLabel.implicitWidth + 24
                Layout.preferredHeight: 30
                radius: 15
                color: root.workspace.isDirty ? "#fff4db" : "#ecfdf3"
                border.color: root.workspace.isDirty ? "#e2b95f" : "#a9dec0"

                Label {
                    id: dirtyLabel

                    anchors.centerIn: parent
                    text: root.workspace.isDirty ? qsTr("● 未保存の変更") : qsTr("✓ 保存済み")
                    color: root.workspace.isDirty ? "#7a5710" : "#176b40"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
            }

            Rectangle {
                Layout.preferredWidth: databaseStatusLabel.implicitWidth + 24
                Layout.preferredHeight: 30
                radius: 15
                color: root.viewModel.databaseReady ? "#ecfdf3" : "#fff8e8"
                border.color: root.viewModel.databaseReady ? "#a9dec0" : "#e9cc86"

                Label {
                    id: databaseStatusLabel

                    anchors.centerIn: parent
                    text: (root.viewModel.databaseReady ? "✓ " : "… ")
                          + root.viewModel.databaseStatusText
                    color: root.viewModel.databaseReady ? "#176b40" : "#7a5710"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
            }

            Label {
                text: qsTr("v%1").arg(root.viewModel.appVersion)
                color: "#667085"
                font.pixelSize: 11
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
                text: qsTr("夏期講習 時間割作成")
                color: "#18212f"
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }

            Label {
                text: qsTr("アプリバージョン: %1").arg(root.viewModel.appVersion)
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
                text: qsTr("リリース候補です。プロジェクト本体のライセンスと"
                           + "コード署名は本番公開前に確認してください。")
                color: "#7a5710"
                wrapMode: Text.WordWrap
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            Layout.preferredWidth: 232
            Layout.fillHeight: true
            itemsModel: navigationModel
            currentIndex: root.currentPageIndex
            onPageSelected: index => root.selectPage(index)
        }

        Rectangle {
            Layout.preferredWidth: 1
            Layout.fillHeight: true
            color: "#dce2ea"
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
                color: "#f4f6f8"

                Loader {
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
                                           ? groupLessonComponent
                                           : root.currentPageIndex === 4
                                             ? availabilityImportComponent
                                             : root.currentPageIndex === 5
                                             ? optimizationComponent
                                             : root.currentPageIndex === 6
                                               ? validationIssuesComponent
                                               : root.currentPageIndex === 7
                                                 ? outputComponent
                                               : root.currentPageIndex === 8
                                                 ? settingsComponent
                                                 : placeholderComponent
                }
            }
        }
    }

    Component {
        id: homeComponent

        ProjectHomePage {
            viewModel: root.workspace
            onOpenSettingsRequested: root.selectPage(8)
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
        id: groupLessonComponent

        GroupLessonPage {
            viewModel: root.phase3
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
        id: optimizationComponent

        StackLayout {
            id: scheduleWorkspace

            currentIndex: 0

            ScheduleEditorPage {
                viewModel: root.scheduleEditor
                onOpenHomeRequested: root.selectPage(0)
                onOpenOptimizationRequested: scheduleWorkspace.currentIndex = 1
            }

            ColumnLayout {
                spacing: 0

                ToolBar {
                    Layout.fillWidth: true

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12

                        ToolButton {
                            text: qsTr("‹ 時間割編集へ戻る")
                            Accessible.name: qsTr("時間割編集画面へ戻る")
                            onClicked: scheduleWorkspace.currentIndex = 0
                        }

                        Item {
                            Layout.fillWidth: true
                        }

                        Label {
                            text: qsTr("ロック済み授業を保持して再最適化")
                            color: "#667085"
                            font.pixelSize: 10
                        }
                    }
                }

                OptimizationPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    viewModel: root.optimization
                    onOpenHomeRequested: root.selectPage(0)
                }
            }
        }
    }

    Component {
        id: validationIssuesComponent

        ValidationIssuesPage {
            viewModel: root.phase3
            onOpenHomeRequested: root.selectPage(0)
        }
    }

    Component {
        id: outputComponent

        OutputPage {
            viewModel: root.output
            onOpenHomeRequested: root.selectPage(0)
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
