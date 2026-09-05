#!/usr/bin/env python3
"""Focused contract tests for the fast-review worker."""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_module():
    # gh_app_auth imports PyJWT at module load; this test never exercises auth.
    sys.modules.setdefault("jwt", types.ModuleType("jwt"))
    script = Path(__file__).resolve().parent / "run-fast-review.py"
    spec = importlib.util.spec_from_file_location("run_fast_review", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


class ModelClientContractTests(unittest.TestCase):
    def test_call_model_unpacks_text_provider_tuple(self) -> None:
        reply = '{"summary":"ok","findings":[],"approve":true}'
        with mock.patch.object(
            mod,
            "chat_with_fallback",
            return_value=(reply, "anthropic"),
        ) as call:
            review, provider = mod.call_model("system", "diff")

        self.assertEqual(provider, "anthropic")
        self.assertEqual(review["summary"], "ok")
        self.assertTrue(review["approve"])
        call.assert_called_once_with(
            primary=mod.PRIMARY,
            fallback=mod.FALLBACK,
            system="system",
            user="## PR diff\n\n```diff\ndiff\n```",
            max_tokens=mod.MAX_TOKENS,
        )


if __name__ == "__main__":
    unittest.main()
