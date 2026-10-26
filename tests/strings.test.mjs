import test from "node:test"
import assert from "node:assert/strict"
import { Strings } from "./loader.mjs"

const S = Strings()
const placeholders = text => (text.match(/\{\w+\}/g) || []).sort().join(",")

test("English and Russian have exactly the same keys", () => {
  assert.deepEqual(Object.keys(S.ru).sort(), Object.keys(S.en).sort())
})

test("no empty strings, same placeholders in every language", () => {
  for (const key of Object.keys(S.en)) {
    for (const lang of S.LANGS) {
      assert.ok(S.TABLES[lang][key].length > 0, `${lang}.${key} is empty`)
    }
    assert.equal(placeholders(S.ru[key]), placeholders(S.en[key]), `placeholders of ${key} differ`)
  }
})

test("every string is plain text: no markup, no doubled spaces", () => {
  for (const lang of S.LANGS)
    for (const [key, text] of Object.entries(S.TABLES[lang])) {
      assert.ok(!/[<>]/.test(text), `${lang}.${key} has markup`)
      assert.ok(!/ {2}/.test(text), `${lang}.${key} has a double space`)
    }
})

test("resolve: explicit choice wins, auto follows the locale, unknown is English", () => {
  assert.equal(S.resolve("ru", "en_US"), "ru")
  assert.equal(S.resolve("en", "ru_RU"), "en")
  assert.equal(S.resolve("Русский", "en_US"), "ru")
  assert.equal(S.resolve("English", "ru_RU"), "en")
  assert.equal(S.resolve("auto", "ru_RU"), "ru")
  assert.equal(S.resolve("auto", "ru"), "ru")
  assert.equal(S.resolve("auto", "ru-RU"), "ru")
  assert.equal(S.resolve("auto", "en_GB"), "en")
  assert.equal(S.resolve("auto", "de_DE"), "en")
  assert.equal(S.resolve(undefined, undefined), "en")
  assert.equal(S.resolve("klingon", "ru_RU"), "ru")
})

test("t fills placeholders, keeps unknown ones, falls back to English then to the key", () => {
  assert.equal(S.t("en", "updated", { time: "13:54" }), "updated 13:54")
  assert.equal(S.t("ru", "updated", { time: "13:54" }), "обновлено 13:54")
  assert.equal(S.t("en", "updated", {}), "updated {time}")
  assert.equal(S.t("xx", "updated", { time: "1" }), "updated 1")
  assert.equal(S.t("en", "no.such.key"), "no.such.key")
  assert.equal(S.t("en", "diffMore", { n: 0 }), "you spent 0% more")
})

test("num uses the decimal separator of the language", () => {
  assert.equal(S.num("en", 7.25, 1), "7.3")
  assert.equal(S.num("ru", 7.2, 1), "7,2")
  assert.equal(S.num("ru", 7, 0), "7")
  assert.equal(S.num("en", "3.14159", 2), "3.14")
})
