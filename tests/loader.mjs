// Loads the plugin's QML JavaScript libraries (`.pragma library`, `.import "X.js" as Name`)
// into plain Node so they can be tested without a running shell.
import fs from "node:fs"
import path from "node:path"
import vm from "node:vm"
import { fileURLToPath } from "node:url"

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

export function load(file, cache = new Map()) {
  if (cache.has(file)) return cache.get(file)
  const sandbox = { Math, Date, Number, String, Array, Object, RegExp, parseInt, isFinite, isNaN, Infinity, NaN, console }
  const imports = []
  const code = fs.readFileSync(path.join(root, file), "utf8")
    .split("\n")
    .filter(line => {
      const m = line.match(/^\.import\s+"([^"]+)"\s+as\s+(\w+)/)
      if (m) imports.push(m)
      return !/^\.(pragma|import)\b/.test(line)
    })
    .join("\n")
  for (const [, f, name] of imports) sandbox[name] = load(f, cache)
  vm.createContext(sandbox)
  vm.runInContext(code, sandbox, { filename: file })
  // Top-level functions and vars become the library's exports, as in QML.
  const lib = {}
  for (const key of Object.keys(sandbox)) if (!(key in globalThis) && !imports.some(i => i[2] === key)) lib[key] = sandbox[key]
  cache.set(file, lib)
  return lib
}

export const Model = () => load("Model.js")
export const Strings = () => load("Strings.js")
export const Contrast = () => load("kit/Contrast.js")
