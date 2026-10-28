"""Tests for limit.py. No network and no real credentials: every test runs in a
temp directory and the HTTP layer is replaced."""

import io
import json
import os
import runpy
import stat
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import warnings
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import limit  # noqa: E402

warnings.simplefilter("ignore", ResourceWarning)  # HTTPError fixtures are never read

NOW = 1_800_000_000.0


def http_error(code, headers=None):
  return urllib.error.HTTPError("http://x", code, "err", headers or {}, io.BytesIO(b"{}"))


class FakeResponse:
  def __init__(self, payload):
    self.payload = json.dumps(payload).encode()

  def read(self):
    return self.payload

  def __enter__(self):
    return self

  def __exit__(self, *a):
    return False


class Sandbox(unittest.TestCase):
  """limit.py pointed at a throwaway ~/.claude and cache dir."""

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    root = Path(self.tmp.name)
    self.claude = root / "claude"
    self.claude.mkdir()
    self.cache = root / "cache"
    self.codex = root / "codex"
    self.codex.mkdir()
    self.gemini = root / "gemini"
    self.gemini.mkdir()
    patches = [
      mock.patch.object(limit, "CLAUDE_DIR", self.claude),
      mock.patch.object(limit, "CODEX_DIR", self.codex),
      mock.patch.object(limit, "GEMINI_DIR", self.gemini),
      mock.patch.object(limit, "CACHE_DIR", self.cache),
      mock.patch.object(limit, "CLAUDE_USAGE_HISTORY", root / "plan-usage-history.json"),
      mock.patch.object(limit, "LEGACY_CACHE_DIR", root / "legacy-cache"),
    ]
    for p in patches:
      p.start()
      self.addCleanup(p.stop)
    self.addCleanup(self.tmp.cleanup)

  def login(self, access="old-access", refresh="old-refresh", expires_in=3600, **extra):
    data = {"claudeAiOauth": {
      "accessToken": access, "refreshToken": refresh,
      "expiresAt": int((NOW + expires_in) * 1000),
      "scopes": ["user:inference", "user:profile"],
      "subscriptionType": "max", "rateLimitTier": "default_claude_max_5x", **extra,
    }, "other": {"keep": "me"}}
    path = self.claude / ".credentials.json"
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path

  def saved(self):
    return json.loads((self.claude / ".credentials.json").read_text())


USAGE = {"limits": [
  {"kind": "five_hour", "group": "session", "percent": 12.5, "resets_at": "2027-01-15T10:00:00Z", "severity": "normal"},
  {"kind": "seven_day", "group": "weekly", "percent": 40, "resets_at": "2027-01-18T00:00:00Z"},
  {"kind": "seven_day_fable", "group": "weekly", "percent": 3,
   "resets_at": "2027-01-18T00:00:00Z", "scope": {"model": {"display_name": "Fable"}}},
  {"kind": "junk", "group": "monthly", "percent": 1},
  {"kind": "nopercent", "group": "weekly", "percent": None},
  "not a dict",
]}


class Windows(unittest.TestCase):
  def test_orders_session_then_weekly_then_model(self):
    out = limit.windows({"limits": list(reversed(USAGE["limits"][:3]))})
    self.assertEqual([w["key"] for w in out], ["five_hour", "seven_day", "seven_day_fable:Fable"])

  def test_ignores_unknown_groups_missing_percent_and_junk(self):
    out = limit.windows(USAGE)
    self.assertEqual(len(out), 3)

  def test_clamps_percent(self):
    out = limit.windows({"limits": [{"group": "session", "percent": 140}, {"group": "weekly", "percent": -5}]})
    self.assertEqual([w["util"] for w in out], [100.0, 0.0])

  def test_model_scope_and_window_length(self):
    fable = limit.windows(USAGE)[2]
    self.assertEqual(fable["model"], "Fable")
    self.assertEqual(fable["window"], 7 * 24 * 3600)

  def test_flat_buckets_fallback(self):
    out = limit.windows({"five_hour": {"utilization": 9, "resets_at": "2027-01-15T10:00:00+00:00"},
                         "seven_day": {"utilization": 30, "resets_at": None}})
    self.assertEqual([(w["group"], w["util"]) for w in out], [("session", 9.0), ("weekly", 30.0)])
    self.assertIsNone(out[1]["resetsAt"])

  def test_empty_payload(self):
    self.assertEqual(limit.windows({}), [])

  def test_parse_time(self):
    self.assertEqual(limit.parse_time("1970-01-01T00:01:00Z"), 60)
    self.assertIsNone(limit.parse_time(""))
    self.assertIsNone(limit.parse_time("garbage"))


class BurnRate(unittest.TestCase):
  def series(self, points, reset=NOW + 3600):
    return {"k": [[NOW - age, util, reset] for age, util in points]}

  def test_slope_is_percent_per_hour(self):
    # +1 point every 5 minutes = 12 %/h
    s = self.series([(1500, 0), (1200, 1), (900, 2), (600, 3), (300, 4), (0, 5)])
    self.assertAlmostEqual(limit.burn_rate(s, "k", NOW, NOW + 3600), 12.0, places=6)

  def test_needs_three_samples_and_ten_minutes(self):
    self.assertIsNone(limit.burn_rate(self.series([(300, 1), (0, 2)]), "k", NOW, NOW + 3600))
    self.assertIsNone(limit.burn_rate(self.series([(300, 1), (200, 2), (0, 3)]), "k", NOW, NOW + 3600))

  def test_never_negative(self):
    s = self.series([(1200, 9), (600, 5), (0, 1)])
    self.assertEqual(limit.burn_rate(s, "k", NOW, NOW + 3600), 0.0)

  def test_ignores_old_samples_and_other_windows(self):
    s = {"k": [[NOW - 5000, 0, NOW + 3600], [NOW - 900, 5, NOW - 99999], [NOW - 600, 5, NOW + 3600],
               [NOW - 300, 5, NOW + 3600], [NOW, 5, NOW + 3600]]}
    self.assertEqual(limit.burn_rate(s, "k", NOW, NOW + 3600), 0.0)

  def test_unknown_key(self):
    self.assertIsNone(limit.burn_rate({}, "k", NOW, NOW + 1))


class LearnRatio(unittest.TestCase):
  def pair(self, s, w, s_reset=NOW + 1000, w_reset=NOW + 9000):
    return [
      {"group": "session", "model": "", "util": s, "resetsAt": s_reset},
      {"group": "weekly", "model": "", "util": w, "resetsAt": w_reset},
    ]

  def test_accumulates_deltas(self):
    state = {}
    limit.learn_ratio(state, self.pair(10, 2), self.pair(20, 3))
    self.assertEqual(state["ratio"], {"ds": 10, "dw": 1})

  def test_skips_when_a_window_reset_between(self):
    state = {}
    limit.learn_ratio(state, self.pair(10, 2), self.pair(2, 3, s_reset=NOW + 99999))
    self.assertNotIn("ratio", state)

  def test_skips_negative_and_missing(self):
    state = {}
    limit.learn_ratio(state, self.pair(10, 5), self.pair(10, 4))
    limit.learn_ratio(state, [], self.pair(1, 1))
    self.assertNotIn("ratio", state)

  def test_halves_past_cap(self):
    state = {"ratio": {"ds": limit.RATIO_CAP - 1, "dw": 30}}
    limit.learn_ratio(state, self.pair(0, 0), self.pair(10, 1))
    self.assertAlmostEqual(state["ratio"]["ds"], (limit.RATIO_CAP + 9) / 2)
    self.assertAlmostEqual(state["ratio"]["dw"], 15.5)


class Private(Sandbox):
  def test_every_cache_file_is_owner_only_even_over_an_older_open_one(self):
    self.cache.mkdir(parents=True, exist_ok=True)
    os.chmod(self.cache, 0o755)
    old = self.cache / "state-claude.json"
    old.write_text("{}")
    os.chmod(old, 0o644)
    prev = os.umask(0o022)
    try:
      limit.make_cache_dir()
      limit.save_state("claude", {"samples": []})
      limit.save_state("codex", {})
      limit.write_selected("codex")
    finally:
      os.umask(prev)
    self.assertEqual(stat.S_IMODE(os.stat(self.cache).st_mode), 0o700)
    for f in self.cache.iterdir():
      self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o600, f.name)


class Hardening(Sandbox):
  def test_a_stale_open_tmp_file_and_lock_end_owner_only(self):
    self.cache.mkdir(parents=True)
    (self.cache / "state-claude.json.tmp").write_text("old")
    os.chmod(self.cache / "state-claude.json.tmp", 0o644)
    (self.cache / "lock").write_text("")
    os.chmod(self.cache / "lock", 0o644)
    prev = os.umask(0o022)
    try:
      limit.save_state("claude", {})
      with mock.patch.dict(limit.DETECTORS, {"claude": lambda: False, "codex": lambda: False, "gemini": lambda: False}):
        limit.run()
    finally:
      os.umask(prev)
    for name in ("state-claude.json", "lock"):
      self.assertEqual(stat.S_IMODE(os.stat(self.cache / name).st_mode), 0o600, name)

  def test_the_legacy_cache_is_closed_and_migrated(self):
    legacy = self.cache.parent / "legacy-cache"
    legacy.mkdir()
    os.chmod(legacy, 0o755)
    (legacy / "state.json").write_text('{"ratio": {"ds": 1, "dw": 1}}')
    os.chmod(legacy / "state.json", 0o644)
    limit.make_cache_dir()
    limit.migrate_legacy()
    self.assertEqual(stat.S_IMODE(os.stat(legacy).st_mode), 0o700)
    self.assertEqual(stat.S_IMODE(os.stat(legacy / "state.json").st_mode), 0o600)
    self.assertEqual(limit.load_state("claude")["ratio"], {"ds": 1, "dw": 1})

  def test_tokens_go_only_where_they_belong(self):
    self.login(access="SENTINEL-ACCESS", refresh="SENTINEL-REFRESH")
    seen = []

    def urlopen(request, timeout=0):
      seen.append((request.full_url, dict(request.header_items())))
      return FakeResponse(USAGE)

    with mock.patch.object(limit.urllib.request, "urlopen", urlopen), mock.patch.object(limit.time, "time", return_value=NOW), \
         mock.patch.dict(limit.DETECTORS, {"codex": lambda: False, "gemini": lambda: False}):
      printed = json.dumps(limit.run(force=True))
    self.assertEqual(len(seen), 1)
    url, headers = seen[0]
    self.assertEqual(url, limit.ENDPOINT)
    self.assertEqual(headers["Authorization"], "Bearer SENTINEL-ACCESS")
    self.assertEqual(headers["Anthropic-beta"], "oauth-2025-04-20")
    self.assertNotIn("SENTINEL", printed)
    for f in self.cache.iterdir():
      self.assertNotIn("SENTINEL", f.read_text(), f.name)

  def test_codex_is_started_sandboxed_and_silent(self):
    proc = FakeProc({})
    rpc = lambda p, request_id, method, params=None, timeout=0: {"id": request_id, "result": {"rateLimits": {}, "account": {}}}
    with mock.patch.object(limit, "find_codex", return_value="/bin/codex"), \
         mock.patch.object(limit.subprocess, "Popen", return_value=proc) as popen, \
         mock.patch.object(limit, "rpc_request", rpc), self.assertRaises(limit.Failure):
      limit.fetch_codex({}, NOW, False)
    args, kwargs = popen.call_args
    self.assertEqual(args[0], ["/bin/codex", "-s", "read-only", "-a", "on-request", "app-server"])
    self.assertEqual(kwargs["stderr"], limit.subprocess.DEVNULL)
    self.assertEqual(kwargs["env"]["PATH"], limit.runtime_env()["PATH"])


class Damaged(Sandbox):
  def test_a_corrupt_or_foreign_state_file_gives_an_empty_state(self):
    self.cache.mkdir(parents=True)
    for text in ("{garbage", "[1, 2]", "42", "null"):
      limit.state_path("claude").write_text(text)
      self.assertEqual(limit.load_state("claude"), {})

  def test_bad_fields_are_dropped_not_trusted(self):
    self.cache.mkdir(parents=True)
    limit.state_path("claude").write_text(json.dumps({
      "fetchedAt": "yesterday", "windows": [{"key": "x"}],
      "samples": {"a": [[1, 2, 3], [1, 2], "x", [1, "z", None]], "b": "no"}}))
    state = limit.load_state("claude")
    self.assertNotIn("fetchedAt", state)
    self.assertNotIn("windows", state)
    self.assertEqual(state["samples"], {"a": [[1, 2, 3]]})

  def test_a_broken_state_file_still_returns_a_record(self):
    self.login()
    self.cache.mkdir(parents=True)
    limit.state_path("claude").write_text(json.dumps([1, 2]))
    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(USAGE)), \
         mock.patch.object(limit.time, "time", return_value=NOW), \
         mock.patch.dict(limit.DETECTORS, {"codex": lambda: False, "gemini": lambda: False}):
      out = limit.run(force=True)
    self.assertTrue(out["providers"][0]["ok"])

  def test_one_failing_provider_does_not_blank_the_others(self):
    real = limit.poll

    def poll(pid, *a):
      if pid == "codex":
        raise ValueError("bug")
      return real(pid, *a)

    self.login()
    with mock.patch.object(limit, "poll", poll), mock.patch.object(limit.time, "time", return_value=NOW), \
         mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(USAGE)), \
         mock.patch.dict(limit.DETECTORS, {"codex": lambda: True, "gemini": lambda: False}):
      out = limit.run(force=True)
    by_id = {p["id"]: p for p in out["providers"]}
    self.assertEqual(by_id["codex"]["error"], "internal")
    self.assertTrue(by_id["claude"]["ok"])

  def test_an_unwritable_cache_is_reported_not_fatal(self):
    self.login()
    with mock.patch.object(limit, "save_state", side_effect=OSError("full")), mock.patch.object(limit.time, "time", return_value=NOW), \
         mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(USAGE)):
      record = limit.poll("claude", NOW, True, False)
    self.assertEqual(record["error"], "cache")

  def test_a_failed_try_counts_for_the_throttle(self):
    limit.make_cache_dir()
    calls = []

    def boom(*a, **k):
      calls.append(1)
      raise limit.Failure("unavailable")

    with mock.patch.dict(limit.FETCHERS, {"codex": boom}):
      limit.poll("codex", NOW, False, False)
      limit.poll("codex", NOW + 30, False, False)
      self.assertEqual(len(calls), 1)
      limit.poll("codex", NOW + 31, True, False)
      self.assertEqual(len(calls), 2)
      limit.poll("codex", NOW + 31 + limit.MIN_INTERVAL["codex"], False, False)
      self.assertEqual(len(calls), 3)


class RpcLoop(unittest.TestCase):
  """rpc_request against a real child process, so select() meets real pipes."""

  def child(self, script):
    return limit.subprocess.Popen([sys.executable, "-c", script], stdin=limit.subprocess.PIPE,
                                  stdout=limit.subprocess.PIPE, text=True)

  def tearDown(self):
    for p in getattr(self, "procs", []):
      p.kill()
      p.wait()
      p.stdin.close()
      p.stdout.close()

  def start(self, script):
    proc = self.child(script)
    self.procs = [proc]
    return proc

  def test_skips_noise_and_other_ids_and_finds_the_reply_sent_in_one_chunk(self):
    proc = self.start("import sys,time\n"
                      "sys.stdout.write('not json\\n{\"method\":\"note\"}\\n{\"id\":9}\\n{\"id\":1,\"result\":{\"a\":1}}\\n{\"id\":2,\"result\":2}\\n')\n"
                      "sys.stdout.flush()\ntime.sleep(5)\n")
    self.assertEqual(limit.rpc_request(proc, 1, "m", timeout=3), {"id": 1, "result": {"a": 1}})
    # The next reply arrived in the same chunk: it must not be lost to select().
    self.assertEqual(limit.rpc_request(proc, 2, "n", timeout=0.5), {"id": 2, "result": 2})

  def test_end_of_output_is_not_a_timeout(self):
    proc = self.start("pass")
    with self.assertRaises(EOFError):
      limit.rpc_request(proc, 1, "m", timeout=3)

  def test_silence_runs_into_the_deadline(self):
    proc = self.start("import time\ntime.sleep(5)")
    started = time.time()
    with self.assertRaises(TimeoutError):
      limit.rpc_request(proc, 1, "m", timeout=0.6)
    self.assertLess(time.time() - started, 3)


class Plan(Sandbox):
  def test_names(self):
    self.login()
    self.assertEqual(limit.claude_plan(), "Max 5x")

  def test_20x_and_plain(self):
    self.login(rateLimitTier="default_claude_max_20x")
    self.assertEqual(limit.claude_plan(), "Max 20x")
    self.login(rateLimitTier="")
    self.assertEqual(limit.claude_plan(), "Max")

  def test_no_file(self):
    self.assertEqual(limit.claude_plan(), "")
    self.assertEqual(limit.token(), ("", 0))


class Renew(Sandbox):
  def answer(self, **kw):
    return {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 28800,
            "refresh_token_expires_in": 86400, "scope": "user:inference user:profile", **kw}

  def test_posts_the_claude_code_refresh_request_and_stores_the_pair(self):
    path = self.login(expires_in=-5)
    seen = {}

    def urlopen(request, timeout=0):
      seen["url"], seen["body"] = request.full_url, json.loads(request.data)
      return FakeResponse(self.answer())

    with mock.patch.object(limit.urllib.request, "urlopen", urlopen):
      access, expires, error = limit.renew(NOW)
    self.assertEqual((access, error), ("new-access", ""))
    self.assertEqual(seen["url"], limit.TOKEN_URL)
    self.assertEqual(seen["body"], {
      "grant_type": "refresh_token", "refresh_token": "old-refresh",
      "client_id": limit.CLIENT_ID, "scope": "user:inference user:profile"})
    stored = self.saved()
    self.assertEqual(stored["claudeAiOauth"]["accessToken"], "new-access")
    self.assertEqual(stored["claudeAiOauth"]["refreshToken"], "new-refresh")
    self.assertEqual(stored["claudeAiOauth"]["expiresAt"], int((NOW + 28800) * 1000))
    self.assertEqual(stored["claudeAiOauth"]["subscriptionType"], "max")
    self.assertEqual(stored["other"], {"keep": "me"})
    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
    self.assertFalse((self.claude / ".credentials.json.tmp").exists())

  def test_keeps_old_refresh_token_when_the_answer_has_none(self):
    self.login(expires_in=-5)
    body = self.answer()
    del body["refresh_token"]
    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(body)):
      limit.renew(NOW)
    self.assertEqual(self.saved()["claudeAiOauth"]["refreshToken"], "old-refresh")

  def test_uses_a_pair_claude_code_renewed_in_the_meantime(self):
    self.login(access="fresh", refresh="fresh-r", expires_in=7200)
    with mock.patch.object(limit.urllib.request, "urlopen", side_effect=AssertionError("no second renewal")):
      access, _, error = limit.renew(NOW, used="dead")
    self.assertEqual((access, error), ("fresh", ""))

  def test_dead_token_with_same_value_is_renewed(self):
    self.login(access="dead", expires_in=7200)
    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(self.answer())):
      access, _, error = limit.renew(NOW, used="dead")
    self.assertEqual((access, error), ("new-access", ""))

  def test_rejected_refresh_token_is_expired_and_file_untouched(self):
    path = self.login(expires_in=-5)
    before = path.read_text()
    with mock.patch.object(limit.urllib.request, "urlopen", side_effect=http_error(400)):
      self.assertEqual(limit.renew(NOW), ("", 0, "expired"))
    self.assertEqual(path.read_text(), before)

  def test_server_trouble_is_network(self):
    self.login(expires_in=-5)
    with mock.patch.object(limit.urllib.request, "urlopen", side_effect=http_error(503)):
      self.assertEqual(limit.renew(NOW)[2], "network")
    with mock.patch.object(limit.urllib.request, "urlopen", side_effect=OSError("down")):
      self.assertEqual(limit.renew(NOW)[2], "network")

  def test_garbage_answer_is_network_and_file_untouched(self):
    path = self.login(expires_in=-5)
    before = path.read_text()
    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse({"oops": 1})):
      self.assertEqual(limit.renew(NOW)[2], "network")
    self.assertEqual(path.read_text(), before)

  def test_no_refresh_token_or_no_file(self):
    self.login(refresh="", expires_in=-5)
    self.assertEqual(limit.renew(NOW)[2], "expired")
    (self.claude / ".credentials.json").unlink()
    self.assertEqual(limit.renew(NOW)[2], "auth")

  def test_unwritable_file_still_returns_the_new_token(self):
    self.login(expires_in=-5)
    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(self.answer())), \
         mock.patch.object(limit, "save_login", side_effect=OSError("read-only")):
      access, _, error = limit.renew(NOW)
    self.assertEqual((access, error), ("new-access", "writefail"))

  def test_a_lost_pair_is_used_once_then_reported(self):
    self.login(expires_in=-5)
    state = {}
    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(self.answer())), \
         mock.patch.object(limit, "save_login", side_effect=OSError("read-only")):
      self.assertEqual(limit.renewed(state, NOW), ("new-access", ""))
      self.assertEqual(limit.renewed(state, NOW + 5), ("", "writefail"))

  def test_does_not_overwrite_a_login_claude_code_rotated_meanwhile(self):
    path = self.login(expires_in=-5)

    def urlopen(request, timeout=0):
      # Claude Code renews while our request is in flight.
      self.login(access="cc-access", refresh="cc-refresh", expires_in=7200)
      return FakeResponse(self.answer())

    with mock.patch.object(limit.urllib.request, "urlopen", urlopen):
      access, _, error = limit.renew(NOW)
    self.assertEqual((access, error), ("new-access", ""))
    self.assertEqual(self.saved()["claudeAiOauth"]["accessToken"], "cc-access")
    self.assertEqual(self.saved()["claudeAiOauth"]["refreshToken"], "cc-refresh")

  def test_save_login_keeps_the_mode_and_the_symlink(self):
    for mode in (0o640, 0o400):
      path = self.login()
      path.chmod(mode)
      self.assertTrue(limit.save_login({"accessToken": "a", "refreshToken": "r"}, "old-refresh"))
      self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
      self.assertEqual(self.saved()["other"], {"keep": "me"})
    real = self.claude / "real.json"
    path.replace(real)
    path.symlink_to(real)
    self.assertTrue(limit.save_login({"accessToken": "b", "refreshToken": "r2"}, "r"))
    self.assertTrue(path.is_symlink())
    self.assertEqual(json.loads(real.read_text())["claudeAiOauth"]["accessToken"], "b")

  def test_retry_pause_after_a_failure(self):
    self.login(expires_in=-5)
    state = {}
    with mock.patch.object(limit.urllib.request, "urlopen", side_effect=http_error(400)) as m:
      self.assertEqual(limit.renewed(state, NOW), ("", "expired"))
      self.assertEqual(limit.renewed(state, NOW + 60), ("", "expired"))
      self.assertEqual(m.call_count, 1)
    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(self.answer())):
      self.assertEqual(limit.renewed(state, NOW + limit.REFRESH_RETRY + 1), ("new-access", ""))
    self.assertNotIn("renewRetryAt", state)


class Run(Sandbox):
  """The Claude provider through poll()/run(): fetching, back-off, samples."""

  def run_with(self, now=NOW, fetch=None, force=False, renew=True):
    fetch = fetch or (lambda access: limit.windows(USAGE))
    with mock.patch.object(limit.time, "time", return_value=now), mock.patch.object(limit, "claude_request", fetch):
      return limit.run(force, renew, only=["claude"])["providers"][0]

  def windows_future(self):
    return [{"key": "five_hour", "group": "session", "model": "", "util": 20.0,
             "resetsAt": NOW + 3600, "window": 18000, "severity": ""}]

  def state(self):
    return json.loads((self.cache / "state-claude.json").read_text())

  def test_ok_path_writes_state_and_reports_windows(self):
    self.login()
    out = self.run_with(fetch=lambda a: self.windows_future())
    self.assertTrue(out["ok"])
    self.assertEqual(out["error"], "")
    self.assertEqual((out["id"], out["name"], out["tool"], out["cmd"]), ("claude", "Claude", "Claude Code", "claude"))
    self.assertEqual(out["plan"], "Max 5x")
    self.assertEqual(out["windows"][0]["util"], 20.0)
    self.assertIsNone(out["windows"][0]["rate"])
    self.assertEqual(len(self.state()["samples"]["five_hour"]), 1)

  def test_no_login_means_claude_is_not_listed(self):
    self.assertEqual(limit.run(only=["claude"])["providers"], [])

  def test_empty_login_file_is_auth(self):
    path = self.login()
    path.write_text(json.dumps({"claudeAiOauth": {}}))
    out = self.run_with()
    self.assertEqual((out["ok"], out["error"]), (False, "auth"))

  def test_expired_token_is_renewed_and_used(self):
    self.login(expires_in=-100)
    used = []

    def fetch(access):
      used.append(access)
      return self.windows_future()

    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(
        {"access_token": "new-access", "refresh_token": "r2", "expires_in": 3600})):
      out = self.run_with(fetch=fetch)
    self.assertEqual(used, ["new-access"])
    self.assertEqual((out["ok"], out["error"]), (True, ""))
    self.assertEqual(self.saved()["claudeAiOauth"]["accessToken"], "new-access")

  def test_expired_and_unrenewable_reports_expired(self):
    self.login(expires_in=-100)
    with mock.patch.object(limit.urllib.request, "urlopen", side_effect=http_error(401)):
      out = self.run_with()
    self.assertEqual((out["ok"], out["error"]), (False, "expired"))

  def test_without_renew_the_login_file_is_never_touched(self):
    path = self.login(expires_in=-100)
    before = path.read_text()
    with mock.patch.object(limit.urllib.request, "urlopen", side_effect=AssertionError("no request")):
      out = self.run_with(renew=False)
    self.assertEqual((out["ok"], out["error"]), (False, "expired"))
    self.assertEqual(path.read_text(), before)

  def test_without_renew_a_rejected_token_is_expired_not_renewed(self):
    path = self.login(access="dead", expires_in=3600)
    before = path.read_text()
    out = self.run_with(renew=False, fetch=lambda a: (_ for _ in ()).throw(http_error(401)))
    self.assertEqual(out["error"], "expired")
    self.assertEqual(path.read_text(), before)

  def test_401_from_usage_renews_once_and_retries(self):
    self.login(access="dead", expires_in=3600)
    calls = []

    def fetch(access):
      calls.append(access)
      if access == "dead":
        raise http_error(401)
      return self.windows_future()

    with mock.patch.object(limit.urllib.request, "urlopen", lambda *a, **k: FakeResponse(
        {"access_token": "alive", "refresh_token": "r2", "expires_in": 3600})):
      out = self.run_with(fetch=fetch)
    self.assertEqual(calls, ["dead", "alive"])
    self.assertTrue(out["ok"])

  def test_429_backs_off_and_respects_retry_after(self):
    self.login()
    out = self.run_with(fetch=lambda a: (_ for _ in ()).throw(http_error(429, {"retry-after": "300"})))
    self.assertEqual(out["error"], "ratelimit")
    self.assertEqual(self.state()["backoffUntil"], NOW + 300)
    boom = mock.Mock(side_effect=AssertionError("must not fetch"))
    self.assertEqual(self.run_with(now=NOW + 100, fetch=boom)["error"], "ratelimit")

  def test_other_http_and_network_errors(self):
    self.login()
    self.assertEqual(self.run_with(fetch=lambda a: (_ for _ in ()).throw(http_error(500)))["error"], "http 500")
    self.assertEqual(self.run_with(now=NOW + 100, fetch=lambda a: (_ for _ in ()).throw(OSError("x")))["error"], "network")

  def test_does_not_refetch_inside_the_minimum_interval(self):
    self.login()
    self.run_with(fetch=lambda a: self.windows_future())
    boom = mock.Mock(side_effect=AssertionError("must not fetch"))
    out = self.run_with(now=NOW + 10, fetch=boom)
    self.assertTrue(out["ok"])
    forced = self.run_with(now=NOW + 11, fetch=lambda a: self.windows_future(), force=True)
    self.assertTrue(forced["ok"])

  def test_stale_numbers_count_as_current_for_five_minutes(self):
    self.login()
    self.run_with(fetch=lambda a: self.windows_future())
    out = self.run_with(now=NOW + 120, fetch=lambda a: (_ for _ in ()).throw(OSError("x")))
    self.assertEqual((out["ok"], out["error"]), (True, "network"))
    out = self.run_with(now=NOW + 400, fetch=lambda a: (_ for _ in ()).throw(OSError("x")))
    self.assertEqual((out["ok"], out["error"]), (False, "network"))

  def test_a_window_that_reset_reads_zero(self):
    self.login()
    self.run_with(fetch=lambda a: self.windows_future())
    out = self.run_with(now=NOW + 7200, fetch=lambda a: (_ for _ in ()).throw(OSError("x")))
    self.assertEqual((out["windows"][0]["util"], out["windows"][0]["resetsAt"]), (0.0, None))

  def test_ratio_prior_before_any_learning(self):
    self.login()
    out = self.run_with(fetch=lambda a: self.windows_future())
    self.assertAlmostEqual(out["ratio"], limit.RATIO_PRIOR)
    self.assertEqual(out["ratioSpan"], 0)

  def test_output_is_json_serialisable(self):
    self.login()
    json.dumps(limit.run(only=["claude"]))

  def history(self, rows, org="org-1"):
    """rows: (minutes since the first sample, 5-hour %, 7-day %)."""
    samples = [{"t": int((NOW + m * 60) * 1000), "org": org, "u": {"fh": fh, "sd": sd, "xu": 0}} for m, fh, sd in rows]
    limit.CLAUDE_USAGE_HISTORY.write_text(json.dumps({"version": 2, "samples": samples}))

  def test_history_totals_sum_the_rises_between_close_samples(self):
    self.history([(0, 0, 10), (15, 4, 10), (30, 10, 11), (45, 10, 12)])
    self.assertEqual(limit.claude_history_totals(), (10.0, 2.0))

  def test_history_skips_resets_and_gaps(self):
    self.history([(0, 50, 20), (15, 2, 20), (30, 8, 21), (31 + 60, 20, 30), (106, 30, 31)])
    # (0->15) the 5-hour counter fell, (30->91) too far apart, the rest count
    self.assertEqual(limit.claude_history_totals(), (16.0, 2.0))

  def test_history_uses_only_the_latest_org(self):
    limit.CLAUDE_USAGE_HISTORY.write_text(json.dumps({"samples": [
      {"t": int(NOW * 1000), "org": "old", "u": {"fh": 0, "sd": 0}},
      {"t": int((NOW + 900) * 1000), "org": "old", "u": {"fh": 50, "sd": 40}},
      {"t": int((NOW + 1800) * 1000), "org": "new", "u": {"fh": 0, "sd": 0}},
      {"t": int((NOW + 2700) * 1000), "org": "new", "u": {"fh": 10, "sd": 1}},
    ]}))
    self.assertEqual(limit.claude_history_totals(), (10.0, 1.0))

  def test_history_missing_or_broken_is_none(self):
    self.assertIsNone(limit.claude_history_totals())
    limit.CLAUDE_USAGE_HISTORY.write_text("{nope")
    self.assertIsNone(limit.claude_history_totals())
    limit.CLAUDE_USAGE_HISTORY.write_text(json.dumps({"samples": [{"t": 1, "org": "x"}]}))
    self.assertIsNone(limit.claude_history_totals())
    self.history([(0, 5, 5), (15, 5, 5)])
    self.assertIsNone(limit.claude_history_totals())

  def test_ratio_follows_the_history_when_it_holds_more(self):
    self.login()
    self.history([(0, 0, 0), (15, 100, 14)])
    out = self.run_with(fetch=lambda a: self.windows_future())
    self.assertEqual((out["ratioSource"], out["ratioSpan"]), ("history", 100.0))
    self.assertAlmostEqual(out["ratio"], (14 + limit.RATIO_PRIOR * limit.RATIO_PRIOR_SPAN) / (100 + limit.RATIO_PRIOR_SPAN))

  def test_ratio_keeps_the_widgets_own_when_it_has_learned_more(self):
    self.login()
    self.history([(0, 0, 0), (15, 10, 5)])
    (self.cache.parent / "legacy-cache").mkdir()
    (self.cache.parent / "legacy-cache" / "state.json").write_text(json.dumps({"ratio": {"ds": 100.0, "dw": 20.0}}))
    out = self.run_with(fetch=lambda a: self.windows_future())
    self.assertEqual((out["ratioSource"], out["ratioSpan"]), ("learned", 100.0))

  def test_ratio_source_is_prior_without_any_data(self):
    self.login()
    self.assertEqual(self.run_with(fetch=lambda a: self.windows_future())["ratioSource"], "prior")

  def test_other_providers_never_read_the_claude_history(self):
    self.history([(0, 0, 0), (15, 100, 14)])
    self.assertEqual(limit.ratio_inputs("codex", {}), (0, 0, "prior"))
    self.assertEqual(limit.ratio_inputs("gemini", {"ratio": {"ds": 4, "dw": 1}}), (4, 1, "learned"))

  def test_legacy_state_is_carried_over(self):
    self.login()
    legacy = self.cache.parent / "legacy-cache"
    legacy.mkdir()
    (legacy / "state.json").write_text(json.dumps({"ratio": {"ds": 100.0, "dw": 20.0}}))
    out = self.run_with(fetch=lambda a: self.windows_future())
    self.assertEqual(out["ratioSpan"], 100.0)
    self.assertAlmostEqual(out["ratio"], (20 + 1.5) / (100 + 15))


RATE_LIMITS = {
  "planType": "plus",
  "primary": {"usedPercent": 12, "windowDurationMins": 300, "resetsAt": NOW + 3600},
  "secondary": {"usedPercent": 40.5, "windowDurationMins": 10080, "resetsAt": NOW + 86400},
}


class CodexWindows(unittest.TestCase):
  def test_primary_and_secondary(self):
    out = limit.codex_windows(RATE_LIMITS)
    self.assertEqual([(w["key"], w["group"], w["util"], w["window"]) for w in out],
                     [("codex:primary", "session", 12.0, 18000), ("codex:secondary", "weekly", 40.5, 604800)])
    self.assertEqual(out[0]["resetsAt"], NOW + 3600)

  def test_a_single_long_window_is_a_weekly_group(self):
    out = limit.codex_windows({"primary": {"usedPercent": 0, "windowDurationMins": 43200, "resetsAt": NOW + 5}})
    self.assertEqual([(w["group"], w["window"]) for w in out], [("weekly", 43200 * 60)])

  def test_missing_length_falls_back_to_the_slot_default(self):
    out = limit.codex_windows({"primary": {"usedPercent": 1}, "secondary": {"usedPercent": 2}})
    self.assertEqual([w["window"] for w in out], [300 * 60, 10080 * 60])
    self.assertIsNone(out[0]["resetsAt"])

  def test_ignores_empty_and_broken_slots(self):
    self.assertEqual(limit.codex_windows({}), [])
    self.assertEqual(limit.codex_windows({"primary": None, "secondary": {"usedPercent": None}}), [])
    self.assertEqual(limit.codex_windows({"primary": {"usedPercent": "x"}}), [])

  def test_percent_is_clamped(self):
    self.assertEqual(limit.codex_windows({"primary": {"usedPercent": 250, "windowDurationMins": 60}})[0]["util"], 100.0)


class FakeProc:
  """A `codex app-server` that answers the three RPC calls from a script."""

  def __init__(self, answers):
    self.answers = answers
    self.sent = []
    self.stdin = mock.Mock()
    self.stdin.write = lambda text: self.sent.append(json.loads(text))
    self.stdout = mock.Mock()
    self.terminated = False

  def terminate(self):
    self.terminated = True

  def wait(self, timeout=None):
    return 0

  def kill(self):
    pass


class CodexFetch(Sandbox):
  def reply(self, answers):
    proc = FakeProc(answers)

    def rpc(p, request_id, method, params=None, timeout=0):
      if isinstance(answers.get(method), Exception):
        raise answers[method]
      proc.sent.append((method, params))
      return {"id": request_id, **answers[method]}

    patches = (mock.patch.object(limit, "find_codex", return_value="/bin/codex"),
               mock.patch.object(limit.subprocess, "Popen", return_value=proc),
               mock.patch.object(limit, "rpc_request", rpc))
    for p in patches:
      p.start()
      self.addCleanup(p.stop)
    return proc

  GOOD = {
    "initialize": {"result": {}},
    "account/read": {"result": {"account": {"type": "chatgpt", "planType": "plus"}}},
    "account/rateLimits/read": {"result": {"rateLimits": RATE_LIMITS}},
  }

  def test_fetch_returns_windows_and_plan_and_stops_the_process(self):
    proc = self.reply(self.GOOD)
    out = limit.fetch_codex({}, NOW, False)
    self.assertEqual(out["plan"], "Plus")
    self.assertEqual(len(out["windows"]), 2)
    self.assertTrue(proc.terminated)
    self.assertEqual(proc.sent[0][0], "initialize")
    self.assertEqual(proc.sent[0][1]["clientInfo"]["name"], "ismoil-ai-limits")

  def test_not_signed_in_is_auth(self):
    self.reply({**self.GOOD, "account/read": {"result": {"account": None}},
                "account/rateLimits/read": {"error": {"code": -1, "message": "no auth"}}})
    with self.assertRaises(limit.Failure) as ctx:
      limit.fetch_codex({}, NOW, False)
    self.assertEqual(ctx.exception.kind, "auth")

  def test_signed_in_but_no_limits_is_unavailable(self):
    self.reply({**self.GOOD, "account/rateLimits/read": {"error": {"code": -1, "message": "boom"}}})
    with self.assertRaises(limit.Failure) as ctx:
      limit.fetch_codex({}, NOW, False)
    self.assertEqual(ctx.exception.kind, "unavailable")

  def test_timeout_is_unavailable_and_process_is_still_stopped(self):
    proc = self.reply({**self.GOOD, "account/read": TimeoutError("account/read")})
    with self.assertRaises(limit.Failure) as ctx:
      limit.fetch_codex({}, NOW, False)
    self.assertEqual(ctx.exception.kind, "unavailable")
    self.assertTrue(proc.terminated)

  def test_no_binary_is_unavailable(self):
    with mock.patch.object(limit, "find_codex", return_value=None):
      with self.assertRaises(limit.Failure):
        limit.fetch_codex({}, NOW, False)

  def test_detected_needs_the_binary_and_a_login(self):
    with mock.patch.object(limit, "find_codex", return_value="/bin/codex"):
      self.assertFalse(limit.codex_detected())
      (self.codex / "auth.json").write_text("{}")
      self.assertTrue(limit.codex_detected())
    with mock.patch.object(limit, "find_codex", return_value=None):
      self.assertFalse(limit.codex_detected())


BUCKETS = {"buckets": [
  {"modelId": "gemini-2.5-pro", "remainingFraction": 0.75, "resetTime": "2027-01-15T10:00:00Z", "tokenType": "REQUESTS"},
  {"modelId": "gemini-3.1-pro-preview", "remainingFraction": 0.5, "resetTime": "2027-01-15T11:00:00Z"},
  {"modelId": "gemini-2.5-flash", "remainingFraction": 1, "resetTime": "2027-01-15T12:00:00Z"},
  {"modelId": "gemini-2.5-flash-lite", "remainingFraction": 0.9},
  {"modelId": "gemini-embedding", "remainingFraction": 0.2},
  {"modelId": "", "remainingFraction": 0.1},
  {"modelId": "gemini-x-pro", "remainingFraction": "nan"},
  "junk",
]}


class GeminiWindows(unittest.TestCase):
  def test_families_use_the_most_used_bucket(self):
    out = limit.gemini_windows(BUCKETS)
    self.assertEqual([(w["key"], w["model"], round(w["util"], 6)) for w in out], [
      ("gemini:Pro", "Pro", 50.0), ("gemini:Flash", "Flash", 0.0), ("gemini:Flash Lite", "Flash Lite", 10.0),
      ("gemini:gemini-embedding", "gemini-embedding", 80.0)])
    self.assertEqual(out[0]["resetsAt"], limit.parse_time("2027-01-15T11:00:00Z"))
    self.assertEqual({w["window"] for w in out}, {86400})
    self.assertEqual({w["group"] for w in out}, {"weekly"})  # longer than six hours: paced in active hours

  def test_a_full_quota_has_no_remaining_amount(self):
    out = limit.gemini_windows({"buckets": [{"modelId": "gemini-2.5-pro", "remainingFraction": 1}]})
    self.assertEqual(out[0]["util"], 0.0)

  def test_fraction_is_clamped(self):
    out = limit.gemini_windows({"buckets": [{"modelId": "gemini-2.5-pro", "remainingFraction": -3}]})
    self.assertEqual(out[0]["util"], 100.0)

  def test_empty(self):
    self.assertEqual(limit.gemini_windows({}), [])
    self.assertEqual(limit.gemini_windows(None), [])

  def test_family(self):
    for model, family in (("gemini-2.5-pro", "Pro"), ("gemini-2.5-flash", "Flash"), ("gemini-2.5-flash-lite", "Flash Lite"),
                          ("gemini-2.5-flash_lite", "Flash Lite"), ("other", "other")):
      self.assertEqual(limit.gemini_family(model), family)


class GeminiFetch(Sandbox):
  def creds(self, expires_in=3600, access="g-access"):
    (self.gemini / "oauth_creds.json").write_text(json.dumps({
      "access_token": access, "refresh_token": "r", "expiry_date": int((NOW + expires_in) * 1000)}))

  def test_detected(self):
    self.assertFalse(limit.gemini_detected())
    self.creds()
    self.assertTrue(limit.gemini_detected())

  def test_fetch_discovers_the_project_then_reads_the_quota_and_caches_both(self):
    self.creds()
    calls = []

    def post(method, access, body):
      calls.append((method, access, body))
      if method == "loadCodeAssist":
        return {"cloudaicompanionProject": "proj-1", "currentTier": {"id": "standard-tier", "name": "Gemini Code Assist"}}
      return BUCKETS

    state = {}
    with mock.patch.object(limit, "gemini_post", post):
      out = limit.fetch_gemini(state, NOW, False)
      limit.fetch_gemini(state, NOW + 200, False)
    self.assertEqual([c[0] for c in calls], ["loadCodeAssist", "retrieveUserQuota", "retrieveUserQuota"])
    self.assertEqual(calls[1][2], {"project": "proj-1"})
    self.assertEqual(calls[0][1], "g-access")
    self.assertEqual(out["plan"], "Gemini Code Assist")
    self.assertEqual(len(out["windows"]), 4)

  def test_project_given_as_an_object(self):
    self.creds()
    state = {}
    with mock.patch.object(limit, "gemini_post", lambda m, a, b: {"cloudaicompanionProject": {"id": "p2"}} if m == "loadCodeAssist" else BUCKETS):
      limit.fetch_gemini(state, NOW, False)
    self.assertEqual(state["project"], "p2")

  def test_expired_token_is_expired_without_a_request(self):
    self.creds(expires_in=-5)
    with mock.patch.object(limit, "gemini_post", side_effect=AssertionError("no request")):
      with self.assertRaises(limit.Failure) as ctx:
        limit.fetch_gemini({}, NOW, True)
    self.assertEqual(ctx.exception.kind, "expired")

  def test_missing_token_is_auth(self):
    with self.assertRaises(limit.Failure) as ctx:
      limit.fetch_gemini({}, NOW, False)
    self.assertEqual(ctx.exception.kind, "auth")

  def test_http_errors_map_to_failures(self):
    self.creds()
    for code, kind in ((401, "expired"), (429, "ratelimit"), (500, "http 500")):
      with mock.patch.object(limit, "gemini_post", side_effect=http_error(code, {"retry-after": "30"})):
        with self.assertRaises(limit.Failure) as ctx:
          limit.fetch_gemini({}, NOW, False)
      self.assertEqual(ctx.exception.kind, kind)

  def test_empty_quota_is_unavailable(self):
    self.creds()
    with mock.patch.object(limit, "gemini_post", lambda m, a, b: {"cloudaicompanionProject": "p"} if m == "loadCodeAssist" else {}):
      with self.assertRaises(limit.Failure) as ctx:
        limit.fetch_gemini({}, NOW, False)
    self.assertEqual(ctx.exception.kind, "unavailable")


class RunAll(Sandbox):
  def setUp(self):
    super().setUp()
    self.login()
    self.creds_g()
    (self.codex / "auth.json").write_text("{}")
    codex = {"windows": limit.codex_windows(RATE_LIMITS), "plan": "Plus"}
    gem = {"windows": limit.gemini_windows(BUCKETS), "plan": "Standard"}
    for name, value in (("claude_request", lambda a: [{"key": "five_hour", "group": "session", "model": "", "util": 5.0,
                                                       "resetsAt": NOW + 600, "window": 18000, "severity": ""}]),
                        ("find_codex", lambda: "/bin/codex")):
      p = mock.patch.object(limit, name, value)
      p.start()
      self.addCleanup(p.stop)
    p = mock.patch.dict(limit.FETCHERS, {"codex": lambda s, n, r: codex, "gemini": lambda s, n, r: gem})
    p.start()
    self.addCleanup(p.stop)
    p = mock.patch.object(limit.time, "time", return_value=NOW)
    p.start()
    self.addCleanup(p.stop)

  def creds_g(self):
    (self.gemini / "oauth_creds.json").write_text(json.dumps({"access_token": "a", "expiry_date": int((NOW + 999) * 1000)}))

  def test_lists_every_detected_provider_in_order(self):
    out = limit.run()
    self.assertEqual([p["id"] for p in out["providers"]], ["claude", "codex", "gemini"])
    self.assertEqual(out["selected"], "claude")
    self.assertEqual([p["plan"] for p in out["providers"]], ["Max 5x", "Plus", "Standard"])
    self.assertEqual(len(out["providers"][1]["windows"]), 2)

  def test_each_provider_has_its_own_state_file(self):
    limit.run()
    self.assertEqual(sorted(p.name for p in self.cache.glob("state-*.json")), ["state-claude.json", "state-codex.json", "state-gemini.json"])

  def test_undetected_providers_are_left_out(self):
    (self.gemini / "oauth_creds.json").unlink()
    self.assertEqual([p["id"] for p in limit.run()["providers"]], ["claude", "codex"])

  def test_providers_filter(self):
    self.assertEqual([p["id"] for p in limit.run(only=["gemini", "claude"])["providers"]], ["claude", "gemini"])

  def test_one_failing_provider_does_not_hide_the_others(self):
    boom = mock.Mock(side_effect=limit.Failure("expired"))
    with mock.patch.dict(limit.FETCHERS, {"gemini": boom}):
      out = limit.run()
    by = {p["id"]: p for p in out["providers"]}
    self.assertEqual((by["gemini"]["ok"], by["gemini"]["error"]), (False, "expired"))
    self.assertTrue(by["claude"]["ok"] and by["codex"]["ok"])

  def test_a_crashing_fetcher_is_a_network_error(self):
    with mock.patch.dict(limit.FETCHERS, {"codex": mock.Mock(side_effect=RuntimeError("bug"))}):
      out = limit.run()
    self.assertEqual({p["id"]: p["error"] for p in out["providers"]}["codex"], "network")

  def test_selection_is_remembered_and_validated(self):
    limit.write_selected("codex")
    self.assertEqual(limit.run()["selected"], "codex")
    limit.write_selected("nonsense")  # ignored
    self.assertEqual(limit.run()["selected"], "codex")
    limit.write_selected("gemini")
    (self.gemini / "oauth_creds.json").unlink()  # selected but gone: fall back to the first
    self.assertEqual(limit.run()["selected"], "claude")

  def test_nothing_installed(self):
    (self.claude / ".credentials.json").unlink()
    (self.gemini / "oauth_creds.json").unlink()
    (self.codex / "auth.json").unlink()
    self.assertEqual(limit.run(), {"selected": "", "providers": []})

  def test_codex_is_asked_less_often_than_claude(self):
    calls = []
    with mock.patch.dict(limit.FETCHERS, {"codex": lambda s, n, r: calls.append(n) or {"windows": limit.codex_windows(RATE_LIMITS), "plan": ""}}):
      limit.run()
      with mock.patch.object(limit.time, "time", return_value=NOW + 60):
        limit.run()
      with mock.patch.object(limit.time, "time", return_value=NOW + 130):
        limit.run()
    self.assertEqual(len(calls), 2)


class Cli(Sandbox):
  def test_flags_reach_run(self):
    for argv, want in (([], (False, False, None)), (["--force"], (True, False, None)), (["--renew"], (False, True, None)),
                       (["--force", "--renew"], (True, True, None)), (["--providers", "codex, gemini"], (False, False, ["codex", "gemini"])),
                       (["--providers", "bogus"], (False, False, None)), (["--providers"], (False, False, None))):
      with mock.patch.object(limit, "run", return_value={}) as run, mock.patch("sys.stdout", io.StringIO()):
        limit.main(argv)
      run.assert_called_once_with(want[0], renew=want[1], only=want[2])

  def test_select_flag_writes_the_choice(self):
    with mock.patch.object(limit, "run", return_value={}), mock.patch("sys.stdout", io.StringIO()):
      limit.main(["--select", "codex"])
    self.assertEqual(limit.read_selected(), "codex")

  def test_prints_one_json_object(self):
    # run_path re-executes the module, so point it at the sandbox by environment.
    self.login()
    out = io.StringIO()
    env = {"CLAUDE_CONFIG_DIR": str(self.claude), "CODEX_HOME": str(self.codex), "XDG_CACHE_HOME": str(self.cache.parent),
           "HOME": str(self.cache.parent)}
    with mock.patch.dict(os.environ, env), mock.patch.object(sys, "argv", ["limit.py", "--force", "--providers", "claude"]), \
         mock.patch("sys.stdout", out), \
         mock.patch.object(urllib.request, "urlopen", lambda *a, **k: FakeResponse({"limits": []})):
      runpy.run_path(limit.__file__, run_name="__main__")
    data = json.loads(out.getvalue())
    self.assertEqual([p["id"] for p in data["providers"]], ["claude"])
    self.assertEqual(data["providers"][0]["windows"], [])


if __name__ == "__main__":
  unittest.main()
