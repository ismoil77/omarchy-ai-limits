import QtQuick
import qs.Commons

// "More 3" / "Less" under a cut list. Hidden while `text` is empty.
Text {
  id: more

  required property QtObject look
  signal clicked()

  visible: text !== ""
  leftPadding: Style.space(6)
  topPadding: Style.space(2)
  bottomPadding: Style.space(2)
  textFormat: Text.PlainText
  color: area.containsMouse ? look.accentText : look.dim
  font.family: look.fontFamily
  font.pixelSize: look.small
  font.underline: area.containsMouse

  MouseArea {
    id: area
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: more.clicked()
  }
}
