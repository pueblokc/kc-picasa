import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

KcDialog {
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
                contentItem: Text { text: parent.text; color: Theme.ink; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { color: parent.highlighted ? "#31564f" : Theme.contentPanel; border.color: Theme.chromeBorder; radius: 4 }
            }
        }
        Text { text: "Keep the current index as index.db.before-restore-..."; color: "#4d8f85"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            KcButton { text: "Cancel"; onClicked: dialog.close() }
            KcButton {
                text: "Confirm restore"; accent: true; enabled: dialog.selectedPath.length > 0
                onClicked: confirm.open()
            }
        }
    }
    KcDialog {
        id: confirm
        anchors.centerIn: parent
        modal: true
        title: "Confirm index restore"
        width: 390; height: 180
        contentItem: ColumnLayout {
            Text { text: "Restore the selected index on next launch?"; color: Theme.ink; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                KcButton { text: "Cancel"; onClicked: confirm.close() }
                KcButton { text: "Restore"; accent: true; onClicked: { kcBackup.restore(dialog.selectedPath); confirm.close(); dialog.close() } }
            }
        }
    }
}
