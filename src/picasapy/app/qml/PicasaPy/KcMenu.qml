import QtQuick
import QtQuick.Controls

PicasaMenu {
    id: menu
    property var bar: null
    title: "&KC"
    KcShareMenu { bar: menu.bar }
    KcTextMenu {}
    KcProjectsMenu { bar: menu.bar }
    PicasaMenuItem {
        objectName: "kcSmartSearch"; text: "Smart Search..."; sajat: true; placeholder: false
        onTriggered: if (menu.bar && menu.bar.kcHostWindow) menu.bar.kcHostWindow.openKcSmartSearch()
    }
    PicasaMenuItem {
        objectName: "kcSmartIndex"; text: "AI: Update Photo Index"; sajat: true; placeholder: false
        onTriggered: kcSmart.updateIndex()
    }
    PicasaMenuItem {
        objectName: "kcSmartIndexing"; text: "AI indexing on"; checkable: true; sajat: true; placeholder: false
        checked: kcSmart.enabled
        onTriggered: kcSmart.setEnabled(checked)
    }
    PicasaMenuItem {
        text: "Reduce Motion"; checkable: true; sajat: true; placeholder: false
        checked: typeof kcUi !== "undefined" && kcUi && kcUi.reduceMotion
        onTriggered: kcUi.setReduceMotion(checked)
    }
    PicasaMenuItem {
        objectName: "kcOnThisDay"; text: "On This Day"; sajat: true; placeholder: false
        onTriggered: if (menu.bar && menu.bar.kcHostWindow) menu.bar.kcHostWindow.openKcOnThisDay()
    }
    PicasaMenuItem {
        objectName: "kcBackupNow"; text: "Back Up Index Now"; sajat: true; placeholder: false
        onTriggered: kcBackup.backupNow()
    }
    PicasaMenuItem {
        objectName: "kcRestoreIndex"; text: "Restore Index..."; sajat: true; placeholder: false
        onTriggered: if (menu.bar && menu.bar.kcHostWindow) menu.bar.kcHostWindow.openKcRestore()
    }
}
