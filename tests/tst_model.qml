import QtQuick
import QtTest
import "../Model.js" as Model
import "../Strings.js" as Strings
import "../Contrast.js" as Contrast

// The same libraries the widget imports, run by Qt's own JavaScript engine:
// a syntax Node accepts but QML does not would fail here.
TestCase {
  name: "Model in the QML engine"

  function test_libraries_load_and_answer() {
    var cfg = Model.config({ language: "ru" })
    compare(cfg.lang, "ru")
    compare(Model.duration(4.75, cfg), "4 ч 45 мин")
    compare(Model.duration(4.75, Model.config({ language: "en" }), true), "4h45m")
    compare(Strings.t("en", "winWeek"), "Week")
    compare(Strings.num("ru", 7.2, 1), "7,2")
    compare(Contrast.ratio("#000000", "#ffffff").toFixed(0), "21")
  }

  function test_pace_and_texts() {
    var cfg = Model.config({ language: "en" })
    var now = new Date(2026, 9, 26, 12).getTime() / 1000
    var w = { group: "session", model: "", util: 50, resetsAt: now + 7200, window: 18000, rate: 30 }
    var p = Model.pace(w, now, { windows: [w], ratio: null }, cfg)
    compare(p.level, "red")
    compare(p.status.id, "statusRunsOut")
    verify(Model.summary(w, p, now, cfg).indexOf("runs out") >= 0)
    verify(Model.rows(w, p, now, cfg).length >= 4)
    verify(Model.tooltip([{ id: "claude", name: "Claude", ok: true, windows: [w] }], true, now, cfg).indexOf("Claude · 5-hour window") === 0)
  }

  function test_other_providers_windows() {
    var cfg = Model.config({ language: "en" })
    compare(Model.title({ group: "weekly", model: "Pro", window: 86400 }, cfg), "Pro · day")
    compare(Model.windowName(720 * 3600, cfg), "30-day window")
    compare(Model.staleText({ error: "expired", tool: "Gemini CLI", cmd: "gemini" }, cfg), "Gemini CLI sign-in expired — run gemini")
  }

  function test_contrast_fix() {
    var c = Contrast.ensure("#d0a215", "#fffcf0", 4.5)
    verify(Contrast.ratio(c, "#fffcf0") >= 4.5)
  }
}
