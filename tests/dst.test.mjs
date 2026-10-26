process.env.TZ = "Europe/Berlin" // DST: 2026-03-29 has 23 hours, 2026-10-25 has 25
import test from "node:test"
import assert from "node:assert/strict"
import { Model } from "./loader.mjs"

const M = Model()
const ALL_DAY = M.config({ workFrom: 0, workTo: 24 })
const local = (y, m, d, h = 0) => new Date(y, m - 1, d, h).getTime() / 1000

test("the clock change shortens and lengthens a day, and the count follows", () => {
  assert.equal(M.workHours(local(2026, 3, 29), local(2026, 3, 30), ALL_DAY), 23)
  assert.equal(M.workHours(local(2026, 10, 25), local(2026, 10, 26), ALL_DAY), 25)
  assert.equal(M.workHours(local(2026, 3, 28), local(2026, 4, 4), ALL_DAY), 7 * 24 - 1)
})

test("active hours 08-23 are unaffected by a night-time clock change", () => {
  assert.equal(M.workHours(local(2026, 3, 28), local(2026, 4, 4), M.config({})), 105)
})

test("addWork across the change still inverts workHours", () => {
  const start = local(2026, 3, 28, 20)
  for (const h of [1, 5, 30]) {
    const end = M.addWork(start, h, ALL_DAY)
    assert.ok(Math.abs(M.workHours(start, end, ALL_DAY) - h) < 1e-6)
  }
})

test("when() uses the local calendar day across the change", () => {
  const now = local(2026, 3, 28, 22)
  const cfg = M.config({ language: "en" })
  assert.equal(M.when(local(2026, 3, 29, 9), now, cfg), "tomorrow 09:00")
})
