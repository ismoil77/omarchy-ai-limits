import QtQuick
import qs.Commons

// A raised, rounded surface that stacks its children in a column.
Rectangle {
  id: card

  required property QtObject look
  property real padding: Style.space(12)
  property alias spacing: inner.spacing
  default property alias content: inner.data

  implicitHeight: inner.implicitHeight + padding * 2
  radius: look.radius
  color: look.surface

  Column {
    id: inner
    x: card.padding
    y: card.padding
    width: card.width - card.padding * 2
    spacing: Style.space(6)
  }
}
