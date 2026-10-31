import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "kcOnThisDayDialog"
    property var photos: []
    modal: true
    title: "On This Day"
    width: 620
    height: 570
    anchors.centerIn: parent
    onAboutToShow: photos = kcMemories.today()
    background: Rectangle { color: "#151b1f"; border.color: "#28323a"; radius: 10 }
    contentItem: ColumnLayout {
        spacing: 12
        Text { text: "On This Day"; color: "#cfc9bb"; font.pixelSize: 22 }
        Text { text: "No photos from this day yet."; color: "#cfc9bb"; visible: dialog.photos.length === 0 }
        ListView {
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            model: dialog.photos
            delegate: Column {
                width: ListView.view.width
                spacing: 6
                Text {
                    visible: index === 0 || modelData.year !== dialog.photos[index - 1].year
                    text: modelData.yearsAgo + (modelData.yearsAgo === 1 ? " year ago — " : " years ago — ") + modelData.year
                    color: "#4d8f85"; font.pixelSize: 17
                }
                Row {
                    spacing: 12
                    Image { source: modelData.url; width: 74; height: 58; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                    Text { text: modelData.name; color: "#cfc9bb"; anchors.verticalCenter: parent.verticalCenter }
                }
                TapHandler {
                    onTapped: {
                        controller.selectFolder(modelData.folder)
                        dialog.close()
                    }
                }
            }
        }
        Button { text: "Close"; onClicked: dialog.close(); Layout.alignment: Qt.AlignRight }
    }
}
