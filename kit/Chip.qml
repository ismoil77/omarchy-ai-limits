import QtQuick
import qs.Commons

// A status pill: a dot and a word, tinted by `tone` (a graphic colour) with
// `toneText` for the word, e.g. look.good / look.goodText.
Rectangle {
  id: chip

  required property QtObject look
  property string text: ""
  property color tone: look.good
  property color toneText: look.goodText

  visible: text !== ""
  implicitWidth: row.implicitWidth + Style.space(16)
  implicitHeight: row.implicitHeight + Style.space(6)
  radius: height / 2
  color: Util.alpha(tone, 0.16)

  Behavior on color { ColorAnimation { duration: chip.look.fade } }

  Row {
    id: row
    anchors.centerIn: parent
    spacing: Style.space(6)

    Rectangle {
      width: Style.space(7)
      height: width
      radius: width / 2
      color: chip.tone
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      textFormat: Text.PlainText
      text: chip.text
      color: chip.toneText
      font.family: chip.look.fontFamily
      font.pixelSize: chip.look.small
      font.bold: true
    }
  }
}
