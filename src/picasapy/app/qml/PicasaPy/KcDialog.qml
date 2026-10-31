import QtQuick
import QtQuick.Controls

Dialog {
    id: dialog
    modal: true
    padding: 18
    anchors.centerIn: parent
    background: Rectangle { color: Theme.chromeBg; border.color: Theme.chromeBorder; border.width: 1; radius: 10 }
    header: Rectangle {
        implicitHeight: 48
        color: Theme.chromeBg
        radius: 10
        Text {
            anchors.left: parent.left; anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            text: dialog.title; color: Theme.ink; font.pixelSize: 19; font.bold: true
        }
    }
}
