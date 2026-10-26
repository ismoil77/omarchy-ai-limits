import QtQuick
import qs.Commons

// A thin horizontal meter: `fraction` (0..1) of the track is filled, from the
// left or, with `fromRight`, from the right.
Rectangle {
  id: meter

  required property QtObject look
  property real fraction: 0
  property bool fromRight: false
  property color fill: look.accentFill

  height: Style.space(6)
  radius: height / 2
  color: look.track

  Rectangle {
    anchors.right: meter.fromRight ? parent.right : undefined
    height: parent.height
    radius: parent.radius
    width: parent.width * Math.max(0, Math.min(1, meter.fraction))
    color: meter.fill

    Behavior on width { NumberAnimation { duration: meter.look.fade; easing.type: Easing.OutCubic } }
  }
}
