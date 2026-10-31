import QtQuick
import QtQuick.Controls

Popup {
    id: toast
    objectName: "kcStatusToast"
    parent: Overlay.overlay
    x: parent ? (parent.width - width) / 2 : 0
    y: parent ? parent.height - height - 72 : 0
    width: Math.min(560, parent ? parent.width - 32 : 560)
    padding: 14
    modal: false
    closePolicy: Popup.NoAutoClose
    property string message: ""
    property bool projectActions: false
    background: Rectangle { color: "#1c2328"; border.color: "#4d8f85"; radius: 9 }
    contentItem: Column {
        spacing: 6
        Text { text: toast.message; color: "#cfc9bb"; wrapMode: Text.Wrap; font.pixelSize: 14; width: parent.width }
        Row {
            visible: toast.projectActions
            spacing: 4
            Button { text: "Open folder"; onClicked: kcProjects.openFolder() }
            Button { text: "Send to Phone"; onClicked: kcTools.share("phone", [kcProjects.output]) }
            Button { text: "Put on Drop"; onClicked: kcTools.share("drop", [kcProjects.output]) }
            Button { text: "Get Share Link"; onClicked: kcTools.share("link", [kcProjects.output]) }
        }
    }
    Timer { id: hideTimer; interval: 4500; onTriggered: toast.close() }
    Connections {
        target: typeof kcTools !== "undefined" ? kcTools : null
        function onMessage(message) { toast.projectActions = false; toast.message = message; toast.open(); hideTimer.restart() }
    }
    Connections {
        target: typeof kcBackup !== "undefined" ? kcBackup : null
        function onMessage(message) { toast.projectActions = false; toast.message = message; toast.open(); hideTimer.restart() }
    }
    Connections {
        target: typeof kcSmart !== "undefined" ? kcSmart : null
        function onMessage(message) { toast.projectActions = false; toast.message = message; toast.open(); hideTimer.restart() }
    }
    Connections {
        target: typeof kcProjects !== "undefined" ? kcProjects : null
        function onMessage(message) { toast.projectActions = kcProjects.output !== ""; toast.message = message; toast.open(); hideTimer.interval = toast.projectActions ? 15000 : 4500; hideTimer.restart() }
    }
}
