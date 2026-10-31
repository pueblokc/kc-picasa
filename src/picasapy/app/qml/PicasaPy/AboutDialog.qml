import QtQuick
import QtQuick.Controls

// Névjegy-dialógus (#150-ben kiemelve a Main.qml-ből): logó + verzió
// (appVersion → version.version_string()) + licenc-sor.
Dialog {
    title: qsTr("About KC Picasa")
    modal: true
    anchors.centerIn: parent
    standardButtons: Dialog.Ok
    Column {
        spacing: 10
        Image {
            anchors.horizontalCenter: parent.horizontalCenter
            // a qml/PicasaPy/ mappából az app/assets a két szinttel feljebb van
            source: Qt.resolvedUrl("../../assets/logo.svg")
            sourceSize.width: 320
            fillMode: Image.PreserveAspectFit
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: ((typeof kcUi !== "undefined" && kcUi)
                      ? "KC Picasa " + kcUi.version + "\n" : "KC Picasa\n")
                  + "© " + new Date().getFullYear() + " "
                  + ((typeof kcUi !== "undefined" && kcUi) ? kcUi.brandLabel : "KCCS · mypueblopc.com")
                  + "\n\nBased on PicasaPy " + appVersion + " — "
                  + qsTr("A modern, open Picasa successor.")
                  + "\nGPL-3.0 · github.com/sanchomuzax/PicasaPy"
                  + "\nFork: github.com/pueblokc/kc-picasa"
                  + "\n\nZoom: Ctrl+= bigger · Ctrl+- smaller · Ctrl+0 reset (View ▸ Zoom)"
                  + "\nKC: device sharing · On This Day · verified index backups"
            color: Theme.ink
            font.pixelSize: Theme.fontSize
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
