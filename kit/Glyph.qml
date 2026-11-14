import QtQuick
import qs.Commons

// An icon glyph centred on its ink, not on its character cell: icon fonts
// leave uneven side bearings, so a glyph centred as text sits off-centre.
// Same measuring as the shell's own OpticalGlyph: tight bounds taken at a
// hundred times the size, so whole-pixel rounding does not move the centre.
// Give it a size (square is best); rotate the Glyph, not its text, to spin
// it around the centre of what is drawn.
Item {
  id: glyph

  property string text: ""
  property color color: "black"
  property string fontFamily: Style.font.family
  property real pixelSize: 16

  readonly property alias drawn: label
  readonly property int scaleUp: 100
  readonly property rect ink: Qt.rect(metrics.tightBoundingRect.x / scaleUp, metrics.tightBoundingRect.y / scaleUp,
                                      metrics.tightBoundingRect.width / scaleUp, metrics.tightBoundingRect.height / scaleUp)

  implicitWidth: Math.ceil(ink.width)
  implicitHeight: Math.ceil(ink.height)

  TextMetrics {
    id: metrics
    font.family: glyph.fontFamily
    font.pixelSize: Math.max(1, Math.round(glyph.pixelSize)) * glyph.scaleUp
    text: glyph.text
  }

  Text {
    id: label
    textFormat: Text.PlainText
    text: glyph.text
    color: glyph.color
    font.family: glyph.fontFamily
    font.pixelSize: Math.max(1, Math.round(glyph.pixelSize))
    // The ink's centre on the item's centre, on whole pixels.
    x: Math.round(glyph.width / 2 - (glyph.ink.x + glyph.ink.width / 2))
    y: Math.round(glyph.height / 2 - (baselineOffset + glyph.ink.y + glyph.ink.height / 2))
  }
}
