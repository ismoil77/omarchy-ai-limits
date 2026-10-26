import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model
import "Contrast.js" as Contrast
import "Strings.js" as Strings

// Claude limits. The bar holds the 5-hour window: a star in the pace colour,
// a meter of the window used with a tick where an even pace would be by now,
// the percent, and the time to reset. The popup lists every window the
// account spends against — 5 hours, the week, model-scoped weeks — each with
// a one-sentence verdict, its meter, reset, pace and forecast. Numbers come
// from Anthropic's usage endpoint (limit.py), so every device on the account
// counts.
//
//   green  - on or under pace, no sign of running out before the reset
//   yellow - ahead of the even pace, or heading past 85% by the reset
//   red    - at the current burn the limit runs out before the reset
//
// Made to be read by people with low vision: text never drops below 13 px
// and scales with the `textSize` setting, every colour used for text is
// pushed to at least WCAG AA contrast on the popup background, and the
// status is also a word and a shape (✓ ▲ ✕) in the popup, never colour alone.
//
//   left click  - open/close the popup
//   right click - refresh now
//   popup       - r refreshes, Esc closes, the wheel scrolls
Panel {
  id: root
  moduleName: "ismoil.claude-limit"
  ipcTarget: "ismoil.claude-limit"
  manageIpc: false

  readonly property int pollSeconds: Math.max(45, Number(setting("interval", 60)) || 60)
  readonly property string script: decodeURIComponent(String(Qt.resolvedUrl("limit.py")).replace(/^file:\/\//, ""))
  readonly property string colorsPath: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"

  readonly property bool vertical: bar ? bar.vertical : false
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  // ---- settings
  readonly property var cfg: Model.config({
    language: setting("language", "auto"),
    locale: Qt.locale().name,
    workFrom: setting("workFrom", 8),
    workTo: setting("workTo", 23),
    clock: setting("clock", "24-hour")
  })
  readonly property real textScale: {
    var v = String(setting("textSize", "Normal")).toLowerCase()
    return v.indexOf("extra") === 0 ? 1.5 : v === "large" ? 1.25 : 1
  }
  readonly property bool motion: setting("animations", true) !== false
  readonly property int fade: motion ? 400 : 0

  // ---- type scale: a 13 px floor, then the user's shell font, then textSize
  function px(base, floor) { return Math.round(Math.max(base, floor) * textScale) }
  readonly property int fsSmall: px(Style.font.body, 13)
  readonly property int fsText: px(Style.font.subtitle, 14)
  readonly property int fsStrong: px(Style.font.title, 16)
  readonly property int fsBig: px(Style.font.heading, 22)
  readonly property int fsHero: px(Style.font.display, 26)
  readonly property int bottomPad: Style.space(10)
  readonly property int fsBar: Math.round(Style.font.body * Math.min(textScale, 1.2))

  // ---- popup colours, held to contrast the theme does not promise
  readonly property string popupBg: String(Color.popups.background)
  readonly property color popupText: Qt.color(Contrast.ensure(String(Color.popups.text), popupBg, 7))
  readonly property color popupDim: Qt.color(Contrast.ensure(Contrast.mix(String(Color.popups.text), popupBg, 0.22), popupBg, 4.5))
  readonly property color popupLine: Qt.color(Contrast.mix(String(Color.popups.text), popupBg, 0.45))

  property var info: ({ ok: false, error: "", fetchedAt: 0, plan: "", windows: [] })
  property bool loaded: false
  property real now: Date.now() / 1000
  property var themePalette: ({})

  readonly property var session: {
    for (var i = 0; i < info.windows.length; i++)
      if (info.windows[i].group === "session") return info.windows[i]
    return { group: "session", model: "", util: 0, resetsAt: null, window: 18000, rate: null }
  }
  readonly property var weekly: {
    for (var i = 0; i < info.windows.length; i++)
      if (info.windows[i].group === "weekly" && !info.windows[i].model) return info.windows[i]
    return null
  }
  readonly property var sessionPace: Model.pace(session, now, info, cfg)
  readonly property bool stale: loaded && !info.ok
  // The 5-hour window owns the bar, but a weekly window that is about to
  // stop you matters more: it shows up beside it while it is yellow or red.
  readonly property var alert: {
    var best = null
    for (var i = 0; i < info.windows.length; i++) {
      var w = info.windows[i]
      if (w.group !== "weekly") continue
      var p = Model.pace(w, now, info, cfg)
      var rank = p.level === "red" ? 2 : p.level === "yellow" ? 1 : 0
      if (rank === 0) continue
      if (!best || rank > best.rank || (rank === best.rank && p.util > best.p.util))
        best = { w: w, p: p, rank: rank }
    }
    return best
  }
  property bool pendingForce: false
  // The popup shows what matters; the rest of the numbers sit behind "Details".
  property bool details: false

  // The theme's colour for a level, for shapes (the bar has no known backdrop).
  function levelColor(level, base) {
    return level === "red" ? themeColor("red", Color.urgent)
      : level === "yellow" ? themeColor("yellow", Color.accent)
      : level === "green" ? themeColor("green", Color.accent)
      : Util.alpha(base !== undefined ? base : popupText, 0.45)
  }

  // The same colour, adjusted to read as text (4.5) or a graphic (3) on `bg`.
  function onPopup(color, min) {
    return Qt.color(Contrast.ensure(String(color), popupBg, min === undefined ? 4.5 : min))
  }
  function levelText(level) { return level === "idle" ? popupDim : onPopup(levelColor(level), 4.5) }
  function levelFill(level) { return level === "idle" ? popupLine : onPopup(levelColor(level), 3) }

  function themeColor(name, fallback) {
    return themePalette[name] ? themePalette[name] : fallback
  }

  readonly property string tooltip: Model.tooltip(info, loaded, now, cfg)

  // ---------------------------------------------------------------- data
  // A click while a scheduled run is in flight is kept, not dropped.
  function refresh(force) {
    if (proc.running) {
      if (force) pendingForce = true
      return
    }
    proc.command = force ? ["python3", "-I", script, "--force"] : ["python3", "-I", script]
    proc.running = true
    colorsFile.reload()
  }

  function apply(text) {
    try {
      var next = JSON.parse(text)
      if (next && Array.isArray(next.windows)) {
        info = next
        loaded = true
      }
    } catch (e) {
      console.warn("ismoil.claude-limit", "bad output", e)
    }
    now = Date.now() / 1000
  }

  function parseColors(text) {
    var next = {}
    var re = /^\s*(red|yellow|green)\s*=\s*"(#[0-9A-Fa-f]{6})"/gm
    var m
    while ((m = re.exec(text)) !== null) next[m[1]] = m[2]
    themePalette = next
  }

  onOpenedChanged: if (opened) { now = Date.now() / 1000; refresh(false) }

  IpcHandler {
    target: "ismoil.claude-limit"

    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh(true) }
  }

  Process {
    id: proc
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.apply(text) }
    onRunningChanged: {
      if (running || !root.pendingForce) return
      root.pendingForce = false
      root.refresh(true)
    }
  }

  FileView {
    id: colorsFile
    path: root.colorsPath
    onLoaded: root.parseColors(text())
  }

  Timer {
    interval: root.pollSeconds * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh(false)
  }

  // The countdowns and pace ticks move between fetches.
  Timer {
    interval: root.opened ? 5000 : 15000
    running: true
    repeat: true
    onTriggered: root.now = Date.now() / 1000
  }

  // Window used, with a tick where an even pace would be by now: fill past
  // the tick is spending faster than the window allows. A faint run after
  // the fill is where the current burn lands by the reset. The outline keeps
  // the empty track visible on any theme.
  component Meter: Item {
    id: meter
    property var p
    property color fill
    property color base
    property color line: Util.alpha(base, 0.5)
    // The popup meter has an outline; the bar's is flat, so it stays crisp at 6 px.
    property bool outlined: true
    property real tickOverhang: barHeight
    // Even whole pixels only: half-pixel edges blur and make a thin bar look slanted.
    function even(v) { return 2 * Math.max(1, Math.round(v / 2)) }
    property real barHeight: even(Style.space(5))
    property bool forecast: true
    // The shaded run past the weekly ceiling is for the popup; the bar's meter stays plain.
    property bool shade: true
    height: barHeight * 2

    Rectangle {
      y: Math.round((meter.height - meter.barHeight) / 2)
      width: Math.round(parent.width)
      height: meter.barHeight
      radius: height / 2
      color: Util.alpha(meter.base, 0.12)
      border.width: meter.outlined ? 1 : 0
      border.color: meter.line
      clip: true

      // Past the ceiling: what this window still allows but the week does not.
      Rectangle {
        visible: meter.shade && meter.p.open && meter.p.capped
        x: parent.width * meter.p.ceiling / 100
        width: parent.width - x
        height: parent.height
        color: Util.alpha(meter.base, 0.28)
        Behavior on x { NumberAnimation { duration: root.fade; easing.type: Easing.OutCubic } }
      }

      Rectangle {
        visible: meter.forecast && meter.p.open && meter.p.rate > 0 && meter.p.util < 100
        width: parent.width * Math.min(100, meter.p.projected) / 100
        height: parent.height
        radius: parent.radius
        color: Util.alpha(meter.fill, 0.32)
        Behavior on width { NumberAnimation { duration: root.fade; easing.type: Easing.OutCubic } }
      }

      Rectangle {
        width: meter.p.util <= 0 ? 0 : Math.max(height, parent.width * Math.min(100, meter.p.util) / 100)
        height: parent.height
        radius: parent.radius
        color: meter.fill
        Behavior on width { NumberAnimation { duration: root.fade; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: root.motion ? 300 : 0 } }
      }
    }

    Rectangle {
      visible: meter.p.open
      width: Math.max(2, Math.round(Style.space(3)))
      height: meter.barHeight + meter.even(meter.tickOverhang)
      y: Math.round((meter.height - height) / 2)
      radius: width / 2
      x: Math.round((parent.width - width) * meter.p.target / 100)
      color: meter.base
      Behavior on x { NumberAnimation { duration: root.fade; easing.type: Easing.OutCubic } }
    }
  }

  // ---------------------------------------------------------------- bar
  implicitWidth: button.implicitWidth

  // The bar draws a line under the widget while its popup is open. Left alone
  // it is 55% of the slot; this makes it span everything the widget paints.
  readonly property real openPanelIndicatorWidth: content.implicitWidth
  readonly property real openPanelIndicatorHeight: content.implicitHeight
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: " "
    labelVisible: false
    active: root.opened
    fixedWidth: root.vertical ? -1 : content.implicitWidth + Style.space(12)
    fixedHeight: root.vertical ? content.implicitHeight + Style.space(12) : -1
    tooltipText: root.opened ? "" : root.tooltip
    onPressed: function(b) {
      if (b === Qt.RightButton) root.refresh(true)
      else root.toggle()
    }

    Grid {
      id: content
      anchors.centerIn: parent
      columns: root.vertical ? 1 : 5
      rowSpacing: Style.space(3)
      columnSpacing: Style.space(5)
      horizontalItemAlignment: Grid.AlignHCenter
      verticalItemAlignment: Grid.AlignVCenter
      opacity: root.stale ? 0.55 : 1

      Text {
        text: "✻"
        color: root.levelColor(root.sessionPace.level, root.barForeground)
        font.family: root.fontFamily
        font.pixelSize: Math.round(root.fsBar * 1.35)
        renderType: Text.NativeRendering
        Behavior on color { ColorAnimation { duration: root.motion ? 300 : 0 } }
      }

      Meter {
        visible: !root.vertical
        width: Math.round(Style.space(44))
        barHeight: even(Style.space(5))
        tickOverhang: even(Style.space(3))
        outlined: false
        shade: false
        forecast: false
        p: root.sessionPace
        fill: root.levelColor(root.sessionPace.level, root.barForeground)
        base: root.barForeground
      }

      // The shape repeats the colour for anyone who cannot tell it apart.
      Text {
        text: Math.round(root.sessionPace.util) + "%"
        color: root.barForeground
        font.family: root.fontFamily
        font.pixelSize: root.fsBar
        font.bold: true
        font.features: { "tnum": 1 }
        renderType: Text.NativeRendering
      }

      Text {
        visible: !root.vertical
        text: root.sessionPace.open ? Model.duration(root.sessionPace.leftHours, root.cfg, true) : Strings.t(root.cfg.lang, "barClosed")
        color: Util.alpha(root.barForeground, 0.8)
        font.family: root.fontFamily
        font.pixelSize: root.fsBar
        font.features: { "tnum": 1 }
        renderType: Text.NativeRendering
      }

      // Weekly alert chip: "W89%" (or the model's initial) in its colour.
      Rectangle {
        visible: !!root.alert
        readonly property color tone: root.alert ? root.levelColor(root.alert.p.level) : "transparent"
        width: chipText.implicitWidth + Style.space(8)
        height: chipText.implicitHeight + Style.space(2)
        radius: height / 2
        color: Util.alpha(tone, 0.22)

        Text {
          id: chipText
          anchors.centerIn: parent
          text: root.alert
            ? (root.alert.w.model ? root.alert.w.model.charAt(0) : Strings.t(root.cfg.lang, "weekShort")) + Math.round(root.alert.p.util) + "%"
            : ""
          color: root.barForeground
          font.family: root.fontFamily
          font.pixelSize: root.fsBar
          font.bold: true
          font.features: { "tnum": 1 }
          renderType: Text.NativeRendering
        }
      }
    }
  }

  // ---------------------------------------------------------------- popup
  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Math.round(Style.space(390) * root.textScale))
    contentHeight: panel.fittedContentHeight(column.implicitHeight + root.bottomPad)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r") root.refresh(true)
        else if (t === "d") root.details = !root.details
      }

      // Large text can outgrow the screen: the card scrolls instead of clipping.
      Flickable {
        id: scroller
        anchors.fill: parent

        // Reopen at the top, not where it was scrolled to last time.
        Connections {
          target: root
          function onOpenedChanged() { if (root.opened) scroller.contentY = 0 }
        }

        contentWidth: width
        contentHeight: column.implicitHeight + root.bottomPad
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Column {
          id: column
          width: parent.width
          spacing: Style.space(12)

          // ---------- Header: star · Claude / plan, updated · refresh ----------
          Item {
            width: parent.width
            implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, refreshButton.implicitHeight)

            Text {
              id: heroIcon
              text: "✻"
              color: root.levelFill(root.sessionPace.level)
              font.family: root.fontFamily
              font.pixelSize: root.fsHero
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
            }

            Column {
              id: heroLabels
              anchors.left: heroIcon.right
              anchors.leftMargin: Style.space(12)
              anchors.right: refreshButton.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)

              Text {
                text: "Claude"
                color: root.popupText
                font.family: root.fontFamily
                font.pixelSize: root.fsBig
                font.bold: true
              }

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: Model.headerText(root.info, root.loaded, root.stale, root.now, root.cfg)
                color: root.stale ? root.onPopup(root.themeColor("red", Color.urgent)) : root.popupDim
                font.family: root.fontFamily
                font.pixelSize: root.fsSmall
              }
            }

            Button {
              id: refreshButton
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰑐"
              iconSpinning: proc.running
              tooltipText: Strings.t(root.cfg.lang, "refreshTip")
              bordered: true
              foreground: root.popupText
              fontFamily: root.fontFamily
              fontSize: root.fsText
              verticalPadding: Style.space(4)
              onClicked: root.refresh(true)
            }
          }

          // ---------- One card per window ----------
          Repeater {
            model: root.info.windows

            delegate: Column {
              id: card
              required property var modelData
              required property int index
              readonly property var p: Model.pace(modelData, root.now, root.info, root.cfg)
              readonly property color tone: root.levelText(p.level)
              readonly property color fillTone: root.levelFill(p.level)
              readonly property color pillBg: Qt.color(Contrast.over(String(root.levelColor(p.level)), 0.16, root.popupBg))
              readonly property color pillText: Qt.color(Contrast.ensure(String(root.levelColor(p.level)), String(pillBg), 4.5))

              width: column.width
              spacing: Style.space(8)

              PanelSeparator { width: parent.width; visible: card.index > 0 }

              Item {
                width: parent.width
                implicitHeight: Math.max(cardTitle.implicitHeight, cardPercent.implicitHeight)

                Text {
                  id: cardTitle
                  anchors.left: parent.left
                  anchors.right: cardPercent.left
                  anchors.rightMargin: Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  wrapMode: Text.WordWrap
                  text: Model.title(card.modelData, root.cfg)
                  color: root.popupText
                  font.family: root.fontFamily
                  font.pixelSize: root.fsStrong
                  font.bold: true
                }

                Text {
                  id: cardPercent
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  text: Math.round(card.p.util) + "%"
                  color: card.tone
                  font.family: root.fontFamily
                  font.pixelSize: root.fsBig
                  font.bold: true
                  font.features: { "tnum": 1 }
                }
              }

              // Status: a word and a shape as well as the colour.
              Rectangle {
                width: pillRow.implicitWidth + Style.space(16)
                height: pillRow.implicitHeight + Style.space(6)
                radius: height / 2
                color: card.pillBg
                border.width: 1
                border.color: Util.alpha(card.pillText, 0.5)

                Row {
                  id: pillRow
                  anchors.centerIn: parent
                  spacing: Style.space(6)

                  Text {
                    text: card.p.status.glyph
                    color: card.pillText
                    font.family: root.fontFamily
                    font.pixelSize: root.fsSmall
                    font.bold: true
                  }

                  Text {
                    text: Model.statusText(card.p, root.cfg)
                    color: card.pillText
                    font.family: root.fontFamily
                    font.pixelSize: root.fsSmall
                    font.bold: true
                  }
                }
              }

              Meter {
                width: parent.width
                barHeight: even(Style.space(8) * root.textScale)
                p: card.p
                fill: card.fillTone
                base: root.popupText
                line: root.popupLine
              }

              // The verdict in one plain sentence (an idle window needs none: the pill says it).
              Text {
                visible: !card.p.open || card.p.level !== "idle"
                width: parent.width
                wrapMode: Text.WordWrap
                text: Model.summary(card.modelData, card.p, root.now, root.cfg)
                color: root.popupText
                font.family: root.fontFamily
                font.pixelSize: root.fsText
                lineHeight: 1.15
              }

              Repeater {
                model: Model.rows(card.modelData, card.p, root.now, root.cfg).filter(function(r) {
                  return root.details || r.key
                })

                // Label and value side by side when they fit, stacked when not;
                // the value wraps rather than getting cut off.
                delegate: Item {
                  id: row
                  required property var modelData
                  width: card.width
                  readonly property real gap: Style.space(12)
                  // 10% slack: TextMetrics measures without tabular figures.
                  readonly property bool side: labelWidth.width + valueWidth.width * 1.1 + gap <= width
                  implicitHeight: side
                    ? Math.max(rowLabel.implicitHeight, rowValue.implicitHeight)
                    : rowLabel.implicitHeight + Style.space(2) + rowValue.implicitHeight

                  TextMetrics {
                    id: labelWidth
                    text: modelData.label
                    font.family: root.fontFamily
                    font.pixelSize: root.fsSmall
                  }

                  TextMetrics {
                    id: valueWidth
                    text: modelData.value
                    font.family: root.fontFamily
                    font.pixelSize: root.fsText
                    font.bold: modelData.strong
                  }

                  Text {
                    id: rowLabel
                    x: 0
                    y: 0
                    text: modelData.label
                    color: root.popupDim
                    font.family: root.fontFamily
                    font.pixelSize: root.fsSmall
                  }

                  Text {
                    id: rowValue
                    width: row.side ? row.width - labelWidth.width - row.gap : row.width
                    x: row.side ? row.width - width : 0
                    y: row.side ? 0 : rowLabel.implicitHeight + Style.space(2)
                    wrapMode: Text.WordWrap
                    horizontalAlignment: row.side ? Text.AlignRight : Text.AlignLeft
                    text: modelData.value
                    color: modelData.strong ? card.tone : root.popupText
                    font.family: root.fontFamily
                    font.pixelSize: root.fsText
                    font.bold: modelData.strong
                    font.features: { "tnum": 1 }
                  }
                }
              }
            }
          }

          // ---------- Legend: how to read the meter ----------
          Column {
            visible: root.info.windows.length > 0
            width: parent.width
            spacing: Style.space(8)

            PanelSeparator { width: parent.width }

            Flow {
              width: parent.width
              spacing: Style.space(16)

              Row {
                spacing: Style.space(6)
                Rectangle {
                  anchors.verticalCenter: parent.verticalCenter
                  width: Math.max(3, Style.space(3)); height: Style.space(14); radius: width / 2
                  color: root.popupText
                }
                Text {
                  text: Strings.t(root.cfg.lang, "legendEven")
                  color: root.popupDim
                  font.family: root.fontFamily
                  font.pixelSize: root.fsSmall
                }
              }

              Row {
                spacing: Style.space(6)
                Rectangle {
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.space(18); height: Style.space(8); radius: height / 2
                  color: Util.alpha(root.levelFill("green"), 0.32)
                  border.width: 1
                  border.color: root.popupLine
                }
                Text {
                  text: Strings.t(root.cfg.lang, "legendForecast")
                  color: root.popupDim
                  font.family: root.fontFamily
                  font.pixelSize: root.fsSmall
                }
              }

              Row {
                spacing: Style.space(6)
                Rectangle {
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.space(18); height: Style.space(8); radius: height / 2
                  color: Util.alpha(root.popupText, 0.28)
                  border.width: 1
                  border.color: root.popupLine
                }
                Text {
                  text: Strings.t(root.cfg.lang, "legendShare")
                  color: root.popupDim
                  font.family: root.fontFamily
                  font.pixelSize: root.fsSmall
                }
              }
            }

            Text {
              visible: root.details
              width: parent.width
              wrapMode: Text.WordWrap
              text: Model.footnote(root.cfg)
              color: root.popupDim
              font.family: root.fontFamily
              font.pixelSize: root.fsSmall
              lineHeight: 1.15
            }
          }

          Button {
            visible: root.info.windows.length > 0
            text: Strings.t(root.cfg.lang, root.details ? "hideDetails" : "showDetails")
            bordered: true
            foreground: root.popupText
            fontFamily: root.fontFamily
            fontSize: root.fsText
            verticalPadding: Style.space(4)
            onClicked: root.details = !root.details
          }

          Text {
            visible: root.loaded && root.info.windows.length === 0
            width: parent.width
            wrapMode: Text.WordWrap
            text: Model.noLimitsText(root.info, root.cfg)
            color: root.popupDim
            font.family: root.fontFamily
            font.pixelSize: root.fsText
          }
        }
      }
    }
  }
}
