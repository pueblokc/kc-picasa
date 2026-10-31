import QtQuick
import QtQuick.Controls

PicasaMenu {
    id: menu
    property var kcController: null
    Component.onCompleted: { try { kcController = kcUi } catch (e) {} }
    title: "Text Size"
    enabled: kcController !== null
    MenuItem { text: "Small 90 %"; checkable: true; checked: menu.kcController && menu.kcController.textScale === 0.9; onTriggered: menu.kcController.setTextScale(0.9) }
    MenuItem { text: "Normal 100 %"; checkable: true; checked: menu.kcController && menu.kcController.textScale === 1.0; onTriggered: menu.kcController.setTextScale(1.0) }
    MenuItem { text: "Large 115 %"; checkable: true; checked: menu.kcController && menu.kcController.textScale === 1.15; onTriggered: menu.kcController.setTextScale(1.15) }
    MenuItem { text: "Larger 130 %"; checkable: true; checked: menu.kcController && menu.kcController.textScale === 1.3; onTriggered: menu.kcController.setTextScale(1.3) }
    MenuItem { text: "Largest 150 %"; checkable: true; checked: menu.kcController && menu.kcController.textScale === 1.5; onTriggered: menu.kcController.setTextScale(1.5) }
}
