import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons as Commons
import "Theme.js" as Theme

// The current Omarchy theme's named colours ({ green: "#879a39", ... }),
// followed live when the theme changes. Hand `colors` to Look's `themeColors`.
Item {
  id: themePalette
  visible: false
  width: 0
  height: 0

  property var colors: ({})

  // A theme switch can replace the whole theme folder, and the file watch with
  // it: the shell's own accent changing is a second cue to read again.
  Connections {
    target: Commons.Color
    function onAccentChanged() { file.reload() }
  }

  FileView {
    id: file
    path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: themePalette.colors = Theme.parseColors(text())
  }
}
