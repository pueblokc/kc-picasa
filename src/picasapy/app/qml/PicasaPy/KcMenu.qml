import QtQuick
import QtQuick.Controls

PicasaMenu {
    id: menu
    property var bar: null
    title: "&KC"
    KcShareMenu { bar: menu.bar }
    PicasaMenuItem {
        objectName: "kcOnThisDay"; text: "On This Day"; sajat: true; placeholder: false
        onTriggered: if (menu.bar && menu.bar.kcHostWindow) menu.bar.kcHostWindow.openKcOnThisDay()
    }
}
