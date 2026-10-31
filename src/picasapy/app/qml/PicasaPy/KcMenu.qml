import QtQuick
import QtQuick.Controls

PicasaMenu {
    id: menu
    property var bar: null
    title: "&KC"
    KcShareMenu { bar: menu.bar }
}
