# Changelog

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
- **The token renews itself.** When the access token expires (or the server
  rejects it), `limit.py` trades the refresh token for a new pair, the way Claude
  Code does, and writes it back to `~/.claude/.credentials.json`. The widget no
  longer sits on "sign-in expired" until you start `claude`.
- **Your hours, your time zone.** Active hours are settings (`workFrom`, `workTo`)
  in local time, DST-safe, instead of a hard-coded UTC+5 08–23. 12-hour clock option.
- The bar's open-popup line now spans the whole widget; the bar meter is drawn on
  whole pixels.
- `animations` setting to stop the meters from sliding.
- 97 automated tests (Python, Node, Qt's own engine).

## 1.0.0

First version: 5-hour window in the bar, popup with the week and model limits,
pace tick, weekly-share ceiling, forecast.
