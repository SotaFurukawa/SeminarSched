import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root

    signal dateEdited

    property int fromYear: 2020
    property int toYear: 2070
    property int selectedYear: Math.max(fromYear,
                                        Math.min(toYear, new Date().getFullYear()))
    property int selectedMonth: 1
    property int selectedDay: 1
    property string accessibleName: qsTr("日付")
    readonly property string dateText: root.pad(root.selectedYear, 4) + "-"
                                               + root.pad(root.selectedMonth, 2) + "-"
                                               + root.pad(root.selectedDay, 2)

    spacing: 6

    function pad(value, digits) {
        let text = String(value)
        while (text.length < digits)
            text = "0" + text
        return text
    }

    function numberRange(first, last, suffix) {
        const result = []
        for (let value = first; value <= last; ++value)
            result.push(String(value) + suffix)
        return result
    }

    function daysInMonth(year, month) {
        return new Date(year, month, 0).getDate()
    }

    function clampDay() {
        const maximum = root.daysInMonth(root.selectedYear, root.selectedMonth)
        if (root.selectedDay > maximum)
            root.selectedDay = maximum
        if (root.selectedDay < 1)
            root.selectedDay = 1
    }

    function setDate(year, month, day) {
        root.selectedYear = Math.max(root.fromYear,
                                     Math.min(root.toYear, Number(year)))
        root.selectedMonth = Math.max(1, Math.min(12, Number(month)))
        root.selectedDay = Math.max(1, Number(day))
        root.clampDay()
    }

    function setDateString(value) {
        const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/)
        if (match)
            root.setDate(Number(match[1]), Number(match[2]), Number(match[3]))
    }

    onSelectedYearChanged: clampDay()
    onSelectedMonthChanged: clampDay()

    ComboBox {
        id: yearBox

        Layout.fillWidth: true
        Layout.minimumWidth: 92
        model: root.numberRange(root.fromYear, root.toYear, qsTr("年"))
        currentIndex: root.selectedYear - root.fromYear
        Accessible.name: root.accessibleName + qsTr("の年")
        onActivated: {
            root.selectedYear = root.fromYear + currentIndex
            root.dateEdited()
        }
    }

    ComboBox {
        id: monthBox

        Layout.preferredWidth: 76
        model: root.numberRange(1, 12, qsTr("月"))
        currentIndex: root.selectedMonth - 1
        Accessible.name: root.accessibleName + qsTr("の月")
        onActivated: {
            root.selectedMonth = currentIndex + 1
            root.dateEdited()
        }
    }

    ComboBox {
        id: dayBox

        Layout.preferredWidth: 76
        model: root.numberRange(
                   1, root.daysInMonth(root.selectedYear, root.selectedMonth), qsTr("日"))
        currentIndex: root.selectedDay - 1
        Accessible.name: root.accessibleName + qsTr("の日")
        onActivated: {
            root.selectedDay = currentIndex + 1
            root.dateEdited()
        }
    }
}
