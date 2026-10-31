import QtQuick
import QtQuick.Controls

TextField {
    id: control
    implicitHeight: 36
    color: Theme.ink
    placeholderTextColor: Theme.textGray
    selectionColor: "#4d8f85"
    selectedTextColor: "#f6faf8"
    leftPadding: 10; rightPadding: 10
    background: Rectangle { color: Theme.contentPanel; border.color: control.activeFocus ? "#4d8f85" : Theme.chromeBorder; border.width: 1; radius: 5 }
}
