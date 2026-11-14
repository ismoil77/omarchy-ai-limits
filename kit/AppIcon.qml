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

  // The first letter or digit in any script: a letter has two cases, or is
  // above ASCII (CJK has no case); punctuation and spaces are skipped.
  readonly property string initial: {
    var chars = Array.from(String(name))
    for (var i = 0; i < chars.length; i++) {
      var c = chars[i]
      if (/[0-9]/.test(c) || c.toLowerCase() !== c.toUpperCase() || c.codePointAt(0) > 0x2FFF) return c.toUpperCase()
    }
    return ""
  }
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
      text: appIcon.initial
      color: Contrast.ensure("#ffffff", String(appIcon.tint), 3) === "#ffffff" ? "#ffffff" : "#000000"
      font.family: appIcon.look.fontFamily
      font.pixelSize: Math.round(appIcon.size * 0.55)
      font.bold: true
    }
  }
}
