import QtQuick
import qs.Commons

// Buttons (or any children) side by side that line up: every visible child gets the same width
// and the height of the tallest one. Give the row a width. It sets its
// children's width and height itself, so do not bind those on a child. A
// hidden child gives its room to the others; a Repeater's items count, the
// Repeater does not.
Row {
  id: evenRow
  spacing: Style.space(6)

  // `visible` of a child is false while any ancestor is hidden: a closed
  // popup has nothing shown, and nothing is resized until it opens.
  readonly property var shown: {
    var out = []
    for (var i = 0; i < children.length; i++) if (children[i].visible && children[i].delegate === undefined) out.push(children[i])
    return out
  }
  readonly property real cell: shown.length > 0 ? Math.max(0, (width - spacing * (shown.length - 1)) / shown.length) : 0
  readonly property real tallest: {
    var h = 0
    for (var i = 0; i < shown.length; i++) h = Math.max(h, shown[i].implicitHeight)
    return h
  }

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
