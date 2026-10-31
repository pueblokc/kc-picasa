import QtQuick
import QtQuick.Controls

PicasaMenu {
    id: shareMenu
    property var bar: null
    property var hostWindow: bar && bar.kcHostWindow ? bar.kcHostWindow : null
    title: "Share to my devices"
    function paths() { return hostWindow ? hostWindow.photoActionPaths() : [] }
    PicasaMenuItem {
        text: "Send to Phone"; objectName: "kcSendPhone"; sajat: true; placeholder: false
        enabled: kcTools.configured("phone") && shareMenu.paths().length > 0
        ToolTip.text: enabled ? "" : "Set up in kc-share.json"
        onTriggered: kcTools.share("phone", shareMenu.paths())
    }
    PicasaMenuItem {
        text: "Put on Drop"; objectName: "kcPutDrop"; sajat: true; placeholder: false
        enabled: kcTools.configured("drop") && shareMenu.paths().length > 0
        ToolTip.text: enabled ? "" : "Set up in kc-share.json"
        onTriggered: kcTools.share("drop", shareMenu.paths())
    }
    PicasaMenuItem {
        text: "Get Share Link"; objectName: "kcGetLink"; sajat: true; placeholder: false
        enabled: kcTools.configured("link") && shareMenu.paths().length > 0
        ToolTip.text: enabled ? "" : "Set up in kc-share.json"
        onTriggered: kcTools.share("link", shareMenu.paths())
    }
}
