import QtQuick
import QtQuick.Controls

PicasaMenu {
    id: menu
    property var kcController: null
    Component.onCompleted: { try { kcController = kcUi } catch (e) {} }
    title: "Text Size"
    enabled: kcController !== null
    PicasaMenuItem { text: "Small 90 %"; sajat: true; placeholder: false; checkable: true; checked: !!menu.kcController && menu.kcController.textScale === 0.9; onTriggered: menu.kcController.setTextScale(0.9) }
    PicasaMenuItem { text: "Normal 100 %"; sajat: true; placeholder: false; checkable: true; checked: !!menu.kcController && menu.kcController.textScale === 1.0; onTriggered: menu.kcController.setTextScale(1.0) }
    PicasaMenuItem { text: "Large 115 %"; sajat: true; placeholder: false; checkable: true; checked: !!menu.kcController && menu.kcController.textScale === 1.15; onTriggered: menu.kcController.setTextScale(1.15) }
    PicasaMenuItem { text: "Larger 130 %"; sajat: true; placeholder: false; checkable: true; checked: !!menu.kcController && menu.kcController.textScale === 1.3; onTriggered: menu.kcController.setTextScale(1.3) }
    PicasaMenuItem { text: "Largest 150 %"; sajat: true; placeholder: false; checkable: true; checked: !!menu.kcController && menu.kcController.textScale === 1.5; onTriggered: menu.kcController.setTextScale(1.5) }
}
