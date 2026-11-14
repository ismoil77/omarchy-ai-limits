import QtQuick
import qs.Commons
import qs.Commons as Commons
import "Contrast.js" as Contrast

// (`Commons.Color`, qualified: QtQuick has a `Color` type of its own that an
// unqualified name can resolve to.)
// How a widget's popup looks, in one place: colours held to WCAG contrast on
// the popup background, a type scale with a legibility floor that follows the
// user's `textSize`, and the animation switch. Components in this folder take
// a Look instead of a dozen loose properties.
//
//   Look { id: skin; textSize: String(setting("textSize", "Normal")); animations: setting("animations", true) !== false }
//
// Do not call the instance `look`: `look: look` binds to itself.
Item {
  id: look
  visible: false
  width: 0
  height: 0

  // "Normal" | "Large" | "Extra large" (any case).
  property string textSize: "Normal"
  property bool animations: true
  property string fontFamily: Style.font.family
  // The theme's accent as it arrives; `accentText`, `accentFill`, `accentSoft`,
  // `urgentText`, `ink` and `dim` are held to contrast.
  property color accent: Commons.Color.accent
  property color urgent: Commons.Color.urgent

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
  readonly property string background: Contrast.flatten(String(Commons.Color.popups.background), String(Commons.Color.background))
  readonly property color ink: Qt.color(Contrast.ensure(String(Commons.Color.popups.text), background, 7))
  readonly property color dim: Qt.color(Contrast.ensure(Contrast.mix(String(Commons.Color.popups.text), background, 0.22), background, 4.5))
  readonly property color track: Util.alpha(ink, 0.10)
  readonly property color accentText: onPopup(accent, 4.5)
  readonly property color accentFill: onPopup(accent, 3)
  // A quieter shade of the accent that is still a 3:1 graphic: what is not selected.
  readonly property color accentSoft: onPopup(Contrast.mix(String(accent), background, 0.45), 3)
  readonly property color urgentText: onPopup(urgent, 4.5)

  // The theme's named colours ({ green: "#..", ... }) from ThemePalette;
  // without them the levels fall back to the accent, a yellow and `urgent`.
  property var themeColors: ({})
  function themed(name, fallback) { return themeColors && themeColors[name] ? themeColors[name] : String(fallback) }

  // Cards: the popup's text faded nearly into its background, a raised
  // surface on light and dark themes alike.
  readonly property color surface: Qt.color(Contrast.mix(background, String(Commons.Color.popups.text), 0.05))
  readonly property color surfaceHover: Qt.color(Contrast.mix(background, String(Commons.Color.popups.text), 0.10))
  readonly property real radius: Math.max(6, Style.cornerRadius + 2)

  // Levels: calm / tight / danger, as graphics (3:1) and as text (4.5:1).
  readonly property color good: onPopup(themed("green", accent), 3)
  readonly property color goodText: onPopup(themed("green", accent), 4.5)
  readonly property color warn: onPopup(themed("yellow", "#d0a215"), 3)
  readonly property color warnText: onPopup(themed("yellow", "#d0a215"), 4.5)
  readonly property color bad: onPopup(themed("red", urgent), 3)
  readonly property color badText: onPopup(themed("red", urgent), 4.5)
  // A named theme colour as a graphic on the popup.
  function hue(name, fallback) { return onPopup(themed(name, fallback === undefined ? accent : fallback), 3) }
  function levelFill(level) { return level === "bad" ? bad : level === "warn" ? warn : good }
  function levelText(level) { return level === "bad" ? badText : level === "warn" ? warnText : goodText }

  // `color` adjusted to read on the popup: 4.5 for text, 3 for graphics.
  function onPopup(color, min) {
    return Qt.color(Contrast.ensure(String(color), background, min === undefined ? 4.5 : min))
  }
}
