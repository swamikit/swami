"""Small provider-abstraction over LLM chat APIs.

Scripts call :func:`chat` (or :func:`chat_with_fallback`) with a provider name
and never touch a vendor SDK directly. That lets ``run-claude-review.py`` and
friends switch between Anthropic (paid, high quality), Gemini (free tier
generous), and OpenRouter (free-tier friendly meta-router) with a single env
var flip instead of code churn.

Design constraints (see Samuel's 2026-09-04 request for free-model integration):

* This module is **stdlib-only at import time**. Provider SDKs are lazy-imported
  inside the per-provider helpers so a script that only ever uses one provider
  doesn't need every SDK installed on the runner.
* Each provider maps its 429 / rate-limit exception onto :class:`RateLimited`
  so :func:`chat_with_fallback` can catch it and cut over to the paid escape
  hatch without knowing which vendor raised.
* Other API errors bubble up as :class:`ModelError` — same reason.

The fallback pattern is: free/cheap primary, Opus (or whichever paid model the
caller trusts) as the secondary. When the primary trips a quota, the secondary
runs and returns; ``chat_with_fallback`` also reports which provider actually
answered so the caller can log it.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional, Tuple


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ModelError(Exception):
    """Any provider-side error that isn't a rate limit."""


class RateLimited(ModelError):
    """HTTP 429 (or the provider-SDK equivalent). Raised so a caller can
    fall back to another provider without inspecting the wrapped SDK error."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chat(
    *,
    provider: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 8000,
    schema: Optional[dict] = None,
) -> str:
    """Return the full (non-streaming) model reply text.

    ``provider`` selects the backend: ``"anthropic"``, ``"gemini"``, or
    ``"openrouter"``. ``model`` is the provider-native id (e.g.
    ``"claude-opus-5"``, ``"gemini-2.0-flash-exp"``,
    ``"anthropic/claude-3.5-sonnet"``).

    ``schema`` — a JSON Schema dict — turns on structured output. Providers
    that support it natively (Gemini's ``response_schema``, OpenRouter's
    ``response_format={"type": "json_schema", ...}`` on capable models) get it
    on the wire; Anthropic (no native structured output) gets a
    prompt-engineered nudge appended to the system prompt.

    Raises :class:`RateLimited` on 429 and :class:`ModelError` for other
    provider errors.
    """
    if provider == "anthropic":
        return _chat_anthropic(
            model=model, system=system, user=user,
            max_tokens=max_tokens, schema=schema,
        )
    if provider == "gemini":
        return _chat_gemini(
            model=model, system=system, user=user,
            max_tokens=max_tokens, schema=schema,
        )
    if provider == "openrouter":
        return _chat_openrouter(
            model=model, system=system, user=user,
            max_tokens=max_tokens, schema=schema,
        )
    raise ModelError(f"unknown provider: {provider!r}")


def chat_with_fallback(
    *,
    primary: Tuple[str, str],
    fallback: Tuple[str, str],
    system: str,
    user: str,
    max_tokens: int = 8000,
    schema: Optional[dict] = None,
    on_fallback: Optional[Callable[[str, BaseException], None]] = None,
    validate: Optional[Callable[[str], Any]] = None,
) -> Tuple[Any, str]:
    """Try the primary provider; on :class:`RateLimited`, :class:`ModelError`,
    or response-validation failure, fall back to the secondary. Return
    ``(reply_or_validated_value, provider_used)``.

    ``on_fallback(provider_name, exc)`` fires once, right before the secondary
    call, so callers can log which path fired and why. It's optional — a
    silent fallback still works.

    ``validate(text)`` may parse or otherwise validate the provider response.
    It runs inside the fallback boundary so malformed structured output from a
    nominally successful provider is treated as a provider failure, not as a
    worker crash after fallback has already returned.
    """
    def accepted(text: str, provider: str) -> Any:
        if validate is None:
            return text
        try:
            return validate(text)
        except Exception as exc:  # noqa: BLE001
            raise ModelError(f"{provider}: response validation failed: {exc}") from exc

    prim_provider, prim_model = primary
    try:
        text = chat(
            provider=prim_provider, model=prim_model,
            system=system, user=user,
            max_tokens=max_tokens, schema=schema,
        )
        return accepted(text, prim_provider), prim_provider
    except (RateLimited, ModelError) as exc:
        if on_fallback is not None:
            try:
                on_fallback(prim_provider, exc)
            except Exception:  # noqa: BLE001
                # A broken logging hook must not eat the fallback.
                pass
        fb_provider, fb_model = fallback
        text = chat(
            provider=fb_provider, model=fb_model,
            system=system, user=user,
            max_tokens=max_tokens, schema=schema,
        )
        return accepted(text, fb_provider), fb_provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env(name: str, provider: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise ModelError(
            f"{provider}: missing required env var {name}. "
            f"Set it before calling chat(provider={provider!r})."
        )
    return val


def _schema_hint(schema: dict) -> str:
    """Prompt-engineered structured-output nudge for providers with no native
    JSON-schema support (currently Anthropic)."""
    return (
        "\n\nReply with valid JSON matching this schema — no prose, no code "
        "fences, JSON only:\n" + json.dumps(schema, indent=2)
    )


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def _chat_anthropic(
    *, model: str, system: str, user: str,
    max_tokens: int, schema: Optional[dict],
) -> str:
    _require_env("ANTHROPIC_API_KEY", "anthropic")
    try:
        import anthropic  # lazy
    except ImportError as exc:  # pragma: no cover — install guidance
        raise ModelError(
            "anthropic: SDK not installed. `pip install anthropic`."
        ) from exc

    sys_prompt = system + (_schema_hint(schema) if schema else "")

    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=sys_prompt,
            messages=[{"role": "user", "content": user}],
            stream=False,
        )
    except Exception as exc:  # noqa: BLE001
        # anthropic.RateLimitError is a subclass of APIStatusError with
        # status_code=429. Detect by class name so we don't have to import
        # the exception hierarchy at module scope (would defeat lazy import).
        if _is_rate_limit(exc):
            raise RateLimited(f"anthropic: {exc}") from exc
        raise ModelError(f"anthropic: {exc}") from exc

    # content is a list of content blocks; take the first text block.
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            return text
    raise ModelError("anthropic: no text block in response")


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def _chat_gemini(
    *, model: str, system: str, user: str,
    max_tokens: int, schema: Optional[dict],
) -> str:
    api_key = _require_env("GEMINI_API_KEY", "gemini")
    try:
        import google.generativeai as genai  # lazy
    except ImportError as exc:  # pragma: no cover
        raise ModelError(
            "gemini: SDK not installed. `pip install google-generativeai`."
        ) from exc

    gen_config: dict[str, Any] = {"max_output_tokens": max_tokens}
    if schema is not None:
        # Native structured output.
        gen_config["response_mime_type"] = "application/json"
        gen_config["response_schema"] = schema

    try:
        genai.configure(api_key=api_key)
        # `system_instruction` puts the review rules on Gemini's trusted system
        # channel. Sending them as an extra content part (the legacy shape)
        # would let an untrusted PR diff in `user` compete with or override
        # the JSON-only / severity-taxonomy rules the Reviewer relies on.
        gm = genai.GenerativeModel(model, system_instruction=system)
        resp = gm.generate_content(
            user,
            generation_config=gen_config,
        )
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limit(exc):
            raise RateLimited(f"gemini: {exc}") from exc
        raise ModelError(f"gemini: {exc}") from exc

    # `resp.text` is a *property* that raises `ValueError` when the candidate
    # has no text part (finish_reason SAFETY / RECITATION / MAX_TOKENS). Read
    # it outside a guard and the exception escapes the ModelError contract —
    # `chat_with_fallback` won't cut over. Prefer walking candidates and map
    # anything unexpected onto ModelError.
    try:
        text = _gemini_extract_text(resp)
    except Exception as exc:  # noqa: BLE001
        raise ModelError(f"gemini: malformed response: {exc}") from exc
    if not text:
        raise ModelError("gemini: empty response text")
    return text


def _gemini_extract_text(resp: Any) -> str:
    """Pull the reply text out of a Gemini response object.

    Walks ``resp.candidates[0].content.parts`` first so a safety-filtered or
    MAX_TOKENS-truncated reply doesn't trip the ``resp.text`` quick-accessor's
    ``ValueError``. Falls back to ``resp.text`` when no candidates/parts are
    exposed (older SDK shapes, minimal test fixtures) — that read is inside
    the caller's try/except and any raise there still becomes ``ModelError``.
    """
    candidates = getattr(resp, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []
        pieces = [getattr(p, "text", "") for p in parts]
        joined = "".join(p for p in pieces if p)
        if joined:
            return joined
    # No usable candidate parts — try the quick accessor. May raise; caller maps it.
    return getattr(resp, "text", "") or ""


# ---------------------------------------------------------------------------
# OpenRouter (OpenAI-compatible)
# ---------------------------------------------------------------------------


_OPENROUTER_REFERER = "https://github.com/swamikit/swami"
_OPENROUTER_TITLE = "swami-review"


def _chat_openrouter(
    *, model: str, system: str, user: str,
    max_tokens: int, schema: Optional[dict],
) -> str:
    api_key = _require_env("OPENROUTER_API_KEY", "openrouter")
    try:
        import openai  # lazy — the openai SDK talks to any OpenAI-compatible endpoint
    except ImportError as exc:  # pragma: no cover
        raise ModelError(
            "openrouter: SDK not installed. `pip install openai`."
        ) from exc

    default_headers = {
        # OpenRouter uses these two headers to attribute traffic in its
        # dashboard and unlock free-tier routing on some models.
        "HTTP-Referer": _OPENROUTER_REFERER,
        "X-Title": _OPENROUTER_TITLE,
    }

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if schema is not None:
        # OpenRouter forwards `response_format` to backends that support it
        # (OpenAI, some Anthropic proxies, Fireworks, etc.). Models that don't
        # will ignore it or 400; the caller can fall back if that happens.
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_reply",
                "schema": schema,
                "strict": True,
            },
        }

    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=default_headers,
        )
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limit(exc):
            raise RateLimited(f"openrouter: {exc}") from exc
        raise ModelError(f"openrouter: {exc}") from exc

    try:
        text = resp.choices[0].message.content
    except (AttributeError, IndexError) as exc:
        raise ModelError(f"openrouter: malformed response: {exc}") from exc
    if not text:
        raise ModelError("openrouter: empty response text")
    return text


# ---------------------------------------------------------------------------
# Rate-limit detection
# ---------------------------------------------------------------------------


def _is_rate_limit(exc: BaseException) -> bool:
    """Best-effort 429 detector that works across SDKs without importing them.

    Each vendor has its own class hierarchy (``anthropic.RateLimitError``,
    ``openai.RateLimitError``, ``google.api_core.exceptions.ResourceExhausted``,
    ``google.generativeai.types.generation_types.StopCandidateException``, …).
    Instead of importing all of them at module scope — which would defeat the
    lazy-import contract — we sniff for the ubiquitous signals: a
    ``status_code`` / ``code`` / ``.response.status_code`` of 429, or a class
    name that ends in ``RateLimitError`` / ``ResourceExhausted``.
    """
    name = type(exc).__name__
    if name.endswith("RateLimitError") or name == "ResourceExhausted":
        return True
    for attr in ("status_code", "code", "http_status"):
        val = getattr(exc, attr, None)
        if val == 429 or val == "429":
            return True
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True
    return False
