#!/usr/bin/env python3
"""GitHub App installation-token helper for the `quibble-review` App.

Purpose: swap the review scripts off `GITHUB_TOKEN` (posts as
`github-actions[bot]`) onto the App's installation token (posts as
`quibble-review[bot]`). See refactor A of the reviewer-identity plan.

Public surface:
    get_installation_token(repo, *, app_id=None, private_key=None) -> str
    set_gh_env(repo) -> dict[str, str]
    AppAuthError

Only stdlib + `PyJWT` (which pulls `cryptography` for RS256) — no requests /
httpx. urllib.request is enough for two GitHub REST calls.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT; needs `cryptography` for RS256 (declared in workflow pins).


class AppAuthError(RuntimeError):
    """Raised for any App-auth failure — missing env, malformed key, HTTP error."""


# Module-level cache keyed by `owner/name`. Value is (token, expires_at_utc).
# Reused across calls within one workflow run so we do not reissue a token
# per subprocess. Invalidated 5 minutes before the actual `expires_at`
# (installation tokens live ~1 hour) so a slow caller can still finish its
# request without racing the wall clock.
_CACHE: dict[str, tuple[str, datetime]] = {}
_CACHE_SAFETY_MARGIN = timedelta(minutes=5)

_GITHUB_API = "https://api.github.com"
_JWT_TTL_SECONDS = 600  # 10 min — GitHub's ceiling.
_JWT_CLOCK_SKEW = 60  # `iat` = now-60s per GitHub's docs.


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _mint_jwt(app_id: str, private_key: str) -> str:
    """Sign an RS256 JWT for App-level auth (iss=app_id, iat=now-60s, exp=+10min)."""
    now = int(time.time())
    payload = {
        "iat": now - _JWT_CLOCK_SKEW,
        "exp": now + _JWT_TTL_SECONDS,
        "iss": str(app_id),
    }
    try:
        return jwt.encode(payload, private_key, algorithm="RS256")
    except Exception as exc:  # noqa: BLE001 — surface cause with context.
        raise AppAuthError(f"failed to sign App JWT (check QUIBBLE_APP_PRIVATE_KEY): {exc}") from exc


def _api_request(url: str, *, method: str, jwt_token: str) -> dict:
    """One JSON call against the GitHub REST API using an App JWT.

    Returns the parsed JSON body. Raises AppAuthError with the status + body
    prefix on any non-2xx so a workflow log is diagnosable without a debugger.
    """
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "quibble-review-app-auth/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400] if exc.fp else ""
        raise AppAuthError(
            f"GitHub API {method} {url} failed: {exc.code} {exc.reason} — {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise AppAuthError(f"GitHub API {method} {url} unreachable: {exc.reason}") from exc


def _installation_id(repo: str, jwt_token: str) -> int:
    owner_name = repo.strip()
    if "/" not in owner_name:
        raise AppAuthError(f"repo must be 'owner/name', got: {repo!r}")
    data = _api_request(
        f"{_GITHUB_API}/repos/{owner_name}/installation",
        method="GET",
        jwt_token=jwt_token,
    )
    iid = data.get("id")
    if not isinstance(iid, int):
        raise AppAuthError(f"installation lookup returned no id for {repo}: {data!r}")
    return iid


def _exchange_for_token(installation_id: int, jwt_token: str) -> tuple[str, datetime]:
    data = _api_request(
        f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens",
        method="POST",
        jwt_token=jwt_token,
    )
    token = data.get("token")
    expires_at = data.get("expires_at")
    if not token or not expires_at:
        raise AppAuthError(f"token exchange missing token/expires_at: {data!r}")
    # GitHub emits RFC3339 with a `Z` suffix; datetime.fromisoformat handles
    # the offset form (`+00:00`) directly, so translate `Z` first.
    expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    return token, expires_dt


def get_installation_token(
    repo: str,
    *,
    app_id: str | None = None,
    private_key: str | None = None,
) -> str:
    """Return a cached-or-fresh installation access token for `repo`.

    `repo` is `owner/name`. `app_id` / `private_key` default to the
    `QUIBBLE_APP_ID` / `QUIBBLE_APP_PRIVATE_KEY` env vars.

    Cache invalidates 5 minutes before the real `expires_at` so a slow caller
    does not race a mid-request expiry.
    """
    cached = _CACHE.get(repo)
    if cached is not None:
        token, expires_at = cached
        if _now_utc() + _CACHE_SAFETY_MARGIN < expires_at:
            return token

    resolved_app_id = app_id if app_id is not None else os.environ.get("QUIBBLE_APP_ID")
    resolved_key = (
        private_key if private_key is not None else os.environ.get("QUIBBLE_APP_PRIVATE_KEY")
    )
    if not resolved_app_id:
        raise AppAuthError("QUIBBLE_APP_ID not set in env (and no app_id kwarg passed)")
    if not resolved_key:
        raise AppAuthError(
            "QUIBBLE_APP_PRIVATE_KEY not set in env (and no private_key kwarg passed)"
        )

    jwt_token = _mint_jwt(resolved_app_id, resolved_key)
    iid = _installation_id(repo, jwt_token)
    token, expires_at = _exchange_for_token(iid, jwt_token)
    _CACHE[repo] = (token, expires_at)
    return token


def set_gh_env(repo: str) -> dict[str, str]:
    """Return `{'GH_TOKEN': <installation-token>}` — nothing else.

    Callers spread this into `subprocess.run(..., env={**os.environ, **set_gh_env(repo)})`
    so the `gh` CLI acts as the App for that call. Only GH_TOKEN is set — no
    other side-effects.
    """
    return {"GH_TOKEN": get_installation_token(repo)}


__all__ = ["AppAuthError", "get_installation_token", "set_gh_env"]
