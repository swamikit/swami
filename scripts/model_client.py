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
) -> Tuple[str, str]:
    """Try the primary provider; on :class:`RateLimited` or :class:`ModelError`
    fall back to the secondary. Return ``(reply, provider_used)``.

    ``on_fallback(provider_name, exc)`` fires once, right before the secondary
    call, so callers can log which path fired and why. It's optional — a
    silent fallback still works.
    """
    prim_provider, prim_model = primary
    try:
        text = chat(
            provider=prim_provider, model=prim_model,
            system=system, user=user,
            max_tokens=max_tokens, schema=schema,
        )
        return text, prim_provider
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
        return text, fb_provider


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
        gm = genai.GenerativeModel(model)
        resp = gm.generate_content(
            [system, user],
            generation_config=gen_config,
        )
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limit(exc):
            raise RateLimited(f"gemini: {exc}") from exc
        raise ModelError(f"gemini: {exc}") from exc

    text = getattr(resp, "text", None)
    if not text:
        raise ModelError("gemini: empty response text")
    return text


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
