import QtQuick
import qs.Commons

// The top of every popup in the family: a glyph in a square tinted with the
// state, the widget's NAME, one big figure, what is going on in words, and a
// status chip. `tone`/`toneText` are a level's graphic and text colours.
Item {
  id: header

  required property QtObject look
  property string glyph: ""
  property string name: ""
  property string value: ""
  property string say: ""
  property color sayColor: look.dim
  property string chip: ""
  property color tone: look.accentFill
  property color toneText: look.accentText

  implicitHeight: Math.max(mark.height, labels.implicitHeight)

  Rectangle {
    id: mark
    width: Math.round(header.look.hero * 1.75)
    height: width
    radius: Math.round(width * 0.27)
    color: Util.alpha(header.tone, 0.15)
    border.width: 1.5
    border.color: Util.alpha(header.tone, 0.45)
    anchors.left: parent.left
    anchors.verticalCenter: parent.verticalCenter

    Behavior on color { ColorAnimation { duration: header.look.fade } }

    Text {
      anchors.centerIn: parent
      textFormat: Text.PlainText
      text: header.glyph
      color: header.toneText
      font.family: header.look.fontFamily
      font.pixelSize: header.look.hero
    }
  }

  Column {
    id: labels
    anchors.left: mark.right
    anchors.leftMargin: Style.space(12)
    anchors.right: chipItem.visible ? chipItem.left : parent.right
    anchors.rightMargin: chipItem.visible ? Style.space(8) : 0
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.space(1)

    Text {
      width: parent.width
      textFormat: Text.PlainText
      text: header.name.toUpperCase()
      color: header.look.dim
      font.family: header.look.fontFamily
      font.pixelSize: header.look.small
      font.bold: true
      font.letterSpacing: 1.4
      elide: Text.ElideRight
    }

    Text {
      visible: text !== ""
      width: parent.width
      textFormat: Text.PlainText
      text: header.value
      color: header.look.ink
      font.family: header.look.fontFamily
      font.pixelSize: header.look.heroLarge
      font.bold: true
      font.features: { "tnum": 1 }
      elide: Text.ElideRight
    }

    Text {
      visible: text !== ""
      width: parent.width
      textFormat: Text.PlainText
      text: header.say
      color: header.sayColor
      font.family: header.look.fontFamily
      font.pixelSize: header.look.small
      wrapMode: Text.WordWrap
    }
  }

  Chip {
    id: chipItem
    look: header.look
    text: header.chip
    tone: header.tone
    toneText: header.toneText
    anchors.right: parent.right
    anchors.top: labels.top
  }
}
