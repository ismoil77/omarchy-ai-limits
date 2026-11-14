import QtQuick
import qs.Commons

// A card with a caption, a big value, an optional meter and a detail line.
// `fraction` < 0 hides the meter; `mark` (0..1) draws a line on it, e.g. where
// a limit is. `action` adds a link-like button under the detail.
Card {
  id: tile

  property string caption: ""
  property string value: ""
  property color valueColor: look.ink
  property string detail: ""
  property real fraction: -1
  property real mark: -1
  property color fill: look.accentFill
  property string action: ""

  signal activated()

  spacing: Style.space(4)

  Text {
    width: parent.width
    textFormat: Text.PlainText
    text: tile.caption.toUpperCase()
    color: tile.look.dim
    font.family: tile.look.fontFamily
    font.pixelSize: tile.look.small
    font.letterSpacing: 0.8
    elide: Text.ElideRight
  }

  Text {
    width: parent.width
    textFormat: Text.PlainText
    text: tile.value
    color: tile.valueColor
    font.family: tile.look.fontFamily
    font.pixelSize: tile.look.big
    font.bold: true
    font.features: { "tnum": 1 }
    elide: Text.ElideRight
  }

  Item {
    visible: tile.fraction >= 0
    width: parent.width
    height: Style.space(6)

    Rectangle {
      anchors.fill: parent
      radius: height / 2
      color: tile.look.track
    }

    Rectangle {
      height: parent.height
      radius: height / 2
      width: parent.width * Math.max(0, Math.min(1, tile.fraction))
      color: tile.fill

      Behavior on width { NumberAnimation { duration: tile.look.fade; easing.type: Easing.OutCubic } }
      Behavior on color { ColorAnimation { duration: tile.look.fade } }
    }

    // The limit: a tick that stands out above and below the track.
    Rectangle {
      visible: tile.mark >= 0 && tile.mark <= 1
      x: Math.round(parent.width * tile.mark) - width / 2
      y: -Style.space(2)
      width: 2
      height: parent.height + Style.space(4)
      color: tile.look.ink
    }
  }

  Text {
    visible: text !== ""
    width: parent.width
    textFormat: Text.PlainText
    text: tile.detail
    color: tile.look.dim
    font.family: tile.look.fontFamily
    font.pixelSize: tile.look.small
    wrapMode: Text.WordWrap
  }

  Text {
    visible: text !== ""
    textFormat: Text.PlainText
    text: tile.action
    color: tile.look.accentText
    font.family: tile.look.fontFamily
    font.pixelSize: tile.look.small
    font.bold: true
    font.underline: actionArea.containsMouse

    MouseArea {
      id: actionArea
      anchors.fill: parent
      anchors.margins: -Style.space(4)
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: tile.activated()
    }
  }
}
