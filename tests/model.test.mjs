process.env.TZ = "Asia/Dushanbe" // UTC+5, no DST: the author's zone, easy to reason about
import test from "node:test"
import assert from "node:assert/strict"
import { Model } from "./loader.mjs"

const M = Model()
// Values come out of a separate vm realm; compare them as plain data.
const plain = x => JSON.parse(JSON.stringify(x))
const EN = M.config({ language: "en" })
const RU = M.config({ language: "ru" })
const at = (d, h, m = 0) => new Date(2026, 9, d, h, m).getTime() / 1000 // 2026-10-<d> local
// 2026-10-26 is a Monday.
const MON_NOON = at(26, 12)

const session = (o = {}) => ({ group: "session", model: "", util: 20, resetsAt: MON_NOON + 3 * 3600, window: 18000, rate: null, ...o })
const week = (o = {}) => ({ group: "weekly", model: "", util: 10, resetsAt: at(26, 3) + 7 * 86400, window: 7 * 86400, rate: null, ...o })
const info = (ws, extra = {}) => ({ ok: true, error: "", windows: ws, ratio: 0.1, ratioSpan: 15, fetchedAt: MON_NOON, ...extra })

test("config: defaults, bad values, overnight ranges, clock", () => {
  assert.deepEqual(plain(M.config()), { lang: "en", workFrom: 8, workTo: 23, workDay: 15, clock: "24h" })
  assert.equal(M.config({ workFrom: "9", workTo: "18" }).workDay, 9)
  assert.equal(M.config({ workFrom: 0, workTo: 24 }).workDay, 24)
  for (const bad of [{ workFrom: 23, workTo: 8 }, { workFrom: 10, workTo: 10 }, { workFrom: -1, workTo: 99 }, { workFrom: "x", workTo: "y" }]) {
    const c = M.config(bad)
    assert.deepEqual([c.workFrom, c.workTo], [8, 23], JSON.stringify(bad))
  }
  assert.equal(M.config({ clock: "12-hour" }).clock, "12h")
  assert.equal(M.config({ clock: "24-hour" }).clock, "24h")
  assert.equal(M.config({ language: "auto", locale: "ru_RU.UTF-8" }).lang, "ru")
})

test("workHours counts only the active hours of the local day", () => {
  assert.equal(M.workHours(at(26, 9), at(26, 12), EN), 3)
  assert.equal(M.workHours(at(26, 22), at(27, 9), EN), 2) // 22-23 and 08-09
  assert.equal(M.workHours(at(26, 0), at(26, 7), EN), 0) // all night
  assert.equal(M.workHours(at(26, 12), at(26, 12), EN), 0)
  assert.equal(M.workHours(at(26, 12), at(26, 10), EN), 0)
  assert.equal(M.workHours(at(26, 0), at(33, 0), EN), 7 * 15)
  assert.equal(M.workHours(at(26, 9), at(26, 12), M.config({ workFrom: 10, workTo: 11 })), 1)
  assert.equal(M.workHours(at(26, 0), at(27, 0), M.config({ workFrom: 0, workTo: 24 })), 24)
})

test("addWork is the inverse of workHours and skips the night", () => {
  for (const h of [0.5, 3, 14.9, 15, 16, 40, 104])
    for (const start of [at(26, 7), at(26, 12), at(26, 22, 30), at(27, 3)]) {
      const end = M.addWork(start, h, EN)
      assert.ok(Math.abs(M.workHours(start, end, EN) - h) < 1e-6, `${h}h from ${start}`)
      const hour = new Date(end * 1000).getHours()
      assert.ok(hour >= 8 || hour === 0 && h === 0 || end === start, "ends in active hours")
    }
  assert.equal(M.addWork(at(26, 22), 2, EN), at(27, 9)) // 1h tonight, 1h tomorrow morning
})

test("duration: full and compact, both languages", () => {
  const d = (h, c = EN, compact = false) => M.duration(h, c, compact)
  assert.equal(d(0), "0 min")
  assert.equal(d(0.75), "45 min")
  assert.equal(d(1), "1 h")
  assert.equal(d(4.75), "4 h 45 min")
  assert.equal(d(24), "1 d")
  assert.equal(d(29), "1 d 5 h")
  assert.equal(d(100.5), "4 d 4 h")
  assert.equal(d(1.9999), "2 h")
  assert.equal(d(-3), "0 min")
  assert.equal(d(4.75, RU), "4 ч 45 мин")
  assert.equal(d(29, RU), "1 д 5 ч")
  assert.equal(d(4.75, EN, true), "4h45m")
  assert.equal(d(0.5, EN, true), "30m")
  assert.equal(d(4.75, RU, true), "4ч45м")
  assert.equal(d(29, EN, true), "1d5h")
})

test("when: today, tomorrow, later; 24-hour and 12-hour", () => {
  const w = (t, c = EN, now = MON_NOON) => M.when(t, now, c)
  assert.equal(w(at(26, 18, 40)), "18:40")
  assert.equal(w(at(26, 0, 5)), "00:05")
  assert.equal(w(at(27, 3)), "tomorrow 03:00")
  assert.equal(w(at(27, 3), RU), "завтра 03:00")
  assert.equal(w(at(31, 21, 58)), "Sat 21:58")
  assert.equal(w(at(31, 21, 58), RU), "сб 21:58")
  assert.equal(w(at(26, 18, 40), M.config({ language: "en", clock: "12-hour" })), "6:40 PM")
  assert.equal(w(at(26, 0, 5), M.config({ language: "en", clock: "12-hour" })), "12:05 AM")
  assert.equal(w(at(26, 12, 0), M.config({ language: "en", clock: "12-hour" })), "12:00 PM")
})

test("rateText: per hour for the window, per active day for the week", () => {
  assert.equal(M.rateText(session(), 7.2, EN), "7.2% per hour")
  assert.equal(M.rateText(session(), 7.2, RU), "7,2% в час")
  assert.equal(M.rateText(week(), 1, EN), "15.0% per day")
  assert.equal(M.rateText(week(), 1, M.config({ language: "ru", workFrom: 9, workTo: 18 })), "9,0% в день")
})

test("title", () => {
  assert.equal(M.title(session(), EN), "5-hour window")
  assert.equal(M.title(week(), EN), "Week")
  assert.equal(M.title(week({ model: "Fable" }), EN), "Fable · week")
  assert.equal(M.title(week({ model: "Fable" }), RU), "Fable · неделя")
  assert.equal(M.title(null, EN), "")
})

// ---------------------------------------------------------------- pace
const paceOf = (w, i, now = MON_NOON, c = EN) => M.pace(w, now, i, c)

test("a closed window is idle and says how it opens", () => {
  const w = session({ util: 0, resetsAt: null })
  const p = paceOf(w, info([w]))
  assert.equal(p.open, false)
  assert.equal(p.status.id, "statusNew")
  assert.equal(p.level, "idle")
  assert.equal(M.summary(w, p, MON_NOON, EN), "The window opens with your first message.")
  assert.deepEqual(plain(M.rows(w, p, MON_NOON, EN)), [])
})

test("a window that reset a second ago is closed", () => {
  const w = session({ resetsAt: MON_NOON - 1 })
  assert.equal(paceOf(w, info([w])).open, false)
})

test("spent: red, and the summary names the reset", () => {
  const w = session({ util: 100 })
  const p = paceOf(w, info([w]))
  assert.equal(p.status.id, "statusSpent")
  assert.equal(p.level, "red")
  assert.match(M.summary(w, p, MON_NOON, EN), /used up.*15:00.*3 h/)
  assert.equal(M.rows(w, p, MON_NOON, EN).length, 1) // only the reset
})

test("running out before the reset: red, with the clock time", () => {
  const w = session({ util: 50, rate: 30, resetsAt: MON_NOON + 2 * 3600 })
  const p = paceOf(w, info([w], { ratio: null }))
  assert.equal(p.runsOut, true)
  assert.equal(p.level, "red")
  assert.ok(Math.abs(p.runsOutAt - (MON_NOON + (50 / 30) * 3600)) < 1)
  assert.match(M.summary(w, p, MON_NOON, EN), /runs out at 13:40, in 1 h 40 min — before the reset/)
  const forecast = M.rows(w, p, MON_NOON, EN).find(r => r.label === "Forecast")
  assert.equal(forecast.value, "runs out at 13:40, in 1 h 40 min")
  assert.equal(forecast.strong, true)
})

test("on track: green, and the forecast sentence", () => {
  const w = session({ util: 10, rate: 2, resetsAt: MON_NOON + 2 * 3600 }) // 3h in, target ≈ 60
  const p = paceOf(w, info([w], { ratio: null }))
  assert.equal(p.status.id, "statusOk")
  assert.equal(p.level, "green")
  assert.equal(M.summary(w, p, MON_NOON, EN), "You are on track: about 14% by the reset.")
  assert.equal(M.summary(w, p, MON_NOON, RU), "Всё идёт хорошо: к сбросу будет около 14%.")
})

test("well ahead of an even pace: yellow", () => {
  const w = session({ util: 60, rate: 0, resetsAt: MON_NOON + 4 * 3600 })
  const p = paceOf(w, info([w], { ratio: null }))
  assert.equal(p.status.id, "statusFast")
  assert.equal(p.level, "yellow")
  assert.ok(p.gap > 5)
})

test("heading past 85% without a weekly cap: yellow 'near the limit'", () => {
  const w = session({ util: 72, rate: 9, resetsAt: MON_NOON + 1.5 * 3600 })
  const p = paceOf(w, info([w], { ratio: null }))
  assert.equal(p.status.id, "statusNear")
  assert.match(M.summary(w, p, MON_NOON, EN), /about 86% by the reset/)
})

test("nothing spent: idle, no pace rows", () => {
  const w = session({ util: 0, rate: 0 })
  const p = paceOf(w, info([w], { ratio: null }))
  assert.equal(p.status.id, "statusUnused")
  assert.equal(p.level, "idle")
  assert.deepEqual(plain(M.rows(w, p, MON_NOON, EN).map(r => r.label)), ["Resets", "Keep under"])
})

test("weekly ceiling: the 5-hour window is capped by what is left of the week", () => {
  const wk = week({ util: 90 })
  const s = session({ util: 5, rate: 0 })
  const p = paceOf(s, info([s, wk]))
  assert.equal(p.capped, true)
  assert.ok(p.ceiling > 5 && p.ceiling < 100, `ceiling ${p.ceiling}`)
  const loose = paceOf(s, info([s, week({ util: 0 })]))
  assert.ok(loose.ceiling > p.ceiling)
})

test("past the ceiling is yellow 'over weekly share', and says so in both languages", () => {
  const wk = week({ util: 95 })
  const s = session({ util: 45, rate: 3 }) // the 1.5 points of week left last half an hour at this rate
  const p = paceOf(s, info([s, wk]))
  assert.equal(p.overCeiling, true)
  assert.equal(p.status.id, "statusOverShare")
  assert.equal(M.statusText(p, EN), "over weekly share")
  assert.equal(M.statusText(p, RU), "больше доли недели")
  const keep = M.rows(s, p, MON_NOON, EN).find(r => r.label === "Keep under")
  assert.equal(keep.strong, true)
  assert.equal(keep.key, true)
})

test("an uncapped window says the week does not limit it", () => {
  const s = session({ util: 10, rate: 1 })
  const p = paceOf(s, info([s], { ratio: null }))
  assert.equal(M.rows(s, p, MON_NOON, EN).find(r => r.label === "Keep under").value, "the week does not limit this window")
})

test("weekly pace is measured in active hours, not clock time", () => {
  const wk = week({ util: 20 })
  const now = at(28, 12) // Wed noon: 2 full days + 4 active hours into the week (from Mon 03:00)
  const p = paceOf(wk, info([wk]), now)
  const done = M.workHours(wk.resetsAt - 7 * 86400, now, EN)
  const all = M.workHours(wk.resetsAt - 7 * 86400, wk.resetsAt, EN)
  assert.ok(Math.abs(p.target - (100 * done) / all) < 1e-6)
  assert.equal(all, 105)
  assert.equal(p.rateSource, "average")
  assert.ok(Math.abs(p.rate - 20 / done) < 1e-6)
})

test("a weekly forecast lands inside active hours", () => {
  const wk = week({ util: 60 })
  const now = at(28, 12)
  const p = paceOf(wk, info([wk]), now)
  assert.equal(p.runsOut, true)
  const hour = new Date(p.runsOutAt * 1000).getHours()
  assert.ok(hour >= 8 && hour < 23, `ends at hour ${hour}`)
})

test("the first minutes of a window: rate is unknown, not zero", () => {
  const s = session({ util: 1, resetsAt: MON_NOON + 5 * 3600 - 60 })
  const p = paceOf(s, info([s], { ratio: null }))
  assert.equal(p.rateSource, "")
  const yours = M.rows(s, p, MON_NOON, EN).find(r => r.label === "Your speed")
  assert.equal(yours.value, "measuring…")
})

test("your-speed row names its source", () => {
  const s = session({ util: 20, rate: 5 })
  const recent = M.rows(s, paceOf(s, info([s], { ratio: null })), MON_NOON, EN).find(r => r.label === "Your speed")
  assert.equal(recent.value, "5.0% per hour (last 30 min)")
  const avg = session({ util: 20, rate: null })
  const p = paceOf(avg, info([avg], { ratio: null }))
  assert.match(M.rows(avg, p, MON_NOON, EN).find(r => r.label === "Your speed").value, /average for the window/)
  const wk = week({ util: 20 })
  const pw = paceOf(wk, info([wk]), at(28, 12))
  assert.match(M.rows(wk, pw, at(28, 12), EN).find(r => r.label === "Your speed").value, /over your active hours/)
})

test("the even-pace row words the gap in plain language", () => {
  const find = (util) => {
    const s = session({ util, rate: 0 })
    const p = paceOf(s, info([s], { ratio: null }))
    return { row: M.rows(s, p, MON_NOON, EN).find(r => r.label === "Even pace"), p }
  }
  const same = find(40) // two hours into five: the even pace is 40%
  assert.match(same.row.value, /^40% by now · you are right on it$/)
  assert.match(find(60).row.value, /you spent 20% more$/)
  assert.match(find(20).row.value, /you spent 20% less$/)
})

test("key rows: the reset always, the rest only when it matters", () => {
  const s = session({ util: 10, rate: 2, resetsAt: MON_NOON + 2 * 3600 })
  const rows = M.rows(s, paceOf(s, info([s], { ratio: null })), MON_NOON, EN)
  assert.deepEqual(plain(rows.filter(r => r.key).map(r => r.label)), ["Resets"])
  assert.ok(rows.length >= 4)
})

// ---------------------------------------------------------------- text sweep
const scenarios = () => {
  const out = []
  const wkHigh = week({ util: 95 })
  for (const [name, ws, now] of [
    ["closed", [session({ util: 0, resetsAt: null })], MON_NOON],
    ["spent", [session({ util: 100 })], MON_NOON],
    ["runs out", [session({ util: 50, rate: 30, resetsAt: MON_NOON + 7200 })], MON_NOON],
    ["ok", [session({ util: 10, rate: 2 })], MON_NOON],
    ["fast", [session({ util: 60, rate: 0, resetsAt: MON_NOON + 4 * 3600 })], MON_NOON],
    ["near", [session({ util: 72, rate: 9, resetsAt: MON_NOON + 5400 })], MON_NOON],
    ["unused", [session({ util: 0, rate: 0 })], MON_NOON],
    ["over share", [session({ util: 40, rate: 3 }), wkHigh], MON_NOON],
    ["week", [week({ util: 60 }), week({ model: "Fable", util: 0 })], at(28, 12)],
    ["week closed", [week({ util: 0, resetsAt: null })], MON_NOON]
  ]) out.push({ name, ws, now })
  return out
}

for (const [lang, cfg] of [["en", EN], ["ru", RU]]) {
  test(`${lang}: no sentence, label or value leaks undefined, NaN, Infinity or a raw {placeholder}`, () => {
    const bad = /undefined|NaN|Infinity|\{\w+\}|\[object/
    for (const { name, ws, now } of scenarios()) {
      const i = info(ws)
      for (const w of ws) {
        const p = M.pace(w, now, i, cfg)
        const texts = [M.title(w, cfg), M.statusText(p, cfg), M.summary(w, p, now, cfg)]
        for (const r of M.rows(w, p, now, cfg)) texts.push(r.label, r.value)
        for (const t of texts) {
          assert.ok(typeof t === "string" && t.length > 0, `${name}: empty text`)
          assert.ok(!bad.test(t), `${name}: "${t}"`)
        }
      }
      assert.ok(!bad.test(M.tooltip(i, true, now, cfg)), `${name} tooltip`)
    }
  })
}

test("russian text uses the comma and 'вы', never 'ты'", () => {
  const s = session({ util: 20, rate: 5 })
  const rows = M.rows(s, paceOf(s, info([s], { ratio: null }), MON_NOON, RU), MON_NOON, RU)
  assert.ok(rows.some(r => /\d,\d/.test(r.value)))
  const all = rows.map(r => r.label + " " + r.value).join(" ")
  assert.ok(!/\bты\b|\bтвой\b|\bтебе\b/i.test(all))
})

// ---------------------------------------------------------------- bar and header text
test("tooltip", () => {
  const s = session({ util: 20, rate: 1 })
  const wk = week({ util: 10 })
  assert.equal(M.tooltip(info([s, wk]), false, MON_NOON, EN), "Claude · loading…")
  const lines = M.tooltip(info([s, wk]), true, MON_NOON, EN).split("\n")
  assert.match(lines[0], /^5-hour window: 20% · .* · resets 15:00$/)
  assert.match(lines[1], /^Week: 10% · .* · resets Mon 03:00$/)
  assert.equal(lines.at(-1), "Click for details")
  const stale = M.tooltip(info([s], { ok: false, error: "network" }), true, MON_NOON, EN).split("\n")
  assert.ok(stale.includes("no network"))
  const closed = M.tooltip(info([session({ util: 0, resetsAt: null })]), true, MON_NOON, RU).split("\n")[0]
  assert.equal(closed, "5 часов: 0% · не начато")
})

test("stale and no-limits texts", () => {
  assert.equal(M.staleText({ error: "expired" }, EN), "Claude Code sign-in expired — run claude")
  assert.equal(M.staleText({ error: "auth" }, RU), "нет входа в Claude Code")
  assert.equal(M.staleText({ error: "ratelimit" }, EN), "the server asks to wait")
  assert.equal(M.staleText({ error: "http 500" }, EN), "http 500")
  assert.equal(M.noLimitsText({ error: "network" }, EN), "No limit data: no network")
})

test("header: plan, update time, and the reason when stale", () => {
  const i = info([], { plan: "Max 5x", fetchedAt: at(26, 13, 54) })
  assert.equal(M.headerText(i, false, false, MON_NOON, EN), "Loading…")
  assert.equal(M.headerText(i, true, false, MON_NOON, EN), "Max 5x · updated 13:54")
  assert.equal(M.headerText(i, true, false, MON_NOON, RU), "Max 5x · обновлено 13:54")
  assert.equal(M.headerText({ ...i, fetchedAt: 0, plan: "" }, true, false, MON_NOON, EN), "no data")
  assert.equal(M.headerText({ ...i, error: "expired" }, true, true, MON_NOON, EN), "Max 5x · updated 13:54 · Claude Code sign-in expired — run claude")
})

test("footnote states the active hours", () => {
  assert.match(M.footnote(M.config({ language: "en", workFrom: 9, workTo: 18 })), /9:00–18:00/)
  assert.match(M.footnote(RU), /8:00–23:00/)
})

test("status glyphs differ per level, so colour is never the only signal", () => {
  const glyphs = ["green", "yellow", "red", "idle"].map(l => M.GLYPHS[l])
  assert.equal(new Set(glyphs).size, 4)
})
