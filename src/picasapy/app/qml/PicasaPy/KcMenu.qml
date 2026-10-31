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
    PicasaMenuItem {
        objectName: "kcBackupNow"; text: "Back Up Index Now"; sajat: true; placeholder: false
        onTriggered: kcBackup.backupNow()
    }
    PicasaMenuItem {
        objectName: "kcRestoreIndex"; text: "Restore Index..."; sajat: true; placeholder: false
        onTriggered: if (menu.bar && menu.bar.kcHostWindow) menu.bar.kcHostWindow.openKcRestore()
    }
}
