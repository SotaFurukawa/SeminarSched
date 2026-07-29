pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var viewModel
    signal openHomeRequested

    function rowValue(row, key, fallback) {
        if (row && row[key] !== undefined && row[key] !== null)
            return row[key]
        return fallback
    }

    function objectiveValue(key) {
        return Number(root.rowValue(root.viewModel.objectiveBreakdown, key, 0))
    }

    function elapsedText(seconds) {
        const value = Math.max(0, Number(seconds) || 0)
        const minutes = Math.floor(value / 60)
        const remaining = value - minutes * 60
        return minutes > 0
                ? qsTr("%1分 %2秒").arg(minutes).arg(remaining.toFixed(1))
                : qsTr("%1秒").arg(remaining.toFixed(1))
    }

    function defaultPresetIndex() {
        const target = String(root.viewModel.defaultPreset || "standard")
        for (let i = 0; i < presetBox.count; ++i) {
            if (String(presetBox.model[i].value) === target)
                return i
        }
        return 1
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
                text: qsTr("時間割を自動作成するには、ホームからプロジェクトを開いてください。")
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
                    text: qsTr("時間割の自動作成")
                    color: "#18212f"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                }
                Label {
                    text: qsTr("ハード制約を守り、配置不能な授業は未配置として理由を表示します。")
                    color: "#667085"
                    font.pixelSize: 10
                }
            }

            Label {
                text: root.viewModel.isRunning ? qsTr("● 実行中") : qsTr("● 待機")
                color: root.viewModel.isRunning ? "#176b40" : "#667085"
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
        }

        StatusBanner {
            Layout.fillWidth: true
            viewModel: root.viewModel
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: runControls.implicitHeight + 18
            radius: 8
            color: "#ffffff"
            border.color: "#dce2ea"

            RowLayout {
                id: runControls

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 9

                Label {
                    text: qsTr("実行品質")
                    color: "#344054"
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                }

                ComboBox {
                    id: presetBox

                    Layout.preferredWidth: 190
                    enabled: !root.viewModel.isRunning
                    model: [
                        {
                            "label": qsTr("高速（30秒）"),
                            "value": "fast"
                        },
                        {
                            "label": qsTr("標準（120秒）"),
                            "value": "standard"
                        },
                        {
                            "label": qsTr("高品質（600秒）"),
                            "value": "high_quality"
                        }
                    ]
                    textRole: "label"
                    valueRole: "value"
                    Component.onCompleted: currentIndex = root.defaultPresetIndex()
                    Accessible.name: qsTr("最適化の実行品質")
                }

                Button {
                    text: qsTr("自動作成を実行")
                    highlighted: true
                    enabled: !root.viewModel.isRunning
                    onClicked: root.viewModel.runOptimization(presetBox.currentValue)
                }

                Button {
                    text: qsTr("中止")
                    enabled: root.viewModel.isRunning
                    onClicked: root.viewModel.cancelOptimization()
                }

                ProgressBar {
                    Layout.fillWidth: true
                    indeterminate: root.viewModel.isRunning
                    from: 0
                    to: 1
                    value: root.viewModel.isRunning ? 0.5 : 0
                    Accessible.name: qsTr("最適化進捗")
                }

                ColumnLayout {
                    Layout.preferredWidth: 170
                    spacing: 0
                    Label {
                        Layout.fillWidth: true
                        text: root.viewModel.stage || qsTr("待機")
                        color: "#344054"
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignRight
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("%1 / %2")
                              .arg(root.viewModel.solverStatus || qsTr("未実行"))
                              .arg(root.elapsedText(root.viewModel.elapsedSeconds))
                        color: "#667085"
                        font.pixelSize: 9
                        horizontalAlignment: Text.AlignRight
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: [
                    {
                        "label": qsTr("solver status"),
                        "value": root.viewModel.solverStatus || qsTr("未実行"),
                        "color": "#174f9e",
                        "background": "#eef5ff"
                    },
                    {
                        "label": qsTr("配置"),
                        "value": root.viewModel.assignedCount,
                        "color": "#176b40",
                        "background": "#ecfdf3"
                    },
                    {
                        "label": qsTr("未配置"),
                        "value": root.viewModel.unassignedCount,
                        "color": root.viewModel.unassignedCount > 0 ? "#a23b3b" : "#176b40",
                        "background": root.viewModel.unassignedCount > 0 ? "#fff6f5" : "#ecfdf3"
                    },
                    {
                        "label": qsTr("経過時間"),
                        "value": root.elapsedText(root.viewModel.elapsedSeconds),
                        "color": "#475467",
                        "background": "#f8fafc"
                    }
                ]

                delegate: Rectangle {
                    id: summaryDelegate

                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 62
                    radius: 7
                    color: root.rowValue(summaryDelegate.modelData,
                                         "background", "#ffffff")
                    border.color: root.rowValue(summaryDelegate.modelData,
                                                "color", "#dce2ea")

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 1
                        Label {
                            Layout.alignment: Qt.AlignHCenter
                            text: root.rowValue(summaryDelegate.modelData, "label", "")
                            color: "#667085"
                            font.pixelSize: 9
                        }
                        Label {
                            Layout.alignment: Qt.AlignHCenter
                            text: root.rowValue(summaryDelegate.modelData, "value", "")
                            color: root.rowValue(summaryDelegate.modelData,
                                                 "color", "#344054")
                            font.pixelSize: 18
                            font.weight: Font.Bold
                        }
                    }
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.preferredWidth: 390
                SplitView.minimumWidth: 330
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 8

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 7

                    Label {
                        text: qsTr("目的関数の内訳")
                        color: "#344054"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: 8
                        rowSpacing: 5

                        Repeater {
                            model: [
                                {
                                    "label": qsTr("未配置数"),
                                    "key": "unassignedCount"
                                },
                                {
                                    "label": qsTr("講師希望違反"),
                                    "key": "teacherPreferencePenalty"
                                },
                                {
                                    "label": qsTr("講師稼働枠"),
                                    "key": "activeTeacherSlotCount"
                                },
                                {
                                    "label": qsTr("日時希望スコア"),
                                    "key": "availabilityPreferenceScore"
                                },
                                {
                                    "label": qsTr("既存割当て変更"),
                                    "key": "changedAssignmentCount"
                                },
                                {
                                    "label": qsTr("任意調整スコア"),
                                    "key": "optionalBalanceScore"
                                }
                            ]

                            delegate: Rectangle {
                                id: objectiveDelegate

                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 48
                                radius: 6
                                color: "#f8fafc"
                                border.color: "#e2e7ee"

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 8
                                    anchors.rightMargin: 8
                                    Label {
                                        Layout.fillWidth: true
                                        text: root.rowValue(
                                                  objectiveDelegate.modelData,
                                                  "label", "")
                                        color: "#667085"
                                        font.pixelSize: 9
                                    }
                                    Label {
                                        text: root.objectiveValue(
                                                  root.rowValue(
                                                      objectiveDelegate.modelData,
                                                      "key", ""))
                                        color: "#344054"
                                        font.pixelSize: 15
                                        font.weight: Font.Bold
                                    }
                                }
                            }
                        }
                    }

                    Label {
                        text: qsTr("警告")
                        color: "#344054"
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }

                    ListView {
                        id: warningList

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 3
                        model: root.viewModel.warnings || []
                        boundsBehavior: Flickable.StopAtBounds

                        delegate: Rectangle {
                            id: warningDelegate

                            required property string modelData
                            width: ListView.view.width
                            implicitHeight: warningText.implicitHeight + 12
                            color: "#fff8e8"
                            border.color: "#ecd49c"
                            radius: 5

                            Label {
                                id: warningText

                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.leftMargin: 7
                                anchors.rightMargin: 7
                                text: qsTr("△ %1").arg(warningDelegate.modelData)
                                color: "#7a5100"
                                font.pixelSize: 9
                                wrapMode: Text.Wrap
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: warningList.count === 0
                            text: qsTr("警告はありません")
                            color: "#7a8493"
                            font.pixelSize: 9
                        }
                    }
                }
            }

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 440
                color: "#ffffff"
                border.color: "#dce2ea"
                radius: 8

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("未配置授業と理由")
                            color: "#344054"
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Label {
                            text: qsTr("%1件").arg(unassignedList.count)
                            color: "#667085"
                            font.pixelSize: 9
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        color: "#eef2f6"
                        border.color: "#dce2ea"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 9
                            anchors.rightMargin: 9
                            Label {
                                Layout.preferredWidth: 150
                                text: qsTr("授業セッション")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                            Label {
                                Layout.fillWidth: true
                                text: qsTr("配置できない理由")
                                color: "#475467"
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                            }
                        }
                    }

                    ListView {
                        id: unassignedList

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 1
                        model: root.viewModel.unassignedLessons || []
                        boundsBehavior: Flickable.StopAtBounds

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }

                        delegate: Rectangle {
                            id: unassignedDelegate

                            required property int index
                            required property var modelData
                            width: ListView.view.width
                            height: 58
                            color: index % 2 === 0 ? "#ffffff" : "#f8fafc"
                            border.color: "#edf0f4"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 9
                                anchors.rightMargin: 9
                                spacing: 8

                                ColumnLayout {
                                    Layout.preferredWidth: 150
                                    spacing: 0
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("要求ID:%1 / 第%2回")
                                              .arg(root.rowValue(
                                                       unassignedDelegate.modelData,
                                                       "lessonRequestId", ""))
                                              .arg(root.rowValue(
                                                       unassignedDelegate.modelData,
                                                       "sessionIndex", ""))
                                        color: "#344054"
                                        font.pixelSize: 9
                                        font.weight: Font.DemiBold
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("生徒ID:%1 / 科目ID:%2")
                                              .arg(root.rowValue(
                                                       unassignedDelegate.modelData,
                                                       "studentId", ""))
                                              .arg(root.rowValue(
                                                       unassignedDelegate.modelData,
                                                       "subjectId", ""))
                                        color: "#7a8493"
                                        font.pixelSize: 8
                                    }
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: root.rowValue(
                                              unassignedDelegate.modelData,
                                              "reasonText",
                                              qsTr("詳細な理由を取得できませんでした"))
                                    color: "#7d2925"
                                    font.pixelSize: 9
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 3
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        Label {
                            anchors.centerIn: parent
                            visible: unassignedList.count === 0
                            text: root.viewModel.solverStatus === "未実行"
                                  ? qsTr("最適化を実行すると未配置理由を表示します")
                                  : qsTr("未配置授業はありません")
                            color: "#7a8493"
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: logRow.implicitHeight + 14
            radius: 6
            color: "#f8fafc"
            border.color: "#dce2ea"

            RowLayout {
                id: logRow

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 9
                anchors.rightMargin: 9
                spacing: 8

                Label {
                    text: qsTr("最適化専用ログ保存先")
                    color: "#475467"
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                }
                Label {
                    Layout.fillWidth: true
                    text: root.viewModel.logPath
                    color: "#667085"
                    font.pixelSize: 9
                    elide: Text.ElideMiddle
                }
                Label {
                    text: qsTr("保存後は時間割編集画面へ戻り、変更差分を確認できます")
                    color: "#7a8493"
                    font.pixelSize: 8
                }
            }
        }
    }
}
