.pragma library

// Translation helpers shared by Omarchy widgets. A widget keeps its own
// tables ({ en: {key: "text {name}"}, ru: {...} }) and passes them in, so this
// file knows no words. English is the fallback for a missing key or language.

var FALLBACK = "en"

// Plural form index per language (CLDR cardinal rules, integers only).
var PLURAL = {
  en: function(n) { return n === 1 ? 0 : 1 },
  ru: function(n) {
    var m10 = n % 10, m100 = n % 100
    if (m10 === 1 && m100 !== 11) return 0
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 1
    return 2
  }
}

// Languages that write 7,2 rather than 7.2.
var DECIMAL_COMMA = { ru: true, uk: true, de: true, fr: true, es: true, it: true, pt: true, pl: true, nl: true, tr: true }

// "auto" follows the system locale (ru_RU.UTF-8 -> ru); anything not in
// `langs` is English. A language may also be written by its own name.
function resolve(setting, locale, langs, names) {
  var s = String(setting || "auto").toLowerCase()
  if (langs.indexOf(s) >= 0) return s
  if (names && names[s]) return names[s]
  var l = String(locale || "").toLowerCase()
  for (var i = 0; i < langs.length; i++)
    if (l === langs[i] || l.indexOf(langs[i] + "_") === 0 || l.indexOf(langs[i] + "-") === 0) return langs[i]
  return FALLBACK
}

// The text for `key`, with {name} placeholders filled from `params`.
function t(tables, lang, key, params) {
  var table = tables[lang] || tables[FALLBACK]
  var text = table[key]
  if (text === undefined) text = tables[FALLBACK][key]
  if (text === undefined) return key
  return String(text).replace(/\{(\w+)\}/g, function(m, name) {
    return params && params[name] !== undefined ? params[name] : m
  })
}

// Pick the form of a noun for `n` from `forms` (one entry per plural class).
function plural(lang, n, forms) {
  var rule = PLURAL[lang] || PLURAL[FALLBACK]
  var i = rule(Math.abs(Math.round(Number(n) || 0)))
  return forms[Math.min(i, forms.length - 1)]
}

// "5 commands": the table entry `key` is an array of forms.
function count(tables, lang, key, n) {
  var table = tables[lang] || tables[FALLBACK]
  var forms = table[key] || tables[FALLBACK][key]
  if (!forms) return String(n)
  return n + " " + plural(lang, n, forms)
}

// 7.2 -> "7.2" in English, "7,2" in Russian.
function num(lang, n, digits) {
  var s = Number(n).toFixed(digits === undefined ? 0 : digits)
  return DECIMAL_COMMA[lang] ? s.replace(".", ",") : s
}
