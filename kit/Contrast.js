.pragma library

// WCAG contrast helpers. Theme colours are picked for looks, not legibility:
// a yellow that reads on a dark popup is nearly invisible on a cream one.
// ensure() nudges a colour toward black or white until it reaches a ratio.

function parse(hex) {
  var s = String(hex).replace("#", "")
  if (s.length === 3) s = s[0] + s[0] + s[1] + s[1] + s[2] + s[2]
  var a = 1
  if (s.length === 8) {
    a = parseInt(s.slice(0, 2), 16) / 255
    s = s.slice(2)
  }
  if (s.length !== 6 || /[^0-9a-fA-F]/.test(s)) return { r: 0, g: 0, b: 0, a: 1 }
  return { r: parseInt(s.slice(0, 2), 16), g: parseInt(s.slice(2, 4), 16), b: parseInt(s.slice(4, 6), 16), a: a }
}

function hex(c) {
  function h(v) {
    var n = Math.max(0, Math.min(255, Math.round(v)))
    return (n < 16 ? "0" : "") + n.toString(16)
  }
  return "#" + h(c.r) + h(c.g) + h(c.b)
}

function luminance(c) {
  function lin(v) {
    v /= 255
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b)
}

function ratio(a, b) {
  var la = luminance(parse(a)), lb = luminance(parse(b))
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

function mix(a, b, t) {
  var x = parse(a), y = parse(b)
  return hex({ r: x.r + (y.r - x.r) * t, g: x.g + (y.g - x.g) * t, b: x.b + (y.b - x.b) * t })
}

// `fg` at `alpha` over an opaque `bg`.
function over(fg, alpha, bg) {
  return mix(bg, fg, alpha)
}

// A colour that may be translucent (#aarrggbb) laid over an opaque `under`,
// as an opaque colour: contrast can only be judged on what is actually seen.
function flatten(c, under) {
  var p = parse(c)
  return p.a >= 1 ? hex(p) : mix(under, hex(p), p.a)
}

// `fg` itself when it already reads on `bg`; otherwise the closest shade of
// it, darkened or lightened, that reaches `min` (4.5 text, 3 graphics).
function ensure(fg, bg, min) {
  if (ratio(fg, bg) >= min) return hex(parse(fg))
  var toBlack = ratio("#000000", bg) >= ratio("#ffffff", bg)
  var order = toBlack ? ["#000000", "#ffffff"] : ["#ffffff", "#000000"]
  for (var k = 0; k < order.length; k++) {
    for (var i = 1; i <= 50; i++) {
      var c = mix(fg, order[k], i / 50)
      if (ratio(c, bg) >= min) return c
    }
  }
  return order[0]
}
