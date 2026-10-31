import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "kcSmartSearchDialog"
    modal: true
    title: "Smart Search"
    width: 780
    height: 640
    anchors.centerIn: parent
    background: Rectangle { color: "#151b1f"; border.color: "#28323a"; radius: 10 }
    contentItem: ColumnLayout {
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            TextField {
                id: query
                objectName: "kcSmartQuery"
                Layout.fillWidth: true
                placeholderText: "Describe a photo..."
                onAccepted: kcSmart.search(text)
            }
            Button { text: "Search"; onClicked: kcSmart.search(query.text) }
        }
        Text { text: kcSmart.status; color: "#cfc9bb" }
        GridView {
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            cellWidth: 150; cellHeight: 150
            model: kcSmart.results
            delegate: Rectangle {
                width: 142; height: 142; color: "#1c2328"; radius: 5
                Column {
                    anchors.fill: parent; spacing: 4
                    Image { source: modelData.url; width: parent.width; height: 104; fillMode: Image.PreserveAspectCrop; asynchronous: true }
                    Text { text: modelData.name + "  " + modelData.score + "%"; color: "#cfc9bb"; elide: Text.ElideRight; width: parent.width }
                }
                TapHandler { onTapped: { controller.selectFolder(modelData.folder); dialog.close() } }
                TapHandler { acceptedButtons: Qt.RightButton; onTapped: kcSmart.similar(modelData.path) }
                Button { text: "Similar"; anchors.right: parent.right; anchors.top: parent.top; onClicked: kcSmart.similar(modelData.path) }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Button { text: "Update Index"; onClicked: kcSmart.updateIndex() }
            Button { text: "Cancel Indexing"; enabled: kcSmart.indexing; onClicked: kcSmart.cancel() }
            Item { Layout.fillWidth: true }
            Button { text: "Close"; onClicked: dialog.close() }
        }
    }
}
