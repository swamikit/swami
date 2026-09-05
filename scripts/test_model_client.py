"""Unit tests for scripts/model_client.py.

Stdlib-only. Every provider SDK is mocked via ``sys.modules`` / patched
attributes so no network calls happen and no vendor packages need to be
installed on the runner.

Run:  python3 -m unittest scripts/test_model_client.py -v
"""
from __future__ import annotations

import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

# Make `scripts/` importable when this test is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import model_client as mc  # noqa: E402


# ---------------------------------------------------------------------------
# Fake exception classes each provider "raises". Their names are what
# _is_rate_limit sniffs on, so keep the suffixes accurate.
# ---------------------------------------------------------------------------


class FakeAnthropicRateLimitError(Exception):
    def __init__(self, msg: str = "rate limited") -> None:
        super().__init__(msg)
        self.status_code = 429


class FakeOpenAIRateLimitError(Exception):
    def __init__(self, msg: str = "rate limited") -> None:
        super().__init__(msg)
        self.status_code = 429


class ResourceExhausted(Exception):
    """Mirrors google.api_core.exceptions.ResourceExhausted by class name."""


# ---------------------------------------------------------------------------
# Helpers for installing fake SDK modules into sys.modules so
# `import anthropic` / `import openai` / `import google.generativeai`
# inside model_client resolve to our mocks.
# ---------------------------------------------------------------------------


def _install_fake_anthropic(client_factory):
    """`client_factory()` returns the fake Anthropic client instance."""
    fake = types.ModuleType("anthropic")
    fake.Anthropic = client_factory  # type: ignore[attr-defined]
    fake.RateLimitError = FakeAnthropicRateLimitError  # type: ignore[attr-defined]
    sys.modules["anthropic"] = fake
    return fake


def _install_fake_openai(client_factory):
    fake = types.ModuleType("openai")
    fake.OpenAI = client_factory  # type: ignore[attr-defined]
    fake.RateLimitError = FakeOpenAIRateLimitError  # type: ignore[attr-defined]
    sys.modules["openai"] = fake
    return fake


def _install_fake_gemini(model_factory):
    """`model_factory(model_name)` returns the fake GenerativeModel."""
    pkg = types.ModuleType("google")
    sub = types.ModuleType("google.generativeai")

    def _configure(**_kwargs):  # noqa: ANN003
        return None

    sub.configure = _configure  # type: ignore[attr-defined]
    sub.GenerativeModel = model_factory  # type: ignore[attr-defined]
    pkg.generativeai = sub  # type: ignore[attr-defined]
    sys.modules["google"] = pkg
    sys.modules["google.generativeai"] = sub
    return sub


def _wipe_fake_sdks():
    for name in ("anthropic", "openai", "google", "google.generativeai"):
        sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Fixtures — text-block objects that quack like each SDK's response shape.
# ---------------------------------------------------------------------------


class _AnthContentBlock:
    def __init__(self, text: str) -> None:
        self.text = text
        self.type = "text"


class _AnthResponse:
    def __init__(self, text: str) -> None:
        self.content = [_AnthContentBlock(text)]


class _OpenAIMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _OpenAIChoice:
    def __init__(self, content: str) -> None:
        self.message = _OpenAIMessage(content)


class _OpenAIResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_OpenAIChoice(content)]


class _GeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _GeminiPart:
    def __init__(self, text: str) -> None:
        self.text = text


class _GeminiContent:
    def __init__(self, parts: list) -> None:
        self.parts = parts


class _GeminiCandidate:
    def __init__(self, parts: list) -> None:
        self.content = _GeminiContent(parts)


class _GeminiResponseWithCandidates:
    """Response whose text lives on ``candidates[0].content.parts`` (the shape
    the real SDK returns). ``.text`` deliberately raises so we assert the
    extractor walks candidates instead of tripping the quick-accessor."""
    def __init__(self, text: str) -> None:
        self.candidates = [_GeminiCandidate([_GeminiPart(text)])]

    @property
    def text(self) -> str:  # pragma: no cover — should never be reached
        raise ValueError(
            "text quick-accessor invoked; extractor should walk parts"
        )


class _GeminiResponseTextRaises:
    """Response with no text part — mirrors SAFETY / RECITATION / MAX_TOKENS
    truncation, where ``.text`` is a property that raises ``ValueError``."""
    def __init__(self) -> None:
        self.candidates = []

    @property
    def text(self) -> str:
        raise ValueError(
            "The `response.text` quick accessor requires the response to "
            "contain a valid `Part`"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class RateLimitDetectionTests(unittest.TestCase):
    def test_status_code_429(self) -> None:
        exc = Exception("nope")
        exc.status_code = 429  # type: ignore[attr-defined]
        self.assertTrue(mc._is_rate_limit(exc))

    def test_class_name_suffix(self) -> None:
        self.assertTrue(mc._is_rate_limit(FakeOpenAIRateLimitError()))
        self.assertTrue(mc._is_rate_limit(ResourceExhausted("quota gone")))

    def test_non_rate_limit(self) -> None:
        self.assertFalse(mc._is_rate_limit(ValueError("something else")))

    def test_response_status_code(self) -> None:
        class Resp:
            status_code = 429
        class Err(Exception):
            def __init__(self):
                super().__init__("x")
                self.response = Resp()
        self.assertTrue(mc._is_rate_limit(Err()))


class EnvVarTests(unittest.TestCase):
    def test_missing_env_raises_modelerror(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(mc.ModelError):
                mc._require_env("NOPE_KEY", "anthropic")


class ChatDispatchTests(unittest.TestCase):
    def test_unknown_provider(self) -> None:
        with self.assertRaises(mc.ModelError):
            mc.chat(provider="mystery", model="x", system="s", user="u")

    def test_anthropic_success(self) -> None:
        _wipe_fake_sdks()
        try:
            call_args: dict = {}

            class FakeClient:
                class messages:
                    @staticmethod
                    def create(**kwargs):
                        call_args.update(kwargs)
                        return _AnthResponse("hello from anthropic")

            _install_fake_anthropic(lambda: FakeClient())
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
                out = mc.chat(
                    provider="anthropic", model="claude-opus-5",
                    system="be terse", user="hi",
                )
            self.assertEqual(out, "hello from anthropic")
            self.assertEqual(call_args["model"], "claude-opus-5")
            self.assertEqual(call_args["messages"], [{"role": "user", "content": "hi"}])
            self.assertFalse(call_args["stream"])
        finally:
            _wipe_fake_sdks()

    def test_anthropic_rate_limit_raises_ratelimited(self) -> None:
        _wipe_fake_sdks()
        try:
            class FakeClient:
                class messages:
                    @staticmethod
                    def create(**_kwargs):
                        raise FakeAnthropicRateLimitError("429 friend")

            _install_fake_anthropic(lambda: FakeClient())
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
                with self.assertRaises(mc.RateLimited):
                    mc.chat(
                        provider="anthropic", model="claude-opus-5",
                        system="s", user="u",
                    )
        finally:
            _wipe_fake_sdks()

    def test_anthropic_schema_becomes_prompt_hint(self) -> None:
        _wipe_fake_sdks()
        try:
            captured: dict = {}

            class FakeClient:
                class messages:
                    @staticmethod
                    def create(**kwargs):
                        captured.update(kwargs)
                        return _AnthResponse("{}")

            _install_fake_anthropic(lambda: FakeClient())
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
                mc.chat(
                    provider="anthropic", model="claude-opus-5",
                    system="original system",
                    user="u", schema={"type": "object"},
                )
            self.assertIn("Reply with valid JSON", captured["system"])
            self.assertIn("original system", captured["system"])
        finally:
            _wipe_fake_sdks()

    def test_gemini_success_and_schema(self) -> None:
        _wipe_fake_sdks()
        try:
            captured: dict = {}

            class FakeModel:
                def __init__(self, name, system_instruction=None):
                    captured["model"] = name
                    captured["system_instruction"] = system_instruction

                def generate_content(self, contents, generation_config=None):
                    captured["contents"] = contents
                    captured["gen_config"] = generation_config
                    return _GeminiResponse('{"ok": true}')

            _install_fake_gemini(FakeModel)
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "gk-test"}):
                out = mc.chat(
                    provider="gemini", model="gemini-2.0-flash-exp",
                    system="sys", user="usr", schema={"type": "object"},
                )
            self.assertEqual(out, '{"ok": true}')
            self.assertEqual(captured["model"], "gemini-2.0-flash-exp")
            # System prompt travels on the trusted `system_instruction` channel,
            # never as an extra content part alongside untrusted user input.
            self.assertEqual(captured["system_instruction"], "sys")
            self.assertEqual(captured["contents"], "usr")
            self.assertEqual(
                captured["gen_config"]["response_mime_type"],
                "application/json",
            )
            self.assertEqual(
                captured["gen_config"]["response_schema"],
                {"type": "object"},
            )
        finally:
            _wipe_fake_sdks()

    def test_gemini_prefers_candidates_over_text_accessor(self) -> None:
        """When candidates carry parts, extractor must walk them and never
        invoke the raising `.text` quick-accessor."""
        _wipe_fake_sdks()
        try:
            class FakeModel:
                def __init__(self, _name, system_instruction=None):
                    pass

                def generate_content(self, _contents, generation_config=None):
                    return _GeminiResponseWithCandidates("from parts")

            _install_fake_gemini(FakeModel)
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "gk-test"}):
                out = mc.chat(
                    provider="gemini", model="gemini-2.0-flash-exp",
                    system="s", user="u",
                )
            self.assertEqual(out, "from parts")
        finally:
            _wipe_fake_sdks()

    def test_gemini_text_property_valueerror_maps_to_modelerror(self) -> None:
        """`resp.text` on a safety-filtered / MAX_TOKENS-truncated reply is a
        property that raises `ValueError`. That must be mapped onto
        `ModelError` so `chat_with_fallback` cuts over instead of crashing."""
        _wipe_fake_sdks()
        try:
            class FakeModel:
                def __init__(self, _name, system_instruction=None):
                    pass

                def generate_content(self, _contents, generation_config=None):
                    return _GeminiResponseTextRaises()

            _install_fake_gemini(FakeModel)
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "gk-test"}):
                with self.assertRaises(mc.ModelError):
                    mc.chat(
                        provider="gemini", model="gemini-2.0-flash-exp",
                        system="s", user="u",
                    )
        finally:
            _wipe_fake_sdks()

    def test_gemini_rate_limit(self) -> None:
        _wipe_fake_sdks()
        try:
            class FakeModel:
                def __init__(self, _name, system_instruction=None):
                    pass

                def generate_content(self, *_a, **_k):
                    raise ResourceExhausted("quota exceeded")

            _install_fake_gemini(FakeModel)
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "gk-test"}):
                with self.assertRaises(mc.RateLimited):
                    mc.chat(
                        provider="gemini", model="gemini-2.0-flash-exp",
                        system="s", user="u",
                    )
        finally:
            _wipe_fake_sdks()

    def test_openrouter_success_and_headers(self) -> None:
        _wipe_fake_sdks()
        try:
            init_args: dict = {}
            call_args: dict = {}

            class FakeCompletions:
                @staticmethod
                def create(**kwargs):
                    call_args.update(kwargs)
                    return _OpenAIResponse("hi from openrouter")

            class FakeChat:
                completions = FakeCompletions()

            class FakeClient:
                def __init__(self, **kwargs):
                    init_args.update(kwargs)
                    self.chat = FakeChat()

            _install_fake_openai(FakeClient)
            with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-test"}):
                out = mc.chat(
                    provider="openrouter",
                    model="anthropic/claude-3.5-sonnet",
                    system="s", user="u",
                    schema={"type": "object"},
                )
            self.assertEqual(out, "hi from openrouter")
            self.assertEqual(init_args["base_url"], "https://openrouter.ai/api/v1")
            self.assertEqual(init_args["api_key"], "or-test")
            self.assertEqual(
                init_args["default_headers"]["HTTP-Referer"],
                "https://github.com/swamikit/swami",
            )
            self.assertEqual(init_args["default_headers"]["X-Title"], "swami-review")
            self.assertEqual(call_args["response_format"]["type"], "json_schema")
        finally:
            _wipe_fake_sdks()


class FallbackTests(unittest.TestCase):
    def test_invalid_primary_response_triggers_fallback_validation(self) -> None:
        calls: list[str] = []

        def _chat(**kwargs):
            calls.append(kwargs["provider"])
            if kwargs["provider"] == "gemini":
                return '{"broken":'
            return '{"ok": true}'

        with mock.patch.object(mc, "chat", side_effect=_chat):
            value, used = mc.chat_with_fallback(
                primary=("gemini", "flash"),
                fallback=("anthropic", "opus"),
                system="s",
                user="u",
                validate=json.loads,
            )

        self.assertEqual(value, {"ok": True})
        self.assertEqual(used, "anthropic")
        self.assertEqual(calls, ["gemini", "anthropic"])

    def test_primary_rate_limited_triggers_fallback(self) -> None:
        """Primary raises RateLimited; secondary answers; caller sees which."""
        _wipe_fake_sdks()
        try:
            calls: list[str] = []

            # Fake Gemini as primary — always 429s.
            class FakeGeminiModel:
                def __init__(self, _name, system_instruction=None):
                    pass

                def generate_content(self, *_a, **_k):
                    calls.append("gemini")
                    raise ResourceExhausted("quota")

            _install_fake_gemini(FakeGeminiModel)

            # Fake Anthropic as fallback — always returns text.
            class FakeAnthClient:
                class messages:
                    @staticmethod
                    def create(**_kwargs):
                        calls.append("anthropic")
                        return _AnthResponse("fallback content")

            _install_fake_anthropic(lambda: FakeAnthClient())

            fallback_log: list = []

            def _log(provider, exc):
                fallback_log.append((provider, type(exc).__name__))

            with mock.patch.dict(os.environ, {
                "GEMINI_API_KEY": "gk-test",
                "ANTHROPIC_API_KEY": "sk-test",
            }):
                text, used = mc.chat_with_fallback(
                    primary=("gemini", "gemini-2.0-flash-exp"),
                    fallback=("anthropic", "claude-opus-5"),
                    system="s", user="u",
                    on_fallback=_log,
                )

            self.assertEqual(text, "fallback content")
            self.assertEqual(used, "anthropic")
            self.assertEqual(calls, ["gemini", "anthropic"])
            self.assertEqual(fallback_log, [("gemini", "RateLimited")])
        finally:
            _wipe_fake_sdks()

    def test_primary_generic_error_also_triggers_fallback(self) -> None:
        """Non-429 ModelError from primary still falls back (spec)."""
        _wipe_fake_sdks()
        try:
            calls: list[str] = []

            class FakeGeminiModel:
                def __init__(self, _name, system_instruction=None):
                    pass

                def generate_content(self, *_a, **_k):
                    calls.append("gemini")
                    raise RuntimeError("500 internal server error")

            _install_fake_gemini(FakeGeminiModel)

            class FakeAnthClient:
                class messages:
                    @staticmethod
                    def create(**_kwargs):
                        calls.append("anthropic")
                        return _AnthResponse("from-fallback")

            _install_fake_anthropic(lambda: FakeAnthClient())

            with mock.patch.dict(os.environ, {
                "GEMINI_API_KEY": "gk-test",
                "ANTHROPIC_API_KEY": "sk-test",
            }):
                text, used = mc.chat_with_fallback(
                    primary=("gemini", "gemini-1.5-flash"),
                    fallback=("anthropic", "claude-opus-5"),
                    system="s", user="u",
                )

            self.assertEqual(text, "from-fallback")
            self.assertEqual(used, "anthropic")
            self.assertEqual(calls, ["gemini", "anthropic"])
        finally:
            _wipe_fake_sdks()

    def test_primary_success_never_calls_fallback(self) -> None:
        _wipe_fake_sdks()
        try:
            calls: list[str] = []

            class FakeGeminiModel:
                def __init__(self, _name, system_instruction=None):
                    pass

                def generate_content(self, *_a, **_k):
                    calls.append("gemini")
                    return _GeminiResponse("primary happy")

            _install_fake_gemini(FakeGeminiModel)

            # Install an anthropic that would blow up if called — proof the
            # secondary was never touched.
            def _boom():
                calls.append("anthropic-init")
                raise AssertionError("fallback should not run")

            _install_fake_anthropic(_boom)

            with mock.patch.dict(os.environ, {
                "GEMINI_API_KEY": "gk-test",
                "ANTHROPIC_API_KEY": "sk-test",
            }):
                text, used = mc.chat_with_fallback(
                    primary=("gemini", "gemini-2.0-flash-exp"),
                    fallback=("anthropic", "claude-opus-5"),
                    system="s", user="u",
                )
            self.assertEqual(text, "primary happy")
            self.assertEqual(used, "gemini")
            self.assertEqual(calls, ["gemini"])
        finally:
            _wipe_fake_sdks()

    def test_on_fallback_hook_errors_do_not_break_fallback(self) -> None:
        _wipe_fake_sdks()
        try:
            class FakeGeminiModel:
                def __init__(self, _name, system_instruction=None):
                    pass

                def generate_content(self, *_a, **_k):
                    raise ResourceExhausted("quota")

            _install_fake_gemini(FakeGeminiModel)

            class FakeAnthClient:
                class messages:
                    @staticmethod
                    def create(**_kwargs):
                        return _AnthResponse("ok")

            _install_fake_anthropic(lambda: FakeAnthClient())

            def _bad_hook(_p, _e):
                raise RuntimeError("logger broke")

            with mock.patch.dict(os.environ, {
                "GEMINI_API_KEY": "gk-test",
                "ANTHROPIC_API_KEY": "sk-test",
            }):
                text, used = mc.chat_with_fallback(
                    primary=("gemini", "gemini-2.0-flash-exp"),
                    fallback=("anthropic", "claude-opus-5"),
                    system="s", user="u",
                    on_fallback=_bad_hook,
                )
            self.assertEqual(text, "ok")
            self.assertEqual(used, "anthropic")
        finally:
            _wipe_fake_sdks()


if __name__ == "__main__":
    unittest.main()
