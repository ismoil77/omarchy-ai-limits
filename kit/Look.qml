import QtQuick
import qs.Commons
import "Contrast.js" as Contrast

// How a widget's popup looks, in one place: colours held to WCAG contrast on
// the popup background, a type scale with a legibility floor that follows the
// user's `textSize`, and the animation switch. Components in this folder take
// a Look instead of a dozen loose properties.
//
//   Look { id: look; textSize: setting("textSize", "Normal"); animations: setting("animations", true) !== false }
Item {
  id: look
  visible: false
  width: 0
  height: 0

  // "Normal" | "Large" | "Extra large" (any case).
  property string textSize: "Normal"
  property bool animations: true
  property string fontFamily: Style.font.family
  // The theme's accent as it arrives; `accentText` and `accentFill` are held to contrast.
  property color accent: Color.accent
  property color urgent: Color.urgent

  readonly property real textScale: {
    var v = String(textSize).toLowerCase()
    return v.indexOf("extra") === 0 ? 1.5 : v === "large" ? 1.25 : 1
  }
  readonly property bool motion: animations
  readonly property int fade: motion ? 240 : 0

  // Type scale: the user's shell size, never below `floor`, then scaled.
  function px(base, floor) { return Math.round(Math.max(base, floor) * textScale) }
  readonly property int small: px(Style.font.body, 13)
  readonly property int body: px(Style.font.subtitle, 14)
  readonly property int strong: px(Style.font.title, 16)
  readonly property int big: px(Style.font.heading, 22)
  readonly property int hero: px(Style.font.display, 26)
  readonly property int heroLarge: px(Style.font.displayLarge, 30)
  readonly property int bottomPad: Style.space(10)

  // The popup's background as seen: a translucent one is judged over the theme's own background.
  readonly property string background: Contrast.flatten(String(Color.popups.background), String(Color.background))
  readonly property color ink: Qt.color(Contrast.ensure(String(Color.popups.text), background, 7))
  readonly property color dim: Qt.color(Contrast.ensure(Contrast.mix(String(Color.popups.text), background, 0.22), background, 4.5))
  readonly property color line: Qt.color(Contrast.mix(String(Color.popups.text), background, 0.45))
  readonly property color track: Util.alpha(ink, 0.10)
  readonly property color accentText: onPopup(accent, 4.5)
  readonly property color accentFill: onPopup(accent, 3)
  // A quieter shade of the accent that is still a 3:1 graphic: what is not selected.
  readonly property color accentSoft: onPopup(Contrast.mix(String(accent), background, 0.45), 3)
  readonly property color urgentText: onPopup(urgent, 4.5)

  // `color` adjusted to read on the popup: 4.5 for text, 3 for graphics.
  function onPopup(color, min) {
    return Qt.color(Contrast.ensure(String(color), background, min === undefined ? 4.5 : min))
  }
}
