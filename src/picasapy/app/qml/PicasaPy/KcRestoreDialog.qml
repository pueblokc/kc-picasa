import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "kcRestoreDialog"
    modal: true
    title: "Restore Index"
    width: 580
    height: 500
    anchors.centerIn: parent
    property var entries: []
    property string selectedPath: ""
    onAboutToShow: { entries = kcBackup.backups(); selectedPath = "" }
    background: Rectangle { color: "#151b1f"; border.color: "#28323a"; radius: 10 }
    contentItem: ColumnLayout {
        spacing: 12
        Text { text: "Restore Index"; color: "#cfc9bb"; font.pixelSize: 22 }
        Text { text: "Choose a backup. The index will be replaced on the next start."; color: "#cfc9bb"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        Text { text: "No index backups yet."; color: "#cfc9bb"; visible: dialog.entries.length === 0 }
        ListView {
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; model: dialog.entries
            delegate: ItemDelegate {
                width: ListView.view.width
                text: modelData.modified + "  ·  " + (modelData.size / 1048576).toFixed(1) + " MB"
                highlighted: dialog.selectedPath === modelData.path
                onClicked: dialog.selectedPath = modelData.path
            }
        }
        Text { text: "Keep the current index as index.db.before-restore-..."; color: "#4d8f85"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            Button { text: "Cancel"; onClicked: dialog.close() }
            Button {
                text: "Confirm restore"; enabled: dialog.selectedPath.length > 0
                onClicked: confirm.open()
            }
        }
    }
    Dialog {
        id: confirm
        anchors.centerIn: parent
        modal: true
        title: "Confirm index restore"
        standardButtons: Dialog.Yes | Dialog.No
        onAccepted: { kcBackup.restore(dialog.selectedPath); dialog.close() }
        contentItem: Text { text: "Restore the selected index on next launch?"; color: "#cfc9bb"; padding: 20 }
        background: Rectangle { color: "#1c2328"; border.color: "#28323a" }
    }
}
