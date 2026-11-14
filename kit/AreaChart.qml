import QtQuick
import qs.Commons

// Recent history as lines: `series` = [{ values: [0..1], color, fill, dashed }],
// newest value at the right edge, `capacity` points across the width. Under
// the chart: `leftLabel` · the legend (each series' `label`) · `rightLabel`.
// Painting happens only when something changes, so a closed popup costs nothing.
Column {
  id: areaChart

  required property QtObject look
  property var series: []
  property int capacity: 200
  property real chartHeight: Style.space(72)
  property string leftLabel: ""
  property string rightLabel: ""

  spacing: Style.space(4)

  // false while nobody can see the chart (a closed popup): new values are
  // kept, the painting waits until it is live again.
  property bool live: true

  onSeriesChanged: if (live) canvas.requestPaint()
  onCapacityChanged: if (live) canvas.requestPaint()
  onLiveChanged: if (live) canvas.requestPaint()

  Canvas {
    id: canvas
    width: parent.width
    height: areaChart.chartHeight
    // Repaint on theme or size changes too.
    property color gridColor: areaChart.look.track
    onGridColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
      var ctx = getContext("2d")
      ctx.reset()
      var w = width, h = height
      ctx.strokeStyle = gridColor
      ctx.lineWidth = 1
      for (var g = 1; g <= 3; g++) {
        var gy = Math.round(h * g / 4) + 0.5
        ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke()
      }
      var step = w / Math.max(1, areaChart.capacity - 1)
      for (var s = 0; s < areaChart.series.length; s++) {
        var line = areaChart.series[s]
        var vals = line.values || []
        if (vals.length < 2) continue
        var first = vals.length - 1
        function px(i) { return w - (first - i) * step }
        function py(i) { return h - 1 - Math.max(0, Math.min(1, Number(vals[i]) || 0)) * (h - 2) }
        if (line.fill) {
          var grad = ctx.createLinearGradient(0, 0, 0, h)
          grad.addColorStop(0, Qt.rgba(line.color.r, line.color.g, line.color.b, 0.32))
          grad.addColorStop(1, Qt.rgba(line.color.r, line.color.g, line.color.b, 0.02))
          ctx.fillStyle = grad
          ctx.beginPath()
          ctx.moveTo(px(0), h)
          for (var i = 0; i < vals.length; i++) ctx.lineTo(px(i), py(i))
          ctx.lineTo(px(first), h)
          ctx.closePath()
          ctx.fill()
        }
        ctx.strokeStyle = line.color
        ctx.lineWidth = line.dashed ? 1.5 : 2
        ctx.setLineDash(line.dashed ? [3, 3] : [])
        ctx.beginPath()
        ctx.moveTo(px(0), py(0))
        for (var j = 1; j < vals.length; j++) ctx.lineTo(px(j), py(j))
        ctx.stroke()
        ctx.setLineDash([])
      }
    }
  }

  Item {
    width: parent.width
    implicitHeight: Math.max(left.implicitHeight, legend.implicitHeight)

    Text {
      id: left
      anchors.left: parent.left
      textFormat: Text.PlainText
      text: areaChart.leftLabel
      color: areaChart.look.dim
      font.family: areaChart.look.fontFamily
      font.pixelSize: areaChart.look.small
    }

    Row {
      id: legend
      anchors.horizontalCenter: parent.horizontalCenter
      spacing: Style.space(10)

      Repeater {
        model: areaChart.series

        delegate: Row {
          required property var modelData
          visible: !!modelData.label
          spacing: Style.space(4)

          Rectangle {
            width: Style.space(12)
            height: modelData.dashed ? 2 : 3
            color: modelData.color
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            textFormat: Text.PlainText
            text: modelData.label || ""
            color: areaChart.look.dim
            font.family: areaChart.look.fontFamily
            font.pixelSize: areaChart.look.small
          }
        }
      }
    }

    Text {
      anchors.right: parent.right
      textFormat: Text.PlainText
      text: areaChart.rightLabel
      color: areaChart.look.dim
      font.family: areaChart.look.fontFamily
      font.pixelSize: areaChart.look.small
    }
  }
}
