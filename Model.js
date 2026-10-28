.pragma library
.import "Strings.js" as S

// Pace maths and every sentence the widget shows. Pure functions: the time,
// the data from limit.py and the settings (`cfg`, see config()) come in as
// arguments, so a binding re-evaluates when any of them changes.

// Settings → the cfg every function below takes.
//   language  "auto" | "en" | "ru"      (locale is the system one, for "auto")
//   workFrom/workTo  hours of the local day you spend limits in; the week's
//             pace is measured in these hours only, not in clock time
//   clock     "24-hour" | "12-hour"
function config(o) {
  o = o || {}
  var from = Math.round(Number(o.workFrom))
  var to = Math.round(Number(o.workTo))
  if (!(from >= 0 && from <= 23)) from = 8
  if (!(to >= 1 && to <= 24) || to <= from) {
    from = 8
    to = 23
  }
  return {
    lang: S.resolve(o.language, o.locale),
    workFrom: from,
    workTo: to,
    workDay: to - from,
    clock: /^12/.test(String(o.clock || "")) ? "12h" : "24h"
  }
}

function cfgOf(cfg) {
  return cfg && cfg.workDay ? cfg : config(cfg)
}

function localDay(unix) {
  var d = new Date(unix * 1000)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function nextDay(day) {
  return new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1)
}

// Working hours of the local day starting at `day`, as unix seconds.
function workSpan(day, cfg) {
  var y = day.getFullYear(), m = day.getMonth(), d = day.getDate()
  return [new Date(y, m, d, cfg.workFrom).getTime() / 1000, new Date(y, m, d, cfg.workTo).getTime() / 1000]
}

// Working hours between unix a and b.
function workHours(a, b, cfg) {
  cfg = cfgOf(cfg)
  if (b <= a) return 0
  var total = 0
  var day = localDay(a)
  for (var i = 0; i < 800 && day.getTime() / 1000 < b; i++, day = nextDay(day)) {
    var span = workSpan(day, cfg)
    var from = Math.max(a, span[0])
    var to = Math.min(b, span[1])
    if (to > from) total += to - from
  }
  return total / 3600
}

// The clock time after `hours` more working hours from `t`.
function addWork(t, hours, cfg) {
  cfg = cfgOf(cfg)
  var left = hours * 3600
  var day = localDay(t)
  for (var i = 0; i < 800; i++, day = nextDay(day)) {
    var span = workSpan(day, cfg)
    var from = Math.max(t, span[0])
    if (span[1] <= from) continue
    if (span[1] - from >= left) return from + left
    left -= span[1] - from
  }
  return t + hours * 3600
}

function overallWeekly(info) {
  var ws = info && info.windows ? info.windows : []
  for (var i = 0; i < ws.length; i++)
    if (ws[i].group === "weekly" && !ws[i].model) return ws[i]
  return null
}

// Pace for one limit window from limit.py, at `now` (unix seconds).
//
//   target    - where an even spend would stand now: the 5-hour window in
//               clock time up to its ceiling; weekly ones in working hours
//   rate      - burn: %/h for the 5-hour window (last ~30 min of samples,
//               falls back to the window average); %/working hour for weekly
//   projected - percent at the reset if the rate holds
//   allowed   - rate that still lasts until the reset (or the ceiling)
//   ceiling   - 5-hour only: how far this window may go before the reset
//               without eating more than the week's even share. Spending a
//               full 5-hour window every time burns the week out early.
//   status    - what to do about it, see status()
function pace(w, now, info, cfg) {
  cfg = cfgOf(cfg)
  var open = !!w && w.resetsAt !== null && w.resetsAt !== undefined && w.resetsAt > now
  var weekly = !!w && w.group === "weekly"
  var windowSec = w ? w.window : 18000
  var util = open ? w.util : 0
  var leftSec = open ? w.resetsAt - now : windowSec
  var leftHours = leftSec / 3600
  var start = open ? w.resetsAt - windowSec : now
  // The span the pace is spread over: working hours for a week.
  var spanLeft = weekly ? workHours(now, start + windowSec, cfg) : leftHours
  var spanDone = weekly ? workHours(start, now, cfg) : (windowSec - leftSec) / 3600
  var spanAll = spanLeft + spanDone

  var ceiling = 100
  var ratio = info && info.ratio ? info.ratio : null
  var weekShare = null
  if (w && w.group === "session" && open) {
    var wk = overallWeekly(info)
    if (wk && ratio) {
      var wkOpen = wk.resetsAt && wk.resetsAt > now
      var wkUtil = wkOpen ? wk.util : 0
      var wkLeft = wkOpen ? workHours(now, wk.resetsAt, cfg) : 7 * cfg.workDay
      // Weekly points per working hour that still last the week, spent over
      // the working hours left in this window, in 5-hour points.
      var perHour = wkLeft > 0 ? Math.max(0, 100 - wkUtil) / wkLeft : 0
      var workHere = Math.min(workHours(now, w.resetsAt, cfg), wkOpen ? wkLeft : Infinity)
      weekShare = perHour * workHere / ratio
      ceiling = Math.max(util, Math.min(100, util + weekShare))
    }
  }

  var target = open && spanAll > 0 ? Math.max(0, Math.min(100, ceiling * spanDone / spanAll)) : 0
  var recent = open && !weekly && w.rate !== null && w.rate !== undefined
  var average = open && spanDone >= 0.25
  var rate = recent ? w.rate : (average ? util / spanDone : 0)
  var projected = util + rate * spanLeft
  var allowed = spanLeft > 0 ? Math.max(0, ceiling - util) / spanLeft : 0
  var hoursToFull = rate > 0 ? Math.max(0, 100 - util) / rate : Infinity
  var hoursToCeiling = rate > 0 ? Math.max(0, ceiling - util) / rate : Infinity

  var p = {
    open: open, util: util, target: target, gap: util - target, leftHours: leftHours,
    spanLeft: spanLeft, weekly: weekly,
    rate: rate, rateSource: recent ? "recent" : (average ? "average" : ""),
    projected: projected, allowed: allowed, hoursToFull: hoursToFull,
    runsOut: open && util < 100 && hoursToFull < spanLeft,
    ceiling: ceiling, capped: ceiling < 100, ratio: ratio, weekShare: weekShare,
    ratioSpan: info && info.ratioSpan ? info.ratioSpan : 0,
    hasWeekly: !!overallWeekly(info),
    hoursToCeiling: hoursToCeiling,
    overCeiling: open && ceiling < 100 && (util >= ceiling - 0.5 || hoursToCeiling < spanLeft)
  }
  p.runsOutAt = p.runsOut ? (weekly ? addWork(now, hoursToFull, cfg) : now + hoursToFull * 3600) : null
  p.status = status(p)
  p.level = p.status.level
  return p
}

// Colour (level), a language-free id and a shape for the pill. The shape
// carries the level for people who cannot tell the colours apart.
// Red is reserved for "this will stop you": spent, or running out before the
// reset at the current burn. A high percent alone is not — 92% with nothing
// being spent and minutes to the reset is fine. Going past the 5-hour
// ceiling is yellow: it does not stop you now, it takes from the week.
var GLYPHS = { green: "✓", yellow: "▲", red: "✕", idle: "•" }

function status(p) {
  var s = statusId(p)
  s.glyph = GLYPHS[s.level]
  return s
}

function statusId(p) {
  if (!p.open) return { level: "idle", id: "statusNew" }
  if (p.util >= 100) return { level: "red", id: "statusSpent" }
  if (p.runsOut) return { level: "red", id: "statusRunsOut" }
  if (p.overCeiling) return { level: "yellow", id: "statusOverShare" }
  if (p.gap > 5) return { level: "yellow", id: "statusFast" }
  if (!p.capped && p.projected >= 85) return { level: "yellow", id: "statusNear" }
  if (p.util === 0 && p.rate === 0) return { level: "idle", id: "statusUnused" }
  return { level: "green", id: "statusOk" }
}

function statusText(p, cfg) {
  return S.t(cfgOf(cfg).lang, p.status.id)
}

// "5-hour window", "Day", "Week", "30-day window": named by length, so any
// provider's windows read right. `lower` for use inside "Fable · week".
function windowName(seconds, cfg, lower) {
  var lang = cfgOf(cfg).lang
  var hours = Math.round(seconds / 3600)
  var text = hours === 24 ? S.t(lang, "winDay")
    : hours === 168 ? S.t(lang, "winWeek")
    : hours % 24 === 0 ? S.t(lang, "winDays", { n: hours / 24 })
    : S.t(lang, "winHours", { n: hours })
  return lower ? text.toLowerCase() : text
}

function title(w, cfg) {
  if (!w) return ""
  var name = windowName(w.window, cfg, !!w.model)
  return w.model ? S.t(cfgOf(cfg).lang, "modelWindow", { model: w.model, window: name }) : name
}

// The bar chip's tag for a window: the model's initial, else its length (W, D, 30d).
function shortName(w, cfg) {
  if (w.model) return w.model.charAt(0)
  var lang = cfgOf(cfg).lang
  var hours = Math.round(w.window / 3600)
  return hours === 168 ? S.t(lang, "shortWeek")
    : hours === 24 ? S.t(lang, "shortDay")
    : hours % 24 === 0 ? S.t(lang, "shortDays", { n: hours / 24 })
    : S.t(lang, "shortHours", { n: hours })
}

// 3 h 26 min, 47 min; a week reads in days: 3 d 15 h. `compact` drops the
// spaces and the word "min" for the bar: 3h26m.
function duration(hours, cfg, compact) {
  var lang = cfgOf(cfg).lang
  var minutes = Math.max(0, Math.round(hours * 60))
  var d = Math.floor(minutes / 1440)
  var h = Math.floor((minutes % 1440) / 60)
  var m = minutes % 60
  var gap = compact ? "" : " "
  var u = function(k) { return S.t(lang, k) }
  var mm = compact ? u("unitM") : u("unitMin")
  var parts = []
  if (d > 0) {
    parts.push(d + gap + u("unitD"))
    if (h > 0) parts.push(h + gap + u("unitH"))
  } else {
    if (h > 0) parts.push(h + gap + u("unitH"))
    if (m > 0 || h === 0) parts.push(m + gap + mm)
  }
  return parts.join(compact ? "" : " ")
}

function clockText(date, cfg) {
  var h = date.getHours(), m = date.getMinutes()
  var mm = (m < 10 ? "0" : "") + m
  if (cfg.clock === "12h") {
    var h12 = h % 12 === 0 ? 12 : h % 12
    return h12 + ":" + mm + " " + S.t(cfg.lang, h < 12 ? "am" : "pm")
  }
  return (h < 10 ? "0" : "") + h + ":" + mm
}

// Today: 13:30; tomorrow: "tomorrow 03:00"; later: "Sat 03:00".
function when(unix, now, cfg) {
  cfg = cfgOf(cfg)
  var d = new Date(Math.round(unix / 60) * 60000)
  var hm = clockText(d, cfg)
  var today = new Date(now * 1000)
  if (d.toDateString() === today.toDateString()) return hm
  var tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1)
  if (d.toDateString() === tomorrow.toDateString()) return S.t(cfg.lang, "tomorrow") + " " + hm
  return S.t(cfg.lang, "wd" + d.getDay()) + " " + hm
}

// Weekly pace reads better per working day than per hour.
function rateText(w, perHour, cfg) {
  cfg = cfgOf(cfg)
  if (w && w.group === "weekly")
    return S.t(cfg.lang, "ratePerDay", { n: S.num(cfg.lang, perHour * cfg.workDay, 1) })
  return S.t(cfg.lang, "ratePerHour", { n: S.num(cfg.lang, perHour, 1) })
}

// One plain sentence: where this window stands and what to do about it.
function summary(w, p, now, cfg) {
  cfg = cfgOf(cfg)
  var t = function(k, params) { return S.t(cfg.lang, k, params) }
  if (!p.open) return t("sumClosed")
  var left = duration(p.leftHours, cfg)
  if (p.util >= 100) return t("sumSpent", { when: when(w.resetsAt, now, cfg), left: left })
  if (p.runsOut)
    return t("sumRunsOut", { when: when(p.runsOutAt, now, cfg), left: duration((p.runsOutAt - now) / 3600, cfg) })
  if (p.overCeiling) return t("sumOverShare")
  if (p.gap > 5) return t("sumFast")
  var pct = Math.round(Math.min(100, p.projected))
  if (!p.capped && p.projected >= 85) return t("sumNear", { pct: pct })
  if (p.status.level === "idle") return t("sumUnused")
  return p.rate > 0 ? t("sumOkForecast", { pct: pct }) : t("sumOk")
}

// Label/value rows for a popup card. `strong` rows take the status colour.
function rows(w, p, now, cfg) {
  cfg = cfgOf(cfg)
  var t = function(k, params) { return S.t(cfg.lang, k, params) }
  if (!p.open || p.util >= 100) {
    if (!p.open) return []
    return [{ label: t("rowReset"), value: t("rowResetValue", { when: when(w.resetsAt, now, cfg), left: duration(p.leftHours, cfg) }), strong: false, key: true }]
  }
  var out = [{ label: t("rowReset"), value: t("rowResetValue", { when: when(w.resetsAt, now, cfg), left: duration(p.leftHours, cfg) }), strong: false, key: true }]
  if (w.group === "session" && p.hasWeekly) {
    out.push({
      label: t("rowKeepUnder"),
      value: p.capped
        ? t("rowKeepUnderCapped", { pct: Math.round(p.ceiling), share: Math.round(100 * p.ratio) })
        : t("rowKeepUnderFree"),
      strong: p.overCeiling,
      key: p.overCeiling
    })
  }
  if (p.status.level === "idle") return out
  var diff = Math.round(p.gap)
  out.push({
    label: t("rowEven"),
    value: t("rowEvenValue", {
      pct: Math.round(p.target),
      diff: diff === 0 ? t("diffSame") : t(diff > 0 ? "diffMore" : "diffLess", { n: Math.abs(diff) })
    }),
    strong: false
  })
  out.push({ label: t("rowSafe"), value: t("rowSafeValue", { rate: rateText(w, p.allowed, cfg) }), strong: false })
  var yours
  if (p.rate > 0)
    yours = t(p.rateSource === "recent" ? "yoursRecent" : p.weekly ? "yoursWeekly" : "yoursAverage", { rate: rateText(w, p.rate, cfg) })
  else
    yours = t(p.rateSource === "" ? "yoursMeasuring" : "yoursIdle")
  out.push({ label: t("rowYours"), value: yours, strong: false })
  if (p.runsOut)
    out.push({
      label: t("rowForecast"),
      value: t("forecastRunsOut", { when: when(p.runsOutAt, now, cfg), left: duration((p.runsOutAt - now) / 3600, cfg) }),
      strong: true
    })
  else if (p.rate > 0)
    out.push({
      label: t("rowForecast"),
      value: t(p.overCeiling ? "forecastOverShare" : "forecastPlain", { pct: Math.round(Math.min(100, p.projected)) }),
      strong: p.overCeiling
    })
  return out
}

function staleText(info, cfg) {
  var lang = cfgOf(cfg).lang
  var who = { tool: (info && info.tool) || "Claude Code", cmd: (info && info.cmd) || "claude" }
  var e = info ? info.error : ""
  return e === "expired" ? S.t(lang, "staleExpired", who)
    : e === "auth" ? S.t(lang, "staleAuth", who)
    : e === "unavailable" ? S.t(lang, "staleUnavailable", who)
    : e === "ratelimit" ? S.t(lang, "staleRate")
    : e === "network" ? S.t(lang, "staleNetwork")
    : e === "forbidden" ? S.t(lang, "staleForbidden", who)
    : e === "writefail" ? S.t(lang, "staleWritefail", who)
    : e === "cache" ? S.t(lang, "staleCache")
    : e === "internal" ? S.t(lang, "staleInternal")
    : e
}

function noLimitsText(info, cfg) {
  return S.t(cfgOf(cfg).lang, "noLimits", { why: staleText(info, cfg) })
}

function headerText(info, loaded, stale, now, cfg) {
  cfg = cfgOf(cfg)
  if (!loaded) return S.t(cfg.lang, "loading")
  var parts = []
  if (info.plan) parts.push(info.plan)
  parts.push(info.fetchedAt > 0 ? S.t(cfg.lang, "updated", { time: when(info.fetchedAt, now, cfg) }) : S.t(cfg.lang, "noData"))
  if (stale) parts.push(staleText(info, cfg) || S.t(cfg.lang, "staleStopped"))
  return parts.join(" · ")
}

function footnote(cfg) {
  cfg = cfgOf(cfg)
  return S.t(cfg.lang, "footnote", { from: cfg.workFrom, to: cfg.workTo })
}

// Hover text for the bar: every AI on the machine, its main window first.
function tooltip(providers, loaded, now, cfg) {
  cfg = cfgOf(cfg)
  var t = function(k, params) { return S.t(cfg.lang, k, params) }
  if (!loaded) return t("tipLoading")
  var lines = []
  for (var i = 0; i < providers.length; i++) {
    var info = providers[i]
    var ws = info.windows || []
    var main = null
    for (var j = 0; j < ws.length; j++) if (ws[j].group === "session") { main = ws[j]; break }
    if (!main && ws.length) main = ws[0]
    if (!main) {
      lines.push(info.name + ": " + (staleText(info, cfg) || t("noData")))
      continue
    }
    var mp = pace(main, now, info, cfg)
    lines.push(info.name + " · " + t("tipLine", { title: title(main, cfg), pct: Math.round(mp.util), status: statusText(mp, cfg) }) +
      (mp.open ? t("tipReset", { when: when(main.resetsAt, now, cfg) }) : ""))
    var weekly = main.group === "session" ? overallWeekly(info) : null
    if (weekly) {
      var wp = pace(weekly, now, info, cfg)
      lines.push("   " + t("tipLine", { title: title(weekly, cfg), pct: Math.round(wp.util), status: statusText(wp, cfg) }) +
        (wp.open ? t("tipReset", { when: when(weekly.resetsAt, now, cfg) }) : ""))
    }
    if (!info.ok && info.error) lines.push("   " + staleText(info, cfg))
  }
  lines.push(t("tipHint"))
  if (providers.length > 1) lines.push(t("tipSwitch"))
  return lines.join("\n")
}

// The main window of a provider: its session window, else the first one.
function mainWindow(info) {
  var ws = info && info.windows ? info.windows : []
  for (var i = 0; i < ws.length; i++) if (ws[i].group === "session") return ws[i]
  return ws.length ? ws[0] : null
}

// The bar's time-to-reset, or the window's length when it is not open.
function barTime(p, w, cfg) {
  cfg = cfgOf(cfg)
  if (p.open) return duration(p.leftHours, cfg, true)
  return duration((w ? w.window : 18000) / 3600, cfg, true)
}
