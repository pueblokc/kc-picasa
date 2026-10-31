import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Dialog {
    id: dialog
    objectName: "kcProjectDialog"
    property string project: "reel"
    property var photos: []
    modal: true; title: "KC Project"; width: 460; height: 430
    anchors.centerIn: parent
    function showProject(kind, paths) {
        project = kind
        photos = paths
        open()
    }
    background: Rectangle { color: "#151b1f"; border.color: "#28323a"; radius: 10 }
    FileDialog { id: musicPicker; title: "Choose music"; nameFilters: ["Audio files (*.mp3 *.wav *.m4a)"] }
    contentItem: ColumnLayout {
        spacing: 10
        Text { text: "Create " + dialog.project; color: "#cfc9bb"; font.pixelSize: 20 }
        Text { text: dialog.project === "yearreview" ? "Whole library for selected year" : dialog.photos.length + " selected photos"; color: "#cfc9bb" }
        TextField { id: titleField; Layout.fillWidth: true; placeholderText: "Title"; visible: ["reel", "photobook"].includes(dialog.project) }
        RowLayout {
            visible: ["reel", "yearreview"].includes(dialog.project)
            Text { text: "Size"; color: "#cfc9bb" }
            ComboBox { id: sizeField; model: ["9:16", "4:5", "16:9"] }
        }
        RowLayout {
            visible: ["reel", "yearreview"].includes(dialog.project)
            Button { text: "Music..."; onClicked: musicPicker.open() }
            Text { text: musicPicker.selectedFile.toString().split("/").pop(); color: "#cfc9bb" }
        }
        RowLayout {
            visible: ["yearreview", "calendar"].includes(dialog.project)
            Text { text: "Year"; color: "#cfc9bb" }
            SpinBox { id: yearField; from: 1900; to: 2100; value: new Date().getFullYear() }
        }
        RowLayout {
            visible: dialog.project === "frames"
            Text { text: "Style"; color: "#cfc9bb" }
            ComboBox { id: styleField; model: ["polaroid", "filmstrip", "card", "matte", "postcard"] }
        }
        Item { Layout.fillHeight: true }
        Text { text: kcProjects.busy ? "Rendering in background..." : "Saves to Pictures/KC Projects"; color: "#4d8f85" }
        RowLayout {
            Button {
                text: "Create"; enabled: !kcProjects.busy
                onClicked: {
                    var opts = {title: titleField.text, size: sizeField.currentText,
                                style: styleField.currentText, year: yearField.value}
                    if (musicPicker.selectedFile.toString()) opts.music = musicPicker.selectedFile.toString()
                    kcProjects.create(dialog.project, dialog.photos, opts)
                }
            }
            Button { text: "Cancel render"; enabled: kcProjects.busy; onClicked: kcProjects.cancel() }
            Button { text: "Close"; onClicked: dialog.close() }
        }
    }
}
