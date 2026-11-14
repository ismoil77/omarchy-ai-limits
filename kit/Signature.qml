import QtQuick
import qs.Commons

// The family's last line: "ismoil · memory" and anything to add, version on the right.
Item {
  id: signature

  required property QtObject look
  property string widget: ""
  property string extra: ""
  property string version: ""

  implicitHeight: left.implicitHeight

  Text {
    id: left
    anchors.left: parent.left
    anchors.right: right.left
    anchors.rightMargin: Style.space(8)
    textFormat: Text.PlainText
    text: "ismoil · " + signature.widget.toLowerCase() + (signature.extra ? " · " + signature.extra : "")
    color: signature.look.dim
    font.family: signature.look.fontFamily
    font.pixelSize: signature.look.small
    font.letterSpacing: 0.6
    elide: Text.ElideRight
    opacity: 0.8
  }

  Text {
    id: right
    anchors.right: parent.right
    textFormat: Text.PlainText
    text: signature.version
    color: signature.look.dim
    font.family: signature.look.fontFamily
    font.pixelSize: signature.look.small
    opacity: 0.8
  }
}
