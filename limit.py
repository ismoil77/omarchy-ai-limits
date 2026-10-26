#!/usr/bin/env python3
"""Claude 5-hour limit for the ismoil.claude-limit bar widget.

The numbers come from Anthropic's OAuth usage endpoint — the same server-side
utilization Claude Code's /usage shows — so usage from every device signed in
to the account is counted, not just this machine's transcripts.

Each run prints one JSON object:
  ok         bool     the numbers are current: fetched without error, or within
                      the last 5 minutes (false: older, or none yet)
  error      string   "", "auth", "expired", "ratelimit", "network", "http <n>"
  fetchedAt  float    unix seconds of the last good answer
  plan       string   "Max 5x", ...
  windows    list     session first, then weekly, then model-scoped weekly:
    key, group ("session"|"weekly"), model ("" or "Fable"), util (0..100),
    resetsAt (unix s, null when no window is open), window (seconds),
    severity (server's "normal"|"warning"|...), rate (%/h, least-squares
    over the last 30 min, null until 3 samples over 10 min)
  ratio      float    weekly points one point of the 5-hour window costs:
                      a prior, refined by paired fetches
  ratioSpan  float    5-hour points that ratio is learned from

With --renew, an expired access token is renewed here the way Claude Code
itself does it (refresh token → new pair, written back to
~/.claude/.credentials.json), so the widget keeps working when no Claude Code
session is running. Without the flag the login file is never written.

Every good answer is kept as a sample, so the burn rate is measured on the
server's own numbers over the last half hour, whichever device did the work.
"""

import fcntl
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
# Claude Code's own OAuth client: the same refresh request it sends.
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
# Renew a little before the token dies, but not again for a while after a failure.
REFRESH_MARGIN = 60
REFRESH_RETRY = 10 * 60
WINDOW = 5 * 3600
# Several bar instances (one per monitor) and the click-to-refresh share one
# answer; the endpoint rate-limits eager pollers.
MIN_INTERVAL = 45
FORCED_MIN_INTERVAL = 10
RATE_SPAN = 30 * 60
RATE_MIN_SPAN = 10 * 60
# Numbers this old still count as current even if the last request failed.
STALE_AFTER = 5 * 60
# Ratio learning: start from a prior worth RATIO_PRIOR_SPAN points of 5-hour
# spend, so the ceiling works from the first fetch; halve learned totals past
# the cap so it follows plan changes. The prior: Max 5x, week of 2026-10-19 —
# 5-hour 4% with weekly 0%, then 6-7% with weekly 1% (whole percents) puts
# one full window at 8-14% of the week.
RATIO_PRIOR = 0.10
RATIO_PRIOR_SPAN = 15
RATIO_CAP = 300

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ismoil-claude-limit"
STATE = CACHE_DIR / "state.json"


def load_state():
  try:
    return json.loads(STATE.read_text())
  except Exception:
    return {}


def save_state(state):
  tmp = STATE.with_suffix(".tmp")
  tmp.write_text(json.dumps(state))
  tmp.replace(STATE)


def credentials_path():
  return CLAUDE_DIR / ".credentials.json"


def token():
  try:
    login = json.loads(credentials_path().read_text())["claudeAiOauth"]
  except Exception:
    return "", 0
  return str(login.get("accessToken") or ""), float(login.get("expiresAt") or 0) / 1000


def save_login(whole, login):
  """Write the credentials file back atomically, keeping its mode and every
  other key it holds."""
  path = credentials_path()
  whole["claudeAiOauth"] = login
  tmp = path.with_name(path.name + ".tmp")
  try:
    mode = path.stat().st_mode & 0o777
  except OSError:
    mode = 0o600
  fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
  with os.fdopen(fd, "w") as f:
    json.dump(whole, f)
  os.chmod(tmp, mode)
  tmp.replace(path)


def renew(now, used=""):
  """Trade the refresh token for a fresh access token.

  Returns (access, expires_at, error). Claude Code may have renewed in the
  meantime — the refresh token rotates, so the file is read again first and
  a newer pair found there is used as is, without a second renewal.
  `used` is the access token the caller just found dead.
  """
  try:
    whole = json.loads(credentials_path().read_text())
    login = whole["claudeAiOauth"]
  except Exception:
    return "", 0, "auth"
  access = str(login.get("accessToken") or "")
  expires = float(login.get("expiresAt") or 0) / 1000
  if access and access != used and expires > now + REFRESH_MARGIN:
    return access, expires, ""
  refresh = str(login.get("refreshToken") or "")
  if not refresh:
    return "", 0, "expired"
  body = json.dumps({
    "grant_type": "refresh_token",
    "refresh_token": refresh,
    "client_id": CLIENT_ID,
    "scope": " ".join(login.get("scopes") or []),
  }).encode()
  request = urllib.request.Request(TOKEN_URL, data=body, method="POST", headers={
    "Content-Type": "application/json", "Accept": "application/json",
  })
  try:
    with urllib.request.urlopen(request, timeout=15) as response:
      answer = json.loads(response.read().decode("utf-8", "replace"))
    access = str(answer["access_token"])
    expires_in = float(answer["expires_in"])
  except urllib.error.HTTPError as e:
    # 400/401: the refresh token is dead (signed out, rotated elsewhere).
    return "", 0, "expired" if e.code in (400, 401, 403) else "network"
  except Exception:
    return "", 0, "network"
  login["accessToken"] = access
  login["refreshToken"] = str(answer.get("refresh_token") or refresh)
  login["expiresAt"] = int((now + expires_in) * 1000)
  if answer.get("refresh_token_expires_in") not in (None, ""):
    try:
      login["refreshTokenExpiresAt"] = int((now + float(answer["refresh_token_expires_in"])) * 1000)
    except (TypeError, ValueError):
      pass
  if answer.get("scope"):
    login["scopes"] = str(answer["scope"]).split()
  try:
    save_login(whole, login)
  except OSError:
    # The new pair is good but could not be stored: use it for this run only.
    return access, now + expires_in, ""
  return access, now + expires_in, ""


def parse_time(value):
  if not value:
    return None
  try:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
  except Exception:
    return None


GROUP_WINDOW = {"session": 5 * 3600, "weekly": 7 * 24 * 3600}


def fetch(access):
  request = urllib.request.Request(ENDPOINT, headers={
    "Authorization": "Bearer " + access,
    "anthropic-beta": "oauth-2025-04-20",
    "Accept": "application/json",
  })
  with urllib.request.urlopen(request, timeout=10) as response:
    payload = json.loads(response.read().decode("utf-8", "replace"))
  return windows(payload)


def windows(payload):
  """Every limit the account is spending against, session first.

  The `limits` array is the only place model-scoped allowances (a weekly
  window only Fable draws from) show up; the flat buckets are the fallback
  for payloads without it. Percent: 7 is 7%, as /usage prints it.
  """
  out = []
  for entry in payload.get("limits") or []:
    if not isinstance(entry, dict):
      continue
    group = str(entry.get("group") or "")
    if group not in GROUP_WINDOW or entry.get("percent") is None:
      continue
    scope = entry.get("scope") or {}
    model = (scope.get("model") or {}) if isinstance(scope, dict) else {}
    name = str(model.get("display_name") or model.get("id") or "").strip()
    out.append({
      "key": str(entry.get("kind") or group) + (":" + name if name else ""),
      "group": group,
      "model": name,
      "util": max(0.0, min(100.0, float(entry["percent"]))),
      "resetsAt": parse_time(entry.get("resets_at")),
      "window": GROUP_WINDOW[group],
      "severity": str(entry.get("severity") or ""),
    })
  if not out:
    for key, group in (("five_hour", "session"), ("seven_day", "weekly")):
      bucket = payload.get(key)
      if isinstance(bucket, dict) and bucket.get("utilization") is not None:
        out.append({
          "key": key, "group": group, "model": "",
          "util": max(0.0, min(100.0, float(bucket["utilization"]))),
          "resetsAt": parse_time(bucket.get("resets_at")),
          "window": GROUP_WINDOW[group], "severity": "",
        })
  out.sort(key=lambda w: (w["group"] != "session", w["model"] != "", w["model"]))
  return out


def plan():
  try:
    login = json.loads((CLAUDE_DIR / ".credentials.json").read_text())["claudeAiOauth"]
  except Exception:
    return ""
  kind = str(login.get("subscriptionType") or "").capitalize()
  tier = str(login.get("rateLimitTier") or "")
  for mult in ("20x", "5x"):
    if mult in tier:
      return f"{kind} {mult}".strip()
  return kind


def same_window(a, b):
  return a is not None and b is not None and abs(a - b) < 120


def burn_rate(samples, key, now, resets_at):
  """Percent per hour over the last RATE_SPAN of this window, or None.

  The server reports whole percents, so two end points alone jump between
  0 and 7.5 %/h; a least-squares slope over every sample in the span evens
  the steps out.
  """
  series = [s for s in samples.get(key, []) if same_window(s[2], resets_at) and now - s[0] <= RATE_SPAN]
  if len(series) < 3 or series[-1][0] - series[0][0] < RATE_MIN_SPAN:
    return None
  n = len(series)
  mean_t = sum(s[0] for s in series) / n
  mean_u = sum(s[1] for s in series) / n
  var = sum((s[0] - mean_t) ** 2 for s in series)
  if var <= 0:
    return None
  slope = sum((s[0] - mean_t) * (s[1] - mean_u) for s in series) / var
  return max(0.0, slope * 3600)


def learn_ratio(state, before, after):
  """Add how much the 5-hour and the overall weekly windows moved since the
  previous fetch, while neither window reset in between."""
  def pick(ws, group):
    return next((w for w in ws if w["group"] == group and not w["model"]), None)
  s0, s1, w0, w1 = pick(before, "session"), pick(after, "session"), pick(before, "weekly"), pick(after, "weekly")
  if not (s0 and s1 and w0 and w1):
    return
  if not (same_window(s0["resetsAt"], s1["resetsAt"]) and same_window(w0["resetsAt"], w1["resetsAt"])):
    return
  ds, dw = s1["util"] - s0["util"], w1["util"] - w0["util"]
  if ds < 0 or dw < 0:
    return
  r = state.get("ratio") or {"ds": 0.0, "dw": 0.0}
  r["ds"] += ds
  r["dw"] += dw
  if r["ds"] > RATIO_CAP:
    r["ds"] /= 2
    r["dw"] /= 2
  state["ratio"] = r


def renewed(state, now, used=""):
  """(access, error) after trying to renew; a failed try is not repeated for
  REFRESH_RETRY seconds, so a dead login does not hammer the server."""
  if now < state.get("renewRetryAt", 0):
    return "", state.get("renewError") or "expired"
  access, _, error = renew(now, used)
  if error:
    state["renewRetryAt"] = now + REFRESH_RETRY
    state["renewError"] = error
    return "", error
  state.pop("renewRetryAt", None)
  state.pop("renewError", None)
  return access, ""


def run(force, renew=False):
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  now = time.time()
  with open(CACHE_DIR / "lock", "w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    state = load_state()
    samples = state.get("samples")
    if not isinstance(samples, dict):
      samples = {}
    error = ""
    fresh = now - state.get("fetchedAt", 0) < (FORCED_MIN_INTERVAL if force else MIN_INTERVAL)

    if fresh:
      error = state.get("error", "")
    elif now < state.get("backoffUntil", 0):
      error = "ratelimit"
    else:
      access, expires = token()
      if access and expires and expires <= now + REFRESH_MARGIN:
        access, error = renewed(state, now) if renew else ("", "expired")
      if not access and not error:
        error = "auth"
      if access and not error:
        try:
          try:
            found = fetch(access)
          except urllib.error.HTTPError as e:
            if e.code not in (401, 403):
              raise
            # Dead before its time (signed out elsewhere?): one renewal, one retry.
            access, error = renewed(state, now, used=access) if renew else ("", "expired")
            if error:
              found = None
            else:
              found = fetch(access)
          if found is not None:
            learn_ratio(state, state.get("windows") or [], found)
            state.update(windows=found, fetchedAt=now)
            for w in found:
              samples.setdefault(w["key"], []).append([now, w["util"], w["resetsAt"]])
        except urllib.error.HTTPError as e:
          if e.code == 429:
            retry = e.headers.get("retry-after") if e.headers else None
            state["backoffUntil"] = now + (int(retry) if retry and retry.isdigit() else 120)
            error = "ratelimit"
          elif e.code in (401, 403):
            error = "expired"
          else:
            error = f"http {e.code}"
        except Exception:
          error = "network"
      state["error"] = error

    # Keep only what the rate window still needs.
    state["samples"] = {k: [s for s in v if now - s[0] <= RATE_SPAN + 600][-200:] for k, v in samples.items()}
    state["samples"] = {k: v for k, v in state["samples"].items() if v}
    save_state(state)

  out = []
  for w in state.get("windows") or []:
    w = dict(w)
    # A window that has since reset no longer holds its old percentage.
    if w["resetsAt"] is not None and w["resetsAt"] <= now:
      w["util"], w["resetsAt"] = 0.0, None
    w["rate"] = burn_rate(state["samples"], w["key"], now, w["resetsAt"]) if w["resetsAt"] else None
    out.append(w)
  return {
    "ok": bool(out) and (error == "" or now - state.get("fetchedAt", 0) < STALE_AFTER),
    "error": error,
    "fetchedAt": state.get("fetchedAt", 0),
    "plan": plan(),
    "windows": out,
    "ratio": ((r := state.get("ratio") or {}).get("dw", 0) + RATIO_PRIOR * RATIO_PRIOR_SPAN) / (r.get("ds", 0) + RATIO_PRIOR_SPAN),
    "ratioSpan": (state.get("ratio") or {}).get("ds", 0),
  }


def main(argv):
  print(json.dumps(run("--force" in argv, renew="--renew" in argv)))


if __name__ == "__main__":
  main(sys.argv[1:])
