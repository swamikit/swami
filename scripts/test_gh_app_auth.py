#!/usr/bin/env python3
"""Unit tests for scripts/gh_app_auth.py — no real GitHub calls.

Run: python3 -m unittest scripts.test_gh_app_auth -v
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

# Make `scripts.gh_app_auth` importable whether we're invoked from repo root
# (`python3 -m unittest scripts.test_gh_app_auth`) or from scripts/ directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import gh_app_auth  # noqa: E402


def _reset_cache() -> None:
    gh_app_auth._CACHE.clear()


def _fake_urlopen(body: dict) -> mock.MagicMock:
    """Build a context-manager mock that urlopen() can return."""
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps(body).encode("utf-8")
    ctx = mock.MagicMock()
    ctx.__enter__.return_value = resp
    ctx.__exit__.return_value = False
    return ctx


class MissingEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def test_missing_app_id_raises(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(gh_app_auth.AppAuthError) as ctx:
                gh_app_auth.get_installation_token("swamikit/swami")
            self.assertIn("QUIBBLE_APP_ID", str(ctx.exception))

    def test_missing_private_key_raises(self) -> None:
        with mock.patch.dict("os.environ", {"QUIBBLE_APP_ID": "4835970"}, clear=True):
            with self.assertRaises(gh_app_auth.AppAuthError) as ctx:
                gh_app_auth.get_installation_token("swamikit/swami")
            self.assertIn("QUIBBLE_APP_PRIVATE_KEY", str(ctx.exception))

    def test_bad_repo_form_raises(self) -> None:
        # Even with env set, a non-owner/name repo should raise before any HTTP
        # call — proven by not mocking urlopen at all (a real call would hang).
        env = {"QUIBBLE_APP_ID": "4835970", "QUIBBLE_APP_PRIVATE_KEY": "---KEY---"}
        with mock.patch.dict("os.environ", env, clear=True), mock.patch.object(
            gh_app_auth.jwt, "encode", return_value="jwt.token.here"
        ):
            with self.assertRaises(gh_app_auth.AppAuthError) as ctx:
                gh_app_auth.get_installation_token("not-a-slug")
            self.assertIn("owner/name", str(ctx.exception))


class JWTConstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def test_jwt_claims_are_correct(self) -> None:
        """iss=app_id, iat≈now-60s, exp≈now+600s, algorithm=RS256."""
        env = {"QUIBBLE_APP_ID": "4835970", "QUIBBLE_APP_PRIVATE_KEY": "---KEY---"}
        with mock.patch.dict("os.environ", env, clear=True), mock.patch.object(
            gh_app_auth.jwt, "encode", return_value="jwt.token.here"
        ) as m_encode, mock.patch(
            "urllib.request.urlopen"
        ) as m_urlopen:
            # Return installation, then token.
            future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            m_urlopen.side_effect = [
                _fake_urlopen({"id": 12345678}),
                _fake_urlopen({"token": "ghs_deadbeef", "expires_at": future}),
            ]
            token = gh_app_auth.get_installation_token("swamikit/swami")
            self.assertEqual(token, "ghs_deadbeef")

        # Verify jwt.encode was called with the right shape.
        self.assertEqual(m_encode.call_count, 1)
        args, kwargs = m_encode.call_args
        payload, key = args[0], args[1]
        self.assertEqual(kwargs.get("algorithm"), "RS256")
        self.assertEqual(payload["iss"], "4835970")
        self.assertEqual(key, "---KEY---")
        # iat is now-60, exp is now+600 — allow small skew for the test wall clock.
        import time as _time

        now = int(_time.time())
        self.assertLessEqual(abs(payload["iat"] - (now - 60)), 5)
        self.assertLessEqual(abs(payload["exp"] - (now + 600)), 5)


class HTTPExchangeTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def test_calls_expected_urls_with_bearer_jwt(self) -> None:
        env = {"QUIBBLE_APP_ID": "4835970", "QUIBBLE_APP_PRIVATE_KEY": "---KEY---"}
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with mock.patch.dict("os.environ", env, clear=True), mock.patch.object(
            gh_app_auth.jwt, "encode", return_value="jwt.token.here"
        ), mock.patch("urllib.request.urlopen") as m_urlopen:
            m_urlopen.side_effect = [
                _fake_urlopen({"id": 42}),
                _fake_urlopen({"token": "ghs_xyz", "expires_at": future}),
            ]
            gh_app_auth.get_installation_token("swamikit/swami")

        self.assertEqual(m_urlopen.call_count, 2)
        # First call: GET /repos/{owner}/{repo}/installation
        req1 = m_urlopen.call_args_list[0].args[0]
        self.assertEqual(req1.get_method(), "GET")
        self.assertEqual(
            req1.full_url,
            "https://api.github.com/repos/swamikit/swami/installation",
        )
        self.assertEqual(req1.get_header("Authorization"), "Bearer jwt.token.here")
        # Second call: POST /app/installations/{iid}/access_tokens
        req2 = m_urlopen.call_args_list[1].args[0]
        self.assertEqual(req2.get_method(), "POST")
        self.assertEqual(
            req2.full_url,
            "https://api.github.com/app/installations/42/access_tokens",
        )
        self.assertEqual(req2.get_header("Authorization"), "Bearer jwt.token.here")


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def test_repeat_call_within_ttl_returns_cached(self) -> None:
        env = {"QUIBBLE_APP_ID": "4835970", "QUIBBLE_APP_PRIVATE_KEY": "---KEY---"}
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with mock.patch.dict("os.environ", env, clear=True), mock.patch.object(
            gh_app_auth.jwt, "encode", return_value="jwt.token.here"
        ), mock.patch("urllib.request.urlopen") as m_urlopen:
            m_urlopen.side_effect = [
                _fake_urlopen({"id": 42}),
                _fake_urlopen({"token": "ghs_first", "expires_at": future}),
            ]
            t1 = gh_app_auth.get_installation_token("swamikit/swami")
            t2 = gh_app_auth.get_installation_token("swamikit/swami")

        self.assertEqual(t1, "ghs_first")
        self.assertEqual(t2, "ghs_first")
        # Second call must NOT touch the network — exactly 2 urlopen calls
        # (installation lookup + token exchange) for the first, zero for the
        # second.
        self.assertEqual(m_urlopen.call_count, 2)

    def test_cache_invalidates_within_safety_margin(self) -> None:
        """Expiry inside the 5-min safety margin should trigger a re-mint."""
        env = {"QUIBBLE_APP_ID": "4835970", "QUIBBLE_APP_PRIVATE_KEY": "---KEY---"}
        # First response expires "soon" (2 min in the future — inside the 5-min
        # safety margin), so a second call must not reuse it.
        soon = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
        far = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with mock.patch.dict("os.environ", env, clear=True), mock.patch.object(
            gh_app_auth.jwt, "encode", return_value="jwt.token.here"
        ), mock.patch("urllib.request.urlopen") as m_urlopen:
            m_urlopen.side_effect = [
                _fake_urlopen({"id": 42}),
                _fake_urlopen({"token": "ghs_first", "expires_at": soon}),
                _fake_urlopen({"id": 42}),
                _fake_urlopen({"token": "ghs_second", "expires_at": far}),
            ]
            t1 = gh_app_auth.get_installation_token("swamikit/swami")
            t2 = gh_app_auth.get_installation_token("swamikit/swami")

        self.assertEqual(t1, "ghs_first")
        self.assertEqual(t2, "ghs_second")
        # Four urlopen calls total: two per exchange, two exchanges.
        self.assertEqual(m_urlopen.call_count, 4)


class SetGhEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def test_returns_only_gh_token(self) -> None:
        env = {"QUIBBLE_APP_ID": "4835970", "QUIBBLE_APP_PRIVATE_KEY": "---KEY---"}
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with mock.patch.dict("os.environ", env, clear=True), mock.patch.object(
            gh_app_auth.jwt, "encode", return_value="jwt.token.here"
        ), mock.patch("urllib.request.urlopen") as m_urlopen:
            m_urlopen.side_effect = [
                _fake_urlopen({"id": 42}),
                _fake_urlopen({"token": "ghs_only", "expires_at": future}),
            ]
            out = gh_app_auth.set_gh_env("swamikit/swami")
        self.assertEqual(out, {"GH_TOKEN": "ghs_only"})


if __name__ == "__main__":
    unittest.main()
