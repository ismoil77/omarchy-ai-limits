import QtQuick
import qs.Commons

// Buttons side by side, sharing the width evenly and one height.
Row {
  id: actionRow
  spacing: Style.space(6)

  readonly property var shown: {
    var out = []
    // A Repeater is a child too but no cell: only what it makes counts.
    for (var i = 0; i < children.length; i++) if (children[i].visible && children[i].delegate === undefined) out.push(children[i])
    return out
  }
  readonly property real cell: shown.length > 0 ? (width - spacing * (shown.length - 1)) / shown.length : 0
  readonly property real tallest: {
    var h = 0
    for (var i = 0; i < shown.length; i++) h = Math.max(h, shown[i].implicitHeight)
    return h
  }
  height: tallest

  function fit() {
    for (var i = 0; i < shown.length; i++) {
      shown[i].width = cell
      shown[i].height = tallest
    }
  }
  onShownChanged: fit()
  onCellChanged: fit()
  onTallestChanged: fit()
  Component.onCompleted: fit()
}
