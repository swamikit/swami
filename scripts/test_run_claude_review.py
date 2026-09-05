#!/usr/bin/env python3
"""Stdlib-only tests for scripts/run-claude-review.py.

Runs without pytest / anthropic installed by stubbing `anthropic` before
importing the module (the module top-level does `import anthropic`).
Exercise the two `_cap_diff` branches so a future refactor that drops
the truncation signal fails loudly.
"""
from __future__ import annotations
import importlib.util
import sys
import types
from pathlib import Path


def _load_module():
    # Stub `anthropic` — the module imports it at top level but we don't need
    # a real client for these tests. A bare ModuleType is enough for the
    # import statement; the tests here never touch it.
    sys.modules.setdefault("anthropic", types.ModuleType("anthropic"))
    script = Path(__file__).resolve().parent / "run-claude-review.py"
    spec = importlib.util.spec_from_file_location("run_claude_review", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cap_diff_small_returns_zero_omitted(mod) -> None:
    small = "diff --git a/x b/x\n+small\n"
    kept, omitted = mod._cap_diff(small, limit=1000)
    assert omitted == 0, f"expected 0 omitted, got {omitted}"
    assert kept == small, "small diff should pass through unchanged"


def test_cap_diff_big_returns_positive_omitted(mod) -> None:
    # Force truncation with a tiny limit so we don't have to allocate MBs.
    big = "x" * 500
    kept, omitted = mod._cap_diff(big, limit=100)
    assert omitted > 0, f"expected positive omitted, got {omitted}"
    assert omitted == 400, f"expected 400 omitted (500-100), got {omitted}"
    assert "[diff truncated" in kept, "truncated diff must carry the marker"
    # Sanity: kept content includes the first `limit` bytes.
    assert kept.startswith("x" * 100), "prefix should be the retained bytes"


def main() -> int:
    mod = _load_module()
    tests = [
        test_cap_diff_small_returns_zero_omitted,
        test_cap_diff_big_returns_positive_omitted,
    ]
    failed = 0
    for t in tests:
        try:
            t(mod)
            print(f"PASS {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
