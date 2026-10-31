import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    implicitWidth: 130; implicitHeight: 36
    leftPadding: 10; rightPadding: 28
    contentItem: Text {
        text: control.displayText; color: Theme.ink
        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
    }
    indicator: Text {
        text: "▾"; color: Theme.ink
        anchors.right: parent.right; anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
    }
    background: Rectangle { color: Theme.contentPanel; border.color: Theme.chromeBorder; border.width: 1; radius: 5 }
    delegate: ItemDelegate {
        id: option
        width: control.width
        text: modelData
        contentItem: Text { text: option.text; color: Theme.ink; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { color: option.highlighted ? "#31564f" : Theme.chromeBg }
    }
    popup: Popup {
        y: control.height; width: control.width
        padding: 1
        contentItem: ListView { implicitHeight: contentHeight; model: control.popup.visible ? control.delegateModel : null; currentIndex: control.highlightedIndex; clip: true }
        background: Rectangle { color: Theme.chromeBg; border.color: Theme.chromeBorder; border.width: 1; radius: 5 }
    }
}
