import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

KcDialog {
    id: dialog
    objectName: "kcProjectDialog"
    property string project: "reel"
    property var photos: []
    modal: true; title: "KC Project"; width: 610; height: 650
    anchors.centerIn: parent
    function showProject(kind, paths) {
        project = kind
        photos = paths
        open()
    }
    FileDialog { id: musicPicker; title: "Choose music"; nameFilters: ["Audio files (*.mp3 *.wav *.m4a)"] }
    contentItem: ColumnLayout {
        spacing: 10
        Text { text: "Create " + dialog.project; color: Theme.ink; font.pixelSize: 20 }
        Text { text: dialog.project === "yearreview" ? "Whole library for selected year" : dialog.photos.length + " selected photos"; color: Theme.ink }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Repeater {
                model: dialog.photos.slice(0, 8)
                delegate: Rectangle {
                    width: 64; height: 64; radius: 4; color: Theme.contentPanel
                    border.color: Theme.chromeBorder
                    Image { anchors.fill: parent; anchors.margins: 2; source: "file:///" + modelData.toString().replace(/\\/g, "/"); fillMode: Image.PreserveAspectCrop; asynchronous: true }
                }
            }
        }
        KcTextField { id: titleField; Layout.fillWidth: true; placeholderText: "Title"; visible: ["reel", "photobook"].includes(dialog.project) }
        RowLayout {
            visible: ["reel", "yearreview"].includes(dialog.project)
            Text { text: "Size"; color: "#cfc9bb" }
            KcComboBox { id: sizeField; model: ["9:16", "4:5", "16:9"] }
        }
        RowLayout {
            visible: ["reel", "yearreview"].includes(dialog.project)
            KcButton { text: "Music..."; onClicked: musicPicker.open() }
            Text { text: musicPicker.selectedFile.toString().split("/").pop(); color: "#cfc9bb" }
        }
        RowLayout {
            visible: ["yearreview", "calendar"].includes(dialog.project)
            Text { text: "Year"; color: "#cfc9bb" }
            KcTextField { id: yearField; text: new Date().getFullYear().toString(); inputMethodHints: Qt.ImhDigitsOnly; width: 100 }
        }
        RowLayout {
            visible: dialog.project === "frames"
            Text { text: "Style"; color: "#cfc9bb" }
            KcComboBox { id: styleField; model: ["polaroid", "filmstrip", "card", "matte", "postcard"] }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 168
            visible: kcProjects && kcProjects.output.length > 0
            color: Theme.contentPanel; border.color: Theme.chromeBorder; radius: 6
            RowLayout {
                anchors.fill: parent; anchors.margins: 10; spacing: 12
                Image { Layout.preferredWidth: 125; Layout.fillHeight: true; source: kcProjects ? kcProjects.thumbnailUrl : ""; fillMode: Image.PreserveAspectFit; asynchronous: true }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Project ready"; color: Theme.ink; font.bold: true }
                    Text { Layout.fillWidth: true; text: kcProjects ? kcProjects.output : ""; color: Theme.textGray; elide: Text.ElideMiddle }
                    Flow {
                        Layout.fillWidth: true; spacing: 5
                        KcButton { text: "Open Folder"; onClicked: kcProjects.openFolder() }
                        KcButton { text: "Send to Phone"; onClicked: kcTools.share("phone", [kcProjects.output]) }
                        KcButton { text: "Put on Drop"; onClicked: kcTools.share("drop", [kcProjects.output]) }
                        KcButton { text: "Get Share Link"; onClicked: kcTools.share("link", [kcProjects.output]) }
                    }
                }
            }
        }
        Item { Layout.fillHeight: true }
        Text { text: kcProjects && kcProjects.busy ? "Rendering in background..." : "Saves to Pictures/KC Projects"; color: "#4d8f85" }
        RowLayout {
            KcButton {
                text: "Create"; accent: true; enabled: kcProjects && !kcProjects.busy
                onClicked: {
                    var opts = {title: titleField.text, size: sizeField.currentText,
                                style: styleField.currentText, year: parseInt(yearField.text)}
                    if (musicPicker.selectedFile.toString()) opts.music = musicPicker.selectedFile.toString()
                    kcProjects.create(dialog.project, dialog.photos, opts)
                }
            }
            KcButton { text: "Cancel render"; enabled: kcProjects && kcProjects.busy; onClicked: kcProjects.cancel() }
            KcButton { text: "Close"; onClicked: dialog.close() }
        }
    }
}
