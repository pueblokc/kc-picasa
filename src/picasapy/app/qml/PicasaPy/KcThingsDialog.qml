import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "kcThingsDialog"
    title: "Things"
    modal: true
    width: 420
    height: 540
    anchors.centerIn: parent
    background: Rectangle { color: "#151b1f"; border.color: "#4d8f85"; radius: 9 }
    contentItem: ColumnLayout {
        Text { text: "Explore your photos by subject"; color: "#cfc9bb" }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true
            ListView {
                model: kcSmart.things
                delegate: Button {
                    required property var modelData
                    width: ListView.view.width
                    text: modelData.tag + "   " + modelData.count
                    onClicked: {
                        kcSmart.showThing(modelData.tag)
                        dialog.close()
                        window.openKcSmartSearch()
                    }
                }
            }
        }
        Button { text: "Close"; onClicked: dialog.close() }
    }
}
