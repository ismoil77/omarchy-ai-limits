# Changelog

## 2.2.0 — long-term history for the pace

- **The 5-hour window's cap on the week now comes from a month of data.** The share of the
  week one 5-hour window costs (`ratio`) is learned from the Claude desktop app's 30-day
  usage log (`plan-usage-history.json`, read-only) whenever that holds more than the widget
  has learned from its own fetches. On the author's account: 1465 session points instead of 261,
  ratio 0.135. Codex and Gemini have no such log and keep the old calculation.
- `limit.py` reports `ratioSource`: `history`, `learned` or `prior`.
- 156 automated tests.

## 2.1.0 — AI limits

- **Claude, Codex and Gemini.** The widget (renamed from "Claude limit", id `ismoil.ai-limits`)
  shows every AI tool that is signed in on the machine, with a switch in the popup (click,
  `h`/`l`, `1`–`3`) and on the bar (middle click). Codex reads its limits through
  `codex app-server`; Gemini through Google Code Assist's quota (per-model daily windows).
  Windows of any length are paced: up to 6 hours in clock time, longer ones over active hours.
- `providers` setting (`all` or a list). The hover tooltip lists every AI.
- Per-provider cache and state (`~/.cache/ismoil-ai-limits/`); the old Claude-only state is carried over.
- Gemini is built on the documented API and response-shape tests; not yet confirmed on a live account.
- 148 automated tests.

## 2.0.0

- **Readable by people with low vision.** Text never goes below 13 px and scales
  with the new `textSize` setting (Normal / Large / Extra large). Every colour used
  for text is nudged to WCAG AA contrast (4.5:1) on the popup background — the
  theme's yellow no longer vanishes on a light popup. Status is a word plus a shape
  (✓ ▲ ✕), never colour alone. The popup scrolls instead of clipping.
- **Plain language.** Each window opens with one sentence saying where you stand
  and what to do. Secondary numbers sit behind a *Details* button (`D`).
- **English and Russian.** `language`: `auto` follows the system locale.
  Russian text addresses you as «вы» and uses decimal commas.
- **Optional token renewal (`renewLogin`, off by default).** When on and the access
  token expires (or the server rejects it), `limit.py` trades the refresh token for a
  new pair, the way Claude Code does, and writes it back to
  `~/.claude/.credentials.json`, instead of sitting on "sign-in expired" until you start
  `claude`. Off, the login file is never written.
- **Your hours, your time zone.** Active hours are settings (`workFrom`, `workTo`)
  in local time, DST-safe, instead of a hard-coded UTC+5 08–23. 12-hour clock option.
- The bar's open-popup line now spans the whole widget; the bar meter is drawn on
  whole pixels.
- `animations` setting to stop the meters from sliding.
- 100 automated tests (Python, Node, Qt's own engine).

## 1.0.0

First version: 5-hour window in the bar, popup with the week and model limits,
pace tick, weekly-share ceiling, forecast.
