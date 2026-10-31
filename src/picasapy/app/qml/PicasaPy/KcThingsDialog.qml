import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

KcDialog {
    id: dialog
    objectName: "kcThingsDialog"
    title: "Things"
    modal: true
    width: 780
    height: 640
    anchors.centerIn: parent
    property string selectedTag: ""
    contentItem: ColumnLayout {
        spacing: 10
        Text { text: "Explore your photos by subject"; color: Theme.ink }
        ScrollView {
            Layout.fillWidth: true; Layout.preferredHeight: 150
            clip: true
            Flow {
                width: dialog.availableWidth - 20; spacing: 7
                Repeater {
                model: kcSmart ? kcSmart.things : []
                delegate: KcButton {
                    required property var modelData
                    text: modelData.tag + "  " + modelData.count
                    accent: dialog.selectedTag === modelData.tag
                    onClicked: {
                        dialog.selectedTag = modelData.tag
                        kcSmart.showThing(modelData.tag)
                    }
                }
                }
            }
        }
        Text { text: dialog.selectedTag ? kcSmart.status : "Choose a subject"; color: Theme.textGray }
        GridView {
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true; cellWidth: 146; cellHeight: 174
            model: dialog.selectedTag && kcSmart ? kcSmart.results : []
            delegate: Rectangle {
                width: 138; height: 166; radius: 5
                color: Theme.chromeBg; border.color: Theme.chromeBorder
                Column {
                    anchors.fill: parent; anchors.margins: 4; spacing: 3
                    Image { width: 130; height: 130; source: modelData.url; sourceSize.width: 130; sourceSize.height: 130; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                    Text { width: parent.width; text: modelData.name; color: Theme.ink; font.pixelSize: 11; elide: Text.ElideRight }
                }
                TapHandler { acceptedButtons: Qt.LeftButton; onDoubleTapped: fileOpsController.openPhoto(modelData.path) }
            }
        }
        KcButton { text: "Close"; Layout.alignment: Qt.AlignRight; onClicked: dialog.close() }
    }
}
