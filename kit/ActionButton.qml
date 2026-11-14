import QtQuick
import qs.Commons
import "Contrast.js" as Contrast

// The family's button. `primary` is the one thing to do: filled with the
// accent; the others are outlined. `selected` marks a picked option;
// `danger` (stop, delete) is outlined in the urgent colour.
Rectangle {
  id: action

  required property QtObject look
  property string text: ""
  property string iconText: ""
  property bool primary: false
  property bool selected: false
  property bool danger: false
  property bool compact: false
  signal clicked()

  readonly property color fillColor: primary ? look.accentFill : selected ? look.ink : "transparent"
  readonly property color labelColor: primary || selected
    ? Qt.color(Contrast.ensure("#ffffff", String(fillColor), 4.5) === "#ffffff" ? "#ffffff" : "#000000")
    : danger ? look.badText : look.ink

  // Sizes come from measured text, never from the laid-out row: the label
  // elides to the button's width, so the width must not depend on the label.
  readonly property real iconWidth: iconText !== "" ? iconMetrics.width + Style.space(6) : 0
  readonly property real pad: Style.space(compact ? 14 : 20)
  implicitWidth: iconWidth + labelMetrics.width + pad
  implicitHeight: Math.max(labelMetrics.height, iconMetrics.height) + Style.space(compact ? 4 : 12)

  TextMetrics { id: labelMetrics; text: action.text; font.family: action.look.fontFamily; font.pixelSize: action.look.small; font.bold: true }
  TextMetrics { id: iconMetrics; text: action.iconText || " "; font.family: action.look.fontFamily; font.pixelSize: action.look.body }
  radius: Math.round(Style.space(compact ? 6 : 8))
  color: area.containsMouse && !primary && !selected ? look.surfaceHover : fillColor
  border.width: primary ? 0 : 1.5
  border.color: selected ? look.ink : danger ? look.badText : Util.alpha(look.ink, 0.75)
  opacity: enabled ? (area.pressed ? 0.8 : 1) : 0.45

  Behavior on color { ColorAnimation { duration: 120 } }

  Row {
    id: row
    anchors.centerIn: parent
    spacing: Style.space(6)

    Text {
      visible: action.iconText !== ""
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: action.iconText
      color: action.labelColor
      font.family: action.look.fontFamily
      font.pixelSize: action.look.body
    }

    Text {
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: action.text
      color: action.labelColor
      font.family: action.look.fontFamily
      font.pixelSize: action.look.small
      font.bold: true
      elide: Text.ElideRight
      width: Math.max(0, Math.min(labelMetrics.width + 1, action.width - action.pad - action.iconWidth))
    }
  }

  MouseArea {
    id: area
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: action.clicked()
  }
}
