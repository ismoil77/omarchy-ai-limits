# Claude limit for the Omarchy bar

Your Claude usage limits in the [Omarchy](https://omarchy.org) bar — the 5-hour
window, the week and model-specific weeks — with a plain-language verdict instead of
a wall of numbers. Built to be read by people with low vision.

[Русская версия](README.ru.md)

![The popup, English](docs/preview-en.png)

In the bar: `✻ [meter] 9% 4h22m W9%` — the star and meter show the 5-hour window in a
pace colour, then the time to reset; a chip appears when the week needs attention.
Click opens the popup, right click refreshes.

## Why another limit widget

- **It tells you what to do.** Each window starts with one sentence: *"At this speed
  the limit runs out at Fri 17:12, in 4 d 2 h — before the reset."* Details (`D`) are
  one key away.
- **It protects your week, not only the window.** The 5-hour window gets a ceiling
  derived from what is left of the week, so burning every window to 100% doesn't leave
  you locked out on Thursday.
- **Real numbers from every device.** It reads Anthropic's usage endpoint, the same
  figures `/usage` shows, so work on other machines counts.
- **Accessible.**
  - text is never smaller than 13 px and scales (`textSize`: Normal, Large, Extra large);
  - every text colour is held to WCAG AA contrast (4.5:1) on your theme's popup
    background — checked against all 22 stock Omarchy themes;
  - status is a word *and* a shape (✓ ▲ ✕), never colour alone;
  - the popup scrolls instead of clipping when the text is large;
  - `animations: false` stops the meters from sliding.
- **English and Russian** (`language`: `auto` follows your locale).

## Requirements

- Omarchy with the shell plugin system (`omarchy plugin` exists).
- `python3` 3.8+ (stdlib only).
- Claude Code signed in with a Claude subscription (Pro/Max). API-key logins have no
  subscription limits to show.

## Install

```bash
omarchy plugin add https://github.com/ismoil77/omarchy-claude-limit.git --enable
```

(or copy the folder to `~/.config/omarchy/plugins/ismoil.claude-limit/`, run
`omarchy-shell shell rescanPlugins`, then `omarchy plugin enable ismoil.claude-limit`).

Plugins run unsandboxed inside the shell — read the code first; it is small.
Update with `omarchy plugin update ismoil.claude-limit`.

## Remove

```bash
omarchy plugin remove ismoil.claude-limit
rm -rf ~/.cache/ismoil-claude-limit      # cached numbers, optional
```

## Settings

Set in the widget's entry in `~/.config/omarchy/shell.json`, or in the shell's
bar settings:

| key | default | |
|---|---|---|
| `language` | `auto` | `auto`, `en`, `ru` |
| `textSize` | `Normal` | `Normal`, `Large`, `Extra large` — scales popup and bar text |
| `workFrom`, `workTo` | `8`, `23` | Hours of your local day you use Claude. The week's pace is counted over these hours only, so nights don't make you look slow. `0`–`24` for round the clock |
| `clock` | `24-hour` | or `12-hour` |
| `animations` | `true` | `false` stops the meters from sliding |
| `renewLogin` | `false` | `true`: renew an expired Claude login by itself (see Privacy) |
| `interval` | `60` | refresh seconds (at least 45) |

## Privacy and what it touches

Read this: the widget handles your Claude login.

- It reads `~/.claude/.credentials.json` (or `$CLAUDE_CONFIG_DIR`) and sends the
  access token **only** to `https://api.anthropic.com/api/oauth/usage`.
- **Off by default: the login file is never written.** When the access token expires the
  widget shows "sign-in expired — run claude" and waits until Claude Code refreshes it.
- **Opt-in `renewLogin: true`.** Then, when the access token has expired (or is rejected), it
  renews it the way Claude Code does: the refresh token goes **only** to
  `https://platform.claude.com/v1/oauth/token`, and the new token pair is written back to
  `.credentials.json` (atomically, same permissions, other keys kept). A failed renewal is
  not retried for 10 minutes. Because the refresh token rotates, a Claude Code session that
  was already running may need `claude` restarted once if it had cached the old pair.
- Nothing else leaves your machine. Cached numbers live in `~/.cache/ismoil-claude-limit/`.

## How the colours are decided

- **green** — on or under an even pace, nothing suggests running out before the reset.
- **yellow** — faster than an even pace, near the limit, or past this window's share
  of the week.
- **red** — at the current speed it runs out before the reset (or already spent).
  A high percent alone is not red: 92% with nothing being spent is fine.

## Development

```bash
tests/run.sh      # Python, Node, Qt's QML engine, and `omarchy plugin validate`
```

`Model.js` (pace maths and every sentence), `Strings.js` (en/ru), `Contrast.js` are
pure functions loaded both by the widget and by the tests. The Qt 6 `qmltestrunner`
suite is skipped if it isn't installed. After changing QML, run
`omarchy restart shell` — hot reload can leave a stale widget.

To add a language, add a table to `Strings.js` (the tests fail until it has every key
and the same placeholders) and its code to `LANGS`.

## License

MIT
