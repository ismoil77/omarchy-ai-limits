import QtQuick
import Quickshell
import Quickshell.Io
import "Theme.js" as Theme

// The current Omarchy theme's named colours ({ green: "#879a39", ... }),
// followed live when the theme changes. Hand `colors` to Look's `themeColors`.
Item {
  id: themePalette
  visible: false
  width: 0
  height: 0

  property var colors: ({})

  FileView {
    path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: themePalette.colors = Theme.parseColors(text())
  }
}
