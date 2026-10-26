import QtQuick
import qs.Commons

// One line of a ranked list: a name, then right-aligned cells, with the row's
// `share` of the whole painted behind it. `cells` are ready-made strings;
// `cellWidths` come from the list so the columns line up across rows, and
// `dimCells[i]` greys a cell out.
Item {
  id: row

  required property QtObject look
  property string name: ""
  property var cells: []
  property var cellWidths: []
  property var dimCells: []
  property real share: 0
  property bool highlighted: false
  property bool clickable: false

  signal clicked()

  readonly property real cellsWidth: {
    var sum = 0
    for (var i = 0; i < cellWidths.length; i++) sum += cellWidths[i] + content.spacing
    return sum
  }

  implicitHeight: content.implicitHeight + Style.space(4)

  Rectangle {
    anchors.fill: parent
    visible: row.highlighted || area.containsMouse
    radius: Math.min(4, Style.cornerRadius)
    color: Util.alpha(row.look.ink, row.highlighted ? 0.12 : 0.06)
  }

  Rectangle {
    anchors.left: parent.left
    anchors.top: parent.top
    anchors.bottom: parent.bottom
    width: parent.width * Math.max(0, Math.min(1, row.share))
    radius: Math.min(4, Style.cornerRadius)
    color: Util.alpha(row.look.accentFill, 0.22)

    Behavior on width { NumberAnimation { duration: row.look.fade; easing.type: Easing.OutCubic } }
  }

  Row {
    id: content
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.leftMargin: Style.space(6)
    anchors.rightMargin: Style.space(6)
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.space(8)

    Text {
      width: Math.max(0, parent.width - row.cellsWidth)
      textFormat: Text.PlainText
      text: row.name
      color: row.look.ink
      font.family: row.look.fontFamily
      font.pixelSize: row.look.small
      font.bold: row.highlighted
      elide: Text.ElideRight
    }

    Repeater {
      model: row.cells

      delegate: Text {
        required property string modelData
        required property int index
        width: row.cellWidths[index] || 0
        horizontalAlignment: Text.AlignRight
        textFormat: Text.PlainText
        text: modelData
        color: row.dimCells[index] ? row.look.dim : row.look.ink
        font.family: row.look.fontFamily
        font.pixelSize: row.look.small
        font.features: { "tnum": 1 }
      }
    }
  }

  MouseArea {
    id: area
    anchors.fill: parent
    enabled: row.clickable
    hoverEnabled: row.clickable
    cursorShape: row.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
    onClicked: row.clicked()
  }
}
