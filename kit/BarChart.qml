import QtQuick
import qs.Commons

// Columns with a readout line above and tick labels below. The widget gives
// it plain data and owns what the readout says:
//
//   values   - one number per column (heights are relative to the largest)
//   ticks    - one label per column, "" to leave it blank
//   current  - index lit by default (-1 for none); columns after it are faint
//   cursor   - index under the pointer or picked with the arrow keys (-1 for none)
//   title / detail - the readout for the lit column; `titleSample` and
//                    `detailSample` are the widest title and detail the chart
//                    can show (see the readout below)
//
// `columnHovered(index)` fires while the pointer moves over a column, `columnLeft()` when
// it leaves.
Item {
  id: chart

  required property QtObject look
  property var values: []
  property var ticks: []
  property int current: -1
  property int cursor: -1
  property string title: ""
  property string detail: ""
  property string titleSample: ""
  property string detailSample: ""
  property real plotHeight: Style.space(72)

  signal columnHovered(int index)
  signal columnLeft()

  readonly property int count: values.length
  readonly property real peak: {
    var max = 0
    for (var i = 0; i < values.length; i++) max = Math.max(max, Number(values[i]) || 0)
    return max
  }
  readonly property real gap: count > 14 ? Style.space(2) : Style.space(4)
  readonly property real columnWidth: count > 0 ? (width - gap * (count - 1)) / count : 0
  readonly property int shown: cursor >= 0 && cursor < count ? cursor : Math.min(current, count - 1)

  implicitHeight: readout.implicitHeight + Style.space(8) + plot.height + Style.space(4) + tickRow.height

  function columnAt(x) {
    return count > 0 ? Math.max(0, Math.min(count - 1, Math.floor(x / (columnWidth + gap)))) : -1
  }

  // The title and its figures share one line while the widest figures the
  // chart can show still fit beside the title; otherwise the figures drop to a
  // second line instead of being cut off. `titleSample` and `detailSample` are
  // the widest texts, so the layout does not jump while the pointer moves
  // across columns.
  Item {
    id: readout
    width: parent.width
    readonly property bool oneLine: titleSampleMetrics.width + Style.space(8) + sampleMetrics.width <= width
    implicitHeight: oneLine ? Math.max(titleText.implicitHeight, detailText.implicitHeight)
                            : titleText.implicitHeight + detailText.implicitHeight

    TextMetrics {
      id: titleSampleMetrics
      font.family: chart.look.fontFamily
      font.pixelSize: chart.look.small
      font.bold: true
      text: chart.titleSample !== "" ? chart.titleSample : chart.title
    }

    TextMetrics {
      id: sampleMetrics
      font.family: chart.look.fontFamily
      font.pixelSize: chart.look.small
      font.features: { "tnum": 1 }
      text: chart.detailSample !== "" ? chart.detailSample : chart.detail
    }

    Text {
      id: titleText
      width: Math.min(implicitWidth, parent.width)
      textFormat: Text.PlainText
      text: chart.title
      color: chart.look.ink
      font.family: chart.look.fontFamily
      font.pixelSize: chart.look.small
      font.bold: true
    }

    Text {
      id: detailText
      x: readout.oneLine ? parent.width - width : 0
      y: readout.oneLine ? 0 : titleText.height
      width: Math.min(implicitWidth, parent.width)
      textFormat: Text.PlainText
      text: chart.detail
      color: chart.look.dim
      font.family: chart.look.fontFamily
      font.pixelSize: chart.look.small
      font.features: { "tnum": 1 }
      elide: Text.ElideRight
    }
  }

  Item {
    id: plot
    anchors.top: readout.bottom
    anchors.topMargin: Style.space(8)
    width: parent.width
    height: chart.plotHeight

    Repeater {
      model: chart.values

      delegate: Item {
        required property var modelData
        required property int index
        readonly property bool lit: index === chart.shown
        // A column is born empty and grows once the chart has settled: while
        // `values` and `peak` update one after the other, a new column can
        // briefly be measured against the old peak and shoot to the top.
        property bool settled: false
        Component.onCompleted: Qt.callLater(function() { settled = true })

        x: index * (chart.columnWidth + chart.gap)
        width: chart.columnWidth
        height: plot.height

        Rectangle {
          anchors.fill: parent
          radius: Math.min(3, width / 2)
          // What is still ahead (hours not yet lived) is barely there.
          color: Util.alpha(chart.look.ink, parent.lit ? 0.14 : chart.current >= 0 && index > chart.current ? 0.04 : 0.08)
        }

        Rectangle {
          objectName: "bar"
          anchors.bottom: parent.bottom
          width: parent.width
          height: parent.settled && modelData > 0 && chart.peak > 0
                  ? Math.min(parent.height, Math.max(Style.space(2), parent.height * modelData / chart.peak)) : 0
          radius: Math.min(3, width / 2)
          // Both stay 3:1 graphics on the popup; the picked one is the stronger.
          color: parent.lit ? chart.look.accentText : chart.look.accentSoft

          Behavior on height { NumberAnimation { duration: chart.look.fade; easing.type: Easing.OutCubic } }
        }
      }
    }

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      onPositionChanged: function(mouse) { chart.columnHovered(chart.columnAt(mouse.x)) }
      onExited: chart.columnLeft()
    }
  }

  Item {
    id: tickRow
    anchors.top: plot.bottom
    anchors.topMargin: Style.space(4)
    width: parent.width
    height: tickMetrics.height

    TextMetrics { id: tickMetrics; font.family: chart.look.fontFamily; font.pixelSize: chart.look.small; text: "00" }

    Repeater {
      model: chart.ticks

      delegate: Text {
        required property string modelData
        required property int index
        readonly property real center: index * (chart.columnWidth + chart.gap) + chart.columnWidth / 2

        x: Math.max(0, Math.min(tickRow.width - implicitWidth, center - implicitWidth / 2))
        textFormat: Text.PlainText
        text: modelData
        color: index === chart.shown ? chart.look.ink : chart.look.dim
        font.family: chart.look.fontFamily
        font.pixelSize: chart.look.small
        font.features: { "tnum": 1 }
      }
    }
  }
}
