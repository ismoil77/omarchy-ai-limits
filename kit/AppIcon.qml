import QtQuick
import qs.Commons
import "Contrast.js" as Contrast
import "Theme.js" as Theme

// An app's icon at `size`, or, while there is none (no `source`, or it fails
// to load), a rounded tile with the first letter of `name` in a theme colour
// that stays the same for that name.
Item {
  id: appIcon

  required property QtObject look
  property url source: ""
  property string name: ""
  property real size: Style.space(22)

  readonly property color tint: appIcon.look.onPopup(Theme.tintFor(name, look.themeColors, String(look.accent)), 3)

  implicitWidth: size
  implicitHeight: size

  Image {
    id: image
    anchors.fill: parent
    source: appIcon.source
    sourceSize: Qt.size(appIcon.size * 2, appIcon.size * 2)
    asynchronous: true
    smooth: true
    visible: status === Image.Ready
  }

  Rectangle {
    anchors.fill: parent
    visible: !image.visible
    radius: Math.round(appIcon.size * 0.28)
    color: appIcon.tint

    Text {
      anchors.centerIn: parent
      textFormat: Text.PlainText
      text: appIcon.name.replace(/^[^A-Za-zА-Яа-я0-9]+/, "").charAt(0).toUpperCase()
      color: Contrast.ensure("#ffffff", String(appIcon.tint), 3) === "#ffffff" ? "#ffffff" : "#000000"
      font.family: appIcon.look.fontFamily
      font.pixelSize: Math.round(appIcon.size * 0.55)
      font.bold: true
    }
  }
}
