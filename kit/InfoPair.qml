import QtQuick
import qs.Commons

// A label on the left and a value on the right; the label gives way when tight.
Item {
  id: pair

  required property QtObject look
  property string label: ""
  property string value: ""
  property color valueColor: look.ink

  width: parent ? parent.width : 0
  implicitHeight: Math.max(labelText.implicitHeight, valueText.implicitHeight)

  Text {
    id: labelText
    anchors.left: parent.left
    anchors.right: valueText.left
    anchors.rightMargin: Style.space(8)
    textFormat: Text.PlainText
    text: pair.label
    color: pair.look.dim
    font.family: pair.look.fontFamily
    font.pixelSize: pair.look.small
    elide: Text.ElideRight
  }

  Text {
    id: valueText
    anchors.right: parent.right
    textFormat: Text.PlainText
    text: pair.value
    color: pair.valueColor
    font.family: pair.look.fontFamily
    font.pixelSize: pair.look.small
    font.features: { "tnum": 1 }
  }
}
