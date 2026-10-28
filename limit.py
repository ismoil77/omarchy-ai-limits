#!/usr/bin/env python3
"""AI usage limits for the ismoil.ai-limits bar widget: Claude, Codex, Gemini.

Each provider reports the same server-side numbers its own CLI shows, so usage
from every device signed in to the account is counted, not just this machine's:

  claude  Anthropic's OAuth usage endpoint (5-hour + weekly + model weeks)
  codex   the Codex CLI's app-server RPC (`account/rateLimits/read`)
  gemini  Google Code Assist's `retrieveUserQuota` (per-model daily quota)

A provider is used only when its CLI is set up on this machine. One run prints
one JSON object:

  selected   string   the provider the bar shows (see --select)
  providers  list     detected providers, in a fixed order, each:
    id, name, tool, cmd   "claude", "Claude", "Claude Code", "claude"
    ok         bool     the numbers are current: fetched without error, or
                        within the last 5 minutes
    error      string   "", "auth", "expired", "ratelimit", "network",
                        "unavailable", "http <n>"
    fetchedAt  float    unix seconds of the last good answer
    plan       string   "Max 5x", "Plus", "Standard", ...
    windows    list     key, group ("session" up to 6 h, "weekly" for any
                        longer window — a day, a week, a month), model (""
                        or "Fable" / "Pro"), util (0..100), resetsAt (unix s,
                        null when no window is open), window (seconds),
                        severity, rate (%/h, least-squares over the last
                        30 min, null until 3 samples over 10 min)
    ratio      float    long-window points one point of the session window
                        costs: a prior, refined by paired fetches or, for
                        Claude, by the desktop app's 30-day usage log
    ratioSpan  float    session points that ratio is learned from
    ratioSource string  "history" (the app's log), "learned" (this widget's
                        fetches) or "prior" (nothing learned yet)

Flags: --force (shorter cache), --renew (let Claude's expired login be renewed
and written back to ~/.claude/.credentials.json), --providers a,b (only these),
--select <id> (remember the provider the bar shows).

Every good answer is kept as a sample, so the burn rate is measured on the
server's own numbers over the last half hour, whichever device did the work.
"""

import fcntl
import json
import os
import select
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

PROVIDERS = {
  "claude": {"name": "Claude", "tool": "Claude Code", "cmd": "claude"},
  "codex": {"name": "Codex", "tool": "Codex", "cmd": "codex"},
  "gemini": {"name": "Gemini", "tool": "Gemini CLI", "cmd": "gemini"},
}

# Several bar instances (one per monitor) and the click-to-refresh share one
# answer; the endpoints rate-limit eager pollers. Codex starts a process per
# fetch and Gemini's quota moves slowly, so they are asked less often.
MIN_INTERVAL = {"claude": 45, "codex": 120, "gemini": 120}
FORCED_MIN_INTERVAL = 10
RATE_SPAN = 30 * 60
RATE_MIN_SPAN = 10 * 60
# Numbers this old still count as current even if the last request failed.
STALE_AFTER = 5 * 60
# A window this short is paced in clock time; a longer one in active hours.
SESSION_MAX = 6 * 3600
# Ratio learning: start from a prior worth RATIO_PRIOR_SPAN points of 5-hour
# spend, so the ceiling works from the first fetch; halve learned totals past
# the cap so it follows plan changes. The prior: Max 5x, week of 2026-10-19 —
# 5-hour 4% with weekly 0%, then 6-7% with weekly 1% (whole percents) puts
# one full window at 8-14% of the week.
RATIO_PRIOR = 0.10
RATIO_PRIOR_SPAN = 15
RATIO_CAP = 300

# ---- Claude
ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
# Claude Code's own OAuth client: the same refresh request it sends.
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
# Renew a little before the token dies, but not again for a while after a failure.
REFRESH_MARGIN = 60
REFRESH_RETRY = 10 * 60
GROUP_WINDOW = {"session": 5 * 3600, "weekly": 7 * 24 * 3600}

# ---- Codex
RPC_TIMEOUT = 8
# Codex reports each window's length; these are only for a missing one.
CODEX_DEFAULT_MINUTES = {"primary": 300, "secondary": 10080}

# ---- Gemini
CLOUDCODE = "https://cloudcode-pa.googleapis.com/v1internal"
GEMINI_QUOTA_WINDOW = 24 * 3600

# The Claude desktop app logs the account's server-side percents every ~15 min
# for 30 days: {"samples": [{"t": ms, "org": id, "u": {"fh": 5-hour, "sd": 7-day}}]}.
# Only the pairs of neighbouring samples that are close in time are used.
CLAUDE_USAGE_HISTORY = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "Claude" / "plan-usage-history.json"
HISTORY_MAX_GAP = 30 * 60

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CODEX_DIR = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
GEMINI_DIR = Path.home() / ".gemini"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ismoil-ai-limits"
LEGACY_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ismoil-claude-limit"


class Failure(Exception):
  """A provider could not give numbers: `kind` is the error the widget shows."""

  def __init__(self, kind, retry_after=None):
    super().__init__(kind)
    self.kind = kind
    self.retry_after = retry_after


# ------------------------------------------------------------------ state
def state_path(pid):
  return CACHE_DIR / f"state-{pid}.json"


def load_state(pid):
  try:
    return json.loads(state_path(pid).read_text())
  except Exception:
    return {}


def save_state(pid, state):
  path = state_path(pid)
  tmp = path.with_suffix(".tmp")
  tmp.write_text(json.dumps(state))
  tmp.replace(path)


def migrate_legacy():
  """The widget used to be Claude-only, with one state file in its own folder:
  keep its samples and the learned weekly ratio."""
  old = LEGACY_CACHE_DIR / "state.json"
  new = state_path("claude")
  if old.exists() and not new.exists() and LEGACY_CACHE_DIR != CACHE_DIR:
    try:
      new.write_text(old.read_text())
    except OSError:
      pass


def selected_path():
  return CACHE_DIR / "selected"


def read_selected():
  try:
    return selected_path().read_text().strip()
  except OSError:
    return ""


def write_selected(pid):
  if pid not in PROVIDERS:
    return
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  selected_path().write_text(pid)


def parse_time(value):
  if not value:
    return None
  try:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
  except Exception:
    return None


def make_window(key, model, util, resets_at, window, severity=""):
  return {
    "key": key,
    "group": "session" if window <= SESSION_MAX else "weekly",
    "model": model,
    "util": max(0.0, min(100.0, float(util))),
    "resetsAt": resets_at,
    "window": window,
    "severity": severity,
  }


def http_failure(e):
  if e.code == 429:
    retry = e.headers.get("retry-after") if e.headers else None
    return Failure("ratelimit", int(retry) if retry and retry.isdigit() else None)
  if e.code in (401, 403):
    return Failure("expired")
  return Failure(f"http {e.code}")


# ------------------------------------------------------------------ Claude
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


def claude_request(access):
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


def claude_plan():
  try:
    login = json.loads(credentials_path().read_text())["claudeAiOauth"]
  except Exception:
    return ""
  kind = str(login.get("subscriptionType") or "").capitalize()
  tier = str(login.get("rateLimitTier") or "")
  for mult in ("20x", "5x"):
    if mult in tier:
      return f"{kind} {mult}".strip()
  return kind


def claude_detected():
  return credentials_path().exists()


def fetch_claude(state, now, renew_login):
  access, expires = token()
  if not access:
    raise Failure("auth")
  if expires and expires <= now + REFRESH_MARGIN:
    access, error = renewed(state, now) if renew_login else ("", "expired")
    if error:
      raise Failure(error)
  try:
    found = claude_request(access)
  except urllib.error.HTTPError as e:
    if e.code not in (401, 403):
      raise http_failure(e)
    # Dead before its time (signed out elsewhere?): one renewal, one retry.
    access, error = renewed(state, now, used=access) if renew_login else ("", "expired")
    if error:
      raise Failure(error)
    try:
      found = claude_request(access)
    except urllib.error.HTTPError as again:
      raise http_failure(again)
  return {"windows": found, "plan": claude_plan()}


# ------------------------------------------------------------------ Codex
def runtime_env():
  home = str(Path.home())
  parts = [os.environ.get("PATH", ""), f"{home}/.local/bin", f"{home}/.npm-global/bin", f"{home}/.local/share/mise/shims"]
  env = os.environ.copy()
  env["PATH"] = os.pathsep.join(p for p in parts if p)
  return env


def find_codex():
  return shutil.which("codex", path=runtime_env().get("PATH"))


def codex_detected():
  return find_codex() is not None and (CODEX_DIR / "auth.json").exists()


def rpc_request(proc, request_id, method, params=None, timeout=RPC_TIMEOUT):
  proc.stdin.write(json.dumps({"id": request_id, "method": method, "params": params or {}}) + "\n")
  proc.stdin.flush()
  deadline = time.time() + timeout
  while time.time() < deadline:
    ready, _, _ = select.select([proc.stdout], [], [], 0.25)
    if not ready:
      continue
    line = proc.stdout.readline()
    if not line:
      break
    try:
      message = json.loads(line)
    except Exception:
      continue
    if message.get("id") == request_id:
      return message
  raise TimeoutError(method)


def codex_windows(rate_limits):
  """Windows from the app-server's `rateLimits`: {primary, secondary, planType}.

  Each window has usedPercent, windowDurationMins and resetsAt (unix seconds).
  A free or Go plan may carry only one window, and a long one (30 days)."""
  out = []
  for slot in ("primary", "secondary"):
    w = rate_limits.get(slot)
    if not isinstance(w, dict) or w.get("usedPercent") is None:
      continue
    try:
      minutes = float(w.get("windowDurationMins") or CODEX_DEFAULT_MINUTES[slot])
      reset = float(w["resetsAt"]) if w.get("resetsAt") else None
      out.append(make_window(f"codex:{slot}", "", float(w["usedPercent"]), reset, int(minutes * 60)))
    except (TypeError, ValueError):
      continue
  out.sort(key=lambda w: w["window"])
  return out


def fetch_codex(state, now, renew_login):
  codex = find_codex()
  if not codex:
    raise Failure("unavailable")
  try:
    proc = subprocess.Popen(
      [codex, "-s", "read-only", "-a", "on-request", "app-server"],
      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
      text=True, env=runtime_env(),
    )
  except OSError:
    raise Failure("unavailable")
  try:
    rpc_request(proc, 1, "initialize", {"clientInfo": {"name": "ismoil-ai-limits", "version": "2"}})
    proc.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
    proc.stdin.flush()
    account = rpc_request(proc, 2, "account/read", timeout=4)
    limits = rpc_request(proc, 3, "account/rateLimits/read", timeout=4)
  except (TimeoutError, OSError, ValueError):
    raise Failure("unavailable")
  finally:
    try:
      proc.terminate()
      proc.wait(timeout=1)
    except Exception:
      try:
        proc.kill()
      except Exception:
        pass
  who = (account.get("result") or {}).get("account") or {}
  if limits.get("error") or not (limits.get("result") or {}).get("rateLimits"):
    raise Failure("auth" if not who else "unavailable")
  rate_limits = limits["result"]["rateLimits"]
  found = codex_windows(rate_limits)
  if not found:
    raise Failure("unavailable")
  plan = str(rate_limits.get("planType") or who.get("planType") or who.get("type") or "")
  return {"windows": found, "plan": plan.capitalize() if plan.islower() else plan}


# ------------------------------------------------------------------ Gemini
def gemini_login():
  try:
    login = json.loads((GEMINI_DIR / "oauth_creds.json").read_text())
  except Exception:
    return "", 0
  return str(login.get("access_token") or ""), float(login.get("expiry_date") or 0) / 1000


def gemini_detected():
  return (GEMINI_DIR / "oauth_creds.json").exists()


def gemini_post(method, access, body):
  request = urllib.request.Request(
    f"{CLOUDCODE}:{method}", data=json.dumps(body).encode(), method="POST",
    headers={"Authorization": "Bearer " + access, "Content-Type": "application/json", "Accept": "application/json"},
  )
  with urllib.request.urlopen(request, timeout=10) as response:
    return json.loads(response.read().decode("utf-8", "replace"))


def gemini_family(model_id):
  """Quotas are per model; people think in Pro / Flash / Flash Lite."""
  m = str(model_id).lower()
  if "flash-lite" in m or "flash_lite" in m:
    return "Flash Lite"
  if "flash" in m:
    return "Flash"
  if "pro" in m:
    return "Pro"
  return str(model_id)


def gemini_windows(payload):
  """One window per model family: the most used bucket of the family wins.
  A full quota omits `remainingAmount`, so only `remainingFraction` is used."""
  best = {}
  for bucket in (payload or {}).get("buckets") or []:
    if not isinstance(bucket, dict) or not bucket.get("modelId"):
      continue
    fraction = bucket.get("remainingFraction")
    if not isinstance(fraction, (int, float)):
      continue
    used = (1 - max(0.0, min(1.0, float(fraction)))) * 100
    family = gemini_family(bucket["modelId"])
    if family not in best or used > best[family][0]:
      best[family] = (used, parse_time(bucket.get("resetTime")))
  order = {"Pro": 0, "Flash": 1, "Flash Lite": 2}
  return [make_window(f"gemini:{family}", family, used, reset, GEMINI_QUOTA_WINDOW)
          for family, (used, reset) in sorted(best.items(), key=lambda kv: (order.get(kv[0], 3), kv[0]))]


def fetch_gemini(state, now, renew_login):
  access, expires = gemini_login()
  if not access:
    raise Failure("auth")
  # The CLI renews its own token; this widget does not hold Google's client secret.
  if expires and expires <= now:
    raise Failure("expired")
  try:
    if not state.get("project") or not state.get("plan"):
      info = gemini_post("loadCodeAssist", access, {"metadata": {
        "ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}})
      project = info.get("cloudaicompanionProject")
      state["project"] = str(project.get("id") if isinstance(project, dict) else project or "")
      tier = info.get("paidTier") or info.get("currentTier") or {}
      state["plan"] = str(tier.get("name") or tier.get("id") or "") if isinstance(tier, dict) else ""
    payload = gemini_post("retrieveUserQuota", access, {"project": state.get("project") or ""})
  except urllib.error.HTTPError as e:
    raise http_failure(e)
  found = gemini_windows(payload)
  if not found:
    raise Failure("unavailable")
  return {"windows": found, "plan": state.get("plan", "")}


FETCHERS = {"claude": fetch_claude, "codex": fetch_codex, "gemini": fetch_gemini}
DETECTORS = {"claude": claude_detected, "codex": codex_detected, "gemini": gemini_detected}


# ------------------------------------------------------------------ pace inputs
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
  """Add how much the session and the overall long window moved since the
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


def claude_history_totals():
  """(session points, weekly points) the account spent over the app's 30-day
  log, or None when there is no usable log.

  Each pair of neighbouring samples that are at most HISTORY_MAX_GAP apart
  adds how far both counters rose; a pair where either fell crosses a reset
  and is skipped. Summed over a month the whole-percent steps even out, which
  a few fetches of this widget cannot do."""
  try:
    samples = json.loads(CLAUDE_USAGE_HISTORY.read_text())["samples"]
    org = samples[-1]["org"]
    series = sorted((s["t"] / 1000, float(s["u"]["fh"]), float(s["u"]["sd"])) for s in samples if s["org"] == org)
  except Exception:
    return None
  ds = dw = 0.0
  for a, b in zip(series, series[1:]):
    if b[0] - a[0] > HISTORY_MAX_GAP or b[1] < a[1] or b[2] < a[2]:
      continue
    ds += b[1] - a[1]
    dw += b[2] - a[2]
  return (ds, dw) if ds > 0 else None


# Longer logs than what the widget learned itself, per provider. Codex and
# Gemini keep none that holds both windows, so they stay on their own samples.
HISTORIES = {"claude": claude_history_totals}


def ratio_inputs(pid, state):
  """(session points, long-window points, source): the history when it holds
  more than the widget has learned itself, else what it learned, else nothing."""
  learned = state.get("ratio") or {}
  ds, dw = learned.get("ds", 0), learned.get("dw", 0)
  source = "learned" if ds else "prior"
  history = HISTORIES.get(pid, lambda: None)()
  if history and history[0] > ds:
    ds, dw, source = history[0], history[1], "history"
  return ds, dw, source


# ------------------------------------------------------------------ run
def poll(pid, now, force, renew_login):
  """One provider: fetch when due, remember samples, return its record."""
  state = load_state(pid)
  samples = state.get("samples")
  if not isinstance(samples, dict):
    samples = {}
  error = ""
  fresh = now - state.get("fetchedAt", 0) < (FORCED_MIN_INTERVAL if force else MIN_INTERVAL[pid])

  if fresh:
    error = state.get("error", "")
  elif now < state.get("backoffUntil", 0):
    error = "ratelimit"
  else:
    try:
      got = FETCHERS[pid](state, now, renew_login)
      learn_ratio(state, state.get("windows") or [], got["windows"])
      state.update(windows=got["windows"], fetchedAt=now, plan=got.get("plan", ""))
      for w in got["windows"]:
        samples.setdefault(w["key"], []).append([now, w["util"], w["resetsAt"]])
    except Failure as f:
      error = f.kind
      if f.kind == "ratelimit":
        state["backoffUntil"] = now + (f.retry_after or 120)
    except Exception:
      error = "network"
    state["error"] = error

  # Keep only what the rate window still needs.
  kept = {k: [s for s in v if now - s[0] <= RATE_SPAN + 600][-200:] for k, v in samples.items()}
  state["samples"] = {k: v for k, v in kept.items() if v}
  save_state(pid, state)

  out = []
  for w in state.get("windows") or []:
    w = dict(w)
    # A window that has since reset no longer holds its old percentage.
    if w["resetsAt"] is not None and w["resetsAt"] <= now:
      w["util"], w["resetsAt"] = 0.0, None
    w["rate"] = burn_rate(state["samples"], w["key"], now, w["resetsAt"]) if w["resetsAt"] else None
    out.append(w)
  ratio_ds, ratio_dw, ratio_source = ratio_inputs(pid, state)
  return {
    "id": pid,
    **PROVIDERS[pid],
    "ok": bool(out) and (error == "" or now - state.get("fetchedAt", 0) < STALE_AFTER),
    "error": error,
    "fetchedAt": state.get("fetchedAt", 0),
    "plan": state.get("plan") or (claude_plan() if pid == "claude" else ""),
    "windows": out,
    "ratio": (ratio_dw + RATIO_PRIOR * RATIO_PRIOR_SPAN) / (ratio_ds + RATIO_PRIOR_SPAN),
    "ratioSpan": ratio_ds,
    "ratioSource": ratio_source,
  }


def run(force=False, renew=False, only=None):
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  now = time.time()
  with open(CACHE_DIR / "lock", "w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    migrate_legacy()
    ids = [p for p in PROVIDERS if (only is None or p in only) and DETECTORS[p]()]
    records = [poll(p, now, force, renew) for p in ids]
    chosen = read_selected()
  selected = chosen if chosen in ids else (ids[0] if ids else "")
  return {"selected": selected, "providers": records}


def main(argv):
  if "--select" in argv:
    index = argv.index("--select")
    write_selected(argv[index + 1] if index + 1 < len(argv) else "")
  only = None
  if "--providers" in argv:
    index = argv.index("--providers")
    names = argv[index + 1] if index + 1 < len(argv) else ""
    only = [n.strip() for n in names.split(",") if n.strip() in PROVIDERS] or None
  print(json.dumps(run("--force" in argv, renew="--renew" in argv, only=only)))


if __name__ == "__main__":
  main(sys.argv[1:])
