import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

KcDialog {
    id: dialog
    objectName: "kcSmartSearchDialog"
    modal: true
    title: "Smart Search"
    width: 780
    height: 640
    anchors.centerIn: parent
    contentItem: ColumnLayout {
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            KcTextField {
                id: query
                objectName: "kcSmartQuery"
                Layout.fillWidth: true
                placeholderText: "Describe a photo..."
                onAccepted: kcSmart.search(text)
            }
            KcButton { text: "Search"; accent: true; onClicked: kcSmart.search(query.text) }
        }
        Text { text: "Try: dog, Halloween, birthday cake, snow, red truck"; color: Theme.textGray; font.pixelSize: 12 }
        Text { text: kcSmart ? kcSmart.status : ""; color: Theme.ink }
        GridView {
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            cellWidth: 146; cellHeight: 174
            model: kcSmart ? kcSmart.results : []
            delegate: Rectangle {
                width: 138; height: 166; color: Theme.chromeBg; radius: 5
                border.color: Theme.chromeBorder
                Column {
                    anchors.fill: parent; anchors.margins: 4; spacing: 3
                    Image { source: modelData.url; width: 130; height: 130; sourceSize.width: 130; sourceSize.height: 130; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                    Row {
                        width: parent.width; spacing: 4
                        Text { text: modelData.name; color: Theme.ink; elide: Text.ElideRight; width: parent.width - scoreLabel.width - 4; font.pixelSize: 11 }
                        Text { id: scoreLabel; text: modelData.score + "%"; color: Theme.textGray; font.pixelSize: 10 }
                    }
                }
                TapHandler { acceptedButtons: Qt.LeftButton; onDoubleTapped: fileOpsController.openPhoto(modelData.path) }
                TapHandler { acceptedButtons: Qt.RightButton; onTapped: similarMenu.popup() }
                KcPopupMenu {
                    id: similarMenu
                    PicasaMenuItem { text: "Find Similar"; sajat: true; kc: true; onTriggered: kcSmart.similar(modelData.path) }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            KcButton { text: "Update Index"; onClicked: kcSmart.updateIndex() }
            KcButton { text: "Cancel Indexing"; enabled: kcSmart && kcSmart.indexing; onClicked: kcSmart.cancel() }
            Item { Layout.fillWidth: true }
            KcButton { text: "Close"; onClicked: dialog.close() }
        }
    }
}
