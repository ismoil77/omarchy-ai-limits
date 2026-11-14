import QtQuick
import qs.Commons

// A card with a CAPTION on the left and, on the right, either a quiet `hint`
// or controls put in `trailing`. Children stack below.
Rectangle {
  id: section

  required property QtObject look
  property string caption: ""
  property string hint: ""
  property color hintColor: look.dim
  property bool hintStrong: false
  property real padding: Style.space(12)
  property alias spacing: body.spacing
  property alias trailing: trailingRow.data
  default property alias content: body.data

  implicitHeight: column.implicitHeight + padding * 2
  radius: look.radius
  color: look.surface

  Column {
    id: column
    x: section.padding
    y: section.padding
    width: section.width - section.padding * 2
    spacing: Style.space(8)

    Item {
      visible: section.caption !== "" || section.hint !== "" || trailingRow.children.length > 0
      width: parent.width
      implicitHeight: Math.max(captionText.implicitHeight, hintText.implicitHeight, trailingRow.implicitHeight)

      Text {
        id: captionText
        anchors.left: parent.left
        anchors.right: trailingRow.children.length > 0 ? trailingRow.left : hintText.left
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: section.caption.toUpperCase()
        color: section.look.dim
        font.family: section.look.fontFamily
        font.pixelSize: section.look.small
        font.bold: true
        font.letterSpacing: 1.1
        elide: Text.ElideRight
      }

      Text {
        id: hintText
        visible: trailingRow.children.length === 0 && text !== ""
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: section.hint
        color: section.hintColor
        font.family: section.look.fontFamily
        font.pixelSize: section.hintStrong ? section.look.body : section.look.small
        font.bold: section.hintStrong
        font.features: { "tnum": 1 }
      }

      Row {
        id: trailingRow
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(4)
      }
    }

    Column {
      id: body
      width: parent.width
      spacing: Style.space(4)
    }
  }
}
