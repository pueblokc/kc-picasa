import QtQuick
import QtQuick.Controls

Popup {
    id: toast
    objectName: "kcStatusToast"
    parent: Overlay.overlay
    x: parent ? (parent.width - width) / 2 : 0
    y: parent ? parent.height - height - 72 : 0
    width: Math.min(480, parent ? parent.width - 32 : 480)
    padding: 14
    modal: false
    closePolicy: Popup.NoAutoClose
    property string message: ""
    background: Rectangle { color: "#1c2328"; border.color: "#4d8f85"; radius: 9 }
    contentItem: Text { text: toast.message; color: "#cfc9bb"; wrapMode: Text.Wrap; font.pixelSize: 14 }
    Timer { id: hideTimer; interval: 4500; onTriggered: toast.close() }
    Connections {
        target: kcTools
        function onMessage(message) { toast.message = message; toast.open(); hideTimer.restart() }
    }
    Connections {
        target: kcBackup
        function onMessage(message) { toast.message = message; toast.open(); hideTimer.restart() }
    }
}
