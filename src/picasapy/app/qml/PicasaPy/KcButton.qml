import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool accent: false
    implicitHeight: 34
    leftPadding: 12; rightPadding: 12
    contentItem: Text {
        text: control.text; font: control.font
        color: control.enabled ? (control.accent ? "#f6faf8" : Theme.ink) : Theme.textGray
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        color: control.accent && control.enabled ? (control.down ? "#39746c" : "#4d8f85")
               : control.hovered ? "#28343a" : Theme.contentPanel
        border.color: control.accent && control.enabled ? "#4d8f85" : Theme.chromeBorder
        border.width: 1; radius: 6
    }
}
