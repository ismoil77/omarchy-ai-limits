.pragma library

// The theme's named colours (colors.toml of the current Omarchy theme) and a
// stable colour per name, for letter icons. No QML here: Node tests it.

// `key = "#rrggbb"` lines -> { key: "#rrggbb" }; anything else is skipped.
function parseColors(text) {
  var out = {}
  var re = /^\s*([a-z_]+)\s*=\s*"(#[0-9A-Fa-f]{6})"/gm
  var m
  while ((m = re.exec(String(text || ""))) !== null) out[m[1]] = m[2].toLowerCase()
  return out
}

var TINTS = ["blue", "cyan", "magenta", "orange", "green", "yellow", "red"]

// The same name always gets the same theme colour.
function tintFor(name, palette, fallback) {
  var s = String(name || "")
  var h = 0
  for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  var key = TINTS[h % TINTS.length]
  return (palette && palette[key]) || fallback
}
