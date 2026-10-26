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
    patches = [
      mock.patch.object(limit, "CLAUDE_DIR", self.claude),
      mock.patch.object(limit, "CACHE_DIR", self.cache),
      mock.patch.object(limit, "STATE", self.cache / "state.json"),
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


class Plan(Sandbox):
  def test_names(self):
    self.login()
    self.assertEqual(limit.plan(), "Max 5x")

  def test_20x_and_plain(self):
    self.login(rateLimitTier="default_claude_max_20x")
    self.assertEqual(limit.plan(), "Max 20x")
    self.login(rateLimitTier="")
    self.assertEqual(limit.plan(), "Max")

  def test_no_file(self):
    self.assertEqual(limit.plan(), "")
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
    self.assertEqual((access, error), ("new-access", ""))

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
  def run_with(self, now=NOW, fetch=None, force=False, renew=True):
    fetch = fetch or (lambda access: limit.windows(USAGE))
    with mock.patch.object(limit.time, "time", return_value=now), mock.patch.object(limit, "fetch", fetch):
      return limit.run(force, renew)

  def windows_future(self):
    return [{"key": "five_hour", "group": "session", "model": "", "util": 20.0,
             "resetsAt": NOW + 3600, "window": 18000, "severity": ""}]

  def test_ok_path_writes_state_and_reports_windows(self):
    self.login()
    out = self.run_with(fetch=lambda a: self.windows_future())
    self.assertTrue(out["ok"])
    self.assertEqual(out["error"], "")
    self.assertEqual(out["plan"], "Max 5x")
    self.assertEqual(out["windows"][0]["util"], 20.0)
    self.assertIsNone(out["windows"][0]["rate"])
    state = json.loads((self.cache / "state.json").read_text())
    self.assertEqual(len(state["samples"]["five_hour"]), 1)

  def test_no_login(self):
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
    state = json.loads((self.cache / "state.json").read_text())
    self.assertEqual(state["backoffUntil"], NOW + 300)
    # Still inside the back-off: no new request.
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
    json.dumps(self.run_with(fetch=lambda a: self.windows_future()))


class Cli(Sandbox):
  def test_prints_one_json_object(self):
    # run_path re-executes the module, so point it at the sandbox by environment.
    self.login()
    out = io.StringIO()
    env = {"CLAUDE_CONFIG_DIR": str(self.claude), "XDG_CACHE_HOME": str(self.cache.parent)}
    with mock.patch.dict(os.environ, env), mock.patch.object(sys, "argv", ["limit.py", "--force"]), \
         mock.patch("sys.stdout", out), \
         mock.patch.object(urllib.request, "urlopen", lambda *a, **k: FakeResponse({"limits": []})):
      runpy.run_path(limit.__file__, run_name="__main__")
    self.assertEqual(json.loads(out.getvalue())["windows"], [])

  def test_flags_reach_run(self):
    for argv, want in (([], (False, False)), (["--force"], (True, False)), (["--renew"], (False, True)), (["--force", "--renew"], (True, True))):
      with mock.patch.object(limit, "run", return_value={}) as run, mock.patch("sys.stdout", io.StringIO()):
        limit.main(argv)
      run.assert_called_once_with(*[want[0]], renew=want[1])


if __name__ == "__main__":
  unittest.main()
