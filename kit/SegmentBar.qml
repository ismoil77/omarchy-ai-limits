import QtQuick
import qs.Commons

// What a whole is made of: one bar split into `segments`
// ([{ value, color, label, text }]) and a legend under it. Values are summed;
// a segment of 0 takes no room.
Column {
  id: segmentBar

  required property QtObject look
  property var segments: []

  readonly property real total: {
    var s = 0
    for (var i = 0; i < segments.length; i++) s += Math.max(0, Number(segments[i].value) || 0)
    return s
  }
  readonly property real gap: 2

  spacing: Style.space(6)

  Item {
    width: parent.width
    height: Style.space(12)

    Row {
      id: bars
      anchors.fill: parent
      spacing: segmentBar.gap

      Repeater {
        model: segmentBar.segments

        delegate: Rectangle {
          required property var modelData
          readonly property real share: segmentBar.total > 0 ? Math.max(0, Number(modelData.value) || 0) / segmentBar.total : 0
          visible: share > 0
          height: bars.height
          width: Math.max(2, share * (bars.width - segmentBar.gap * (segmentBar.segments.length - 1)))
          radius: 3
          color: modelData.color

          Behavior on width { NumberAnimation { duration: segmentBar.look.fade; easing.type: Easing.OutCubic } }
        }
      }
    }
  }

  Flow {
    width: parent.width
    spacing: Style.space(12)

    Repeater {
      model: segmentBar.segments

      delegate: Row {
        required property var modelData
        spacing: Style.space(5)

        Rectangle {
          width: Style.space(9)
          height: width
          radius: 2
          color: modelData.color
          anchors.verticalCenter: parent.verticalCenter
        }

        Text {
          textFormat: Text.PlainText
          text: modelData.label + (modelData.text ? " " + modelData.text : "")
          color: segmentBar.look.ink
          font.family: segmentBar.look.fontFamily
          font.pixelSize: segmentBar.look.small
        }
      }
    }
  }
}
