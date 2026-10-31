import QtQuick
import QtQuick.Controls

KcPopupMenu {
    id: menu
    property var bar: null
    title: "KC Projects"
    function openProject(kind) {
        if (bar && bar.kcHostWindow) bar.kcHostWindow.openKcProject(kind)
    }
    PicasaMenuItem { text: "Photo Reel..."; sajat: true; kc: true; placeholder: false; onTriggered: menu.openProject("reel") }
    PicasaMenuItem { text: "Animated Loop (GIF)..."; sajat: true; kc: true; placeholder: false; onTriggered: menu.openProject("animate") }
    PicasaMenuItem { text: "Frame / Card..."; sajat: true; kc: true; placeholder: false; onTriggered: menu.openProject("frames") }
    PicasaMenuItem { text: "Photo Calendar..."; sajat: true; kc: true; placeholder: false; onTriggered: menu.openProject("calendar") }
    PicasaMenuItem { text: "Photo Book..."; sajat: true; kc: true; placeholder: false; onTriggered: menu.openProject("photobook") }
    PicasaMenuItem { text: "Before / After..."; sajat: true; kc: true; placeholder: false; onTriggered: menu.openProject("beforeafter") }
    PicasaMenuItem { text: "Photo Mosaic..."; sajat: true; kc: true; placeholder: false; onTriggered: menu.openProject("mosaic") }
    PicasaMenuItem { text: "Year in Review..."; sajat: true; kc: true; placeholder: false; onTriggered: menu.openProject("yearreview") }
}
