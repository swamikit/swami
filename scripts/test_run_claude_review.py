#!/usr/bin/env python3
"""Stdlib-only tests for scripts/run-claude-review.py.

Runs without pytest / anthropic installed by stubbing `anthropic` before
importing the module (the module top-level does `import anthropic`).

Covers:
- `_cap_diff` truncation-signal preservation.
- `compute_event` event-mapping (APPROVE / REQUEST_CHANGES / COMMENT).
- `format_review` payload shape + truncation forcing REQUEST_CHANGES.
- `main`'s dismiss-prior-then-post-new subprocess sequence.

Run: python3 -m unittest scripts.test_run_claude_review -v
"""
from __future__ import annotations
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_module():
    """Import scripts/run-claude-review.py under the name `run_claude_review`.

    Stubs `anthropic` because the module imports it at top level — no need
    for a real client for any of these tests.
    """
    sys.modules.setdefault("anthropic", types.ModuleType("anthropic"))
    script = Path(__file__).resolve().parent / "run-claude-review.py"
    spec = importlib.util.spec_from_file_location("run_claude_review", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


class CapDiffTests(unittest.TestCase):
    """Truncation signal must survive round-trips through `_cap_diff`."""

    def test_small_returns_zero_omitted(self) -> None:
        small = "diff --git a/x b/x\n+small\n"
        kept, omitted = mod._cap_diff(small, limit=1000)
        self.assertEqual(omitted, 0)
        self.assertEqual(kept, small)

    def test_big_returns_positive_omitted(self) -> None:
        big = "x" * 500
        kept, omitted = mod._cap_diff(big, limit=100)
        self.assertEqual(omitted, 400)
        self.assertIn("[diff truncated", kept)
        self.assertTrue(kept.startswith("x" * 100))


class ComputeEventTests(unittest.TestCase):
    """Event-mapping is the merge-gate contract — cover every arm."""

    def test_approve_true_and_no_p1_maps_to_APPROVE(self) -> None:
        r = {"approve": True, "findings": []}
        self.assertEqual(mod.compute_event(r), "APPROVE")

    def test_approve_true_but_p1_present_maps_to_REQUEST_CHANGES(self) -> None:
        # A model that returned approve=true while flagging a P1 should NOT
        # ship as APPROVE — the P1 wins. This is a merge-gate correctness case.
        r = {
            "approve": True,
            "findings": [{"severity": "P1", "file": "a", "line": 1, "title": "x"}],
        }
        self.assertEqual(mod.compute_event(r), "REQUEST_CHANGES")

    def test_approve_false_no_p1_maps_to_REQUEST_CHANGES(self) -> None:
        # Explicit reviewer NO. Even without P1s, respect the verdict.
        r = {"approve": False, "findings": []}
        self.assertEqual(mod.compute_event(r), "REQUEST_CHANGES")

    def test_approve_false_with_p1_maps_to_REQUEST_CHANGES(self) -> None:
        r = {
            "approve": False,
            "findings": [{"severity": "P1", "file": "a", "line": 1, "title": "x"}],
        }
        self.assertEqual(mod.compute_event(r), "REQUEST_CHANGES")

    def test_approve_missing_no_p1_maps_to_COMMENT(self) -> None:
        # Neutral: reviewer took no stance and no P1s exist. Post as COMMENT
        # so branch protection sees neither approving nor blocking.
        r = {"findings": [{"severity": "P2", "file": "a", "line": 1, "title": "x"}]}
        self.assertEqual(mod.compute_event(r), "COMMENT")

    def test_approve_missing_with_p1_maps_to_REQUEST_CHANGES(self) -> None:
        # Neutral + P1 → block. P1 wins the tie.
        r = {
            "findings": [{"severity": "P1", "file": "a", "line": 1, "title": "x"}]
        }
        self.assertEqual(mod.compute_event(r), "REQUEST_CHANGES")

    def test_legacy_blocking_severity_counts_as_P1(self) -> None:
        # Legacy `blocking` word from older stored responses folds into P1
        # inside `_normalize_findings`, so it MUST also drive the event.
        r = {
            "approve": True,
            "findings": [{"severity": "blocking", "file": "a", "line": 1, "title": "x"}],
        }
        self.assertEqual(mod.compute_event(r), "REQUEST_CHANGES")


class FormatReviewShapeTests(unittest.TestCase):
    """Payload shape is what the Reviews API sees — pin it down."""

    def test_payload_has_body_event_and_comments(self) -> None:
        r = {"approve": True, "summary": "s", "findings": []}
        p = mod.format_review(r, head_sha="abc123")
        self.assertEqual(set(p.keys()), {"body", "event", "comments"})
        self.assertEqual(p["event"], "APPROVE")
        self.assertIsInstance(p["comments"], list)

    def test_body_carries_marker_and_bucket_headers(self) -> None:
        r = {
            "approve": False,
            "summary": "s",
            "findings": [
                {"severity": "P1", "file": "a.py", "line": 3, "title": "boom"},
                {"severity": "P2", "file": "b.py", "line": 4, "title": "meh"},
            ],
        }
        body = mod.format_review(r, head_sha="abc123")["body"]
        # Marker must be first line so merge-gate greps still match.
        self.assertTrue(body.startswith(mod.MARKER))
        # Count headers for all three severities are always emitted so
        # downstream regex greps work regardless of which severities the
        # reviewer actually raised.
        self.assertIn("### P1 (1)", body)
        self.assertIn("### P2 (1)", body)
        self.assertIn("### P3 (0)", body)
        # "inline in Files changed" pointer so a human reader knows where to
        # look for the actual finding text.
        self.assertIn("Findings inline in Files changed.", body)

    def test_comment_entry_shape(self) -> None:
        r = {
            "approve": False,
            "findings": [
                {
                    "severity": "P1",
                    "file": "scripts/x.py",
                    "line": 42,
                    "title": "wrong constant",
                    "reasoning": "should be 100 not 10",
                    "suggestion": "use MAX_FRAMES",
                }
            ],
        }
        comments = mod.format_review(r, head_sha="abc123")["comments"]
        self.assertEqual(len(comments), 1)
        c = comments[0]
        # Reviews API line-anchored comment shape.
        self.assertEqual(c["path"], "scripts/x.py")
        self.assertEqual(c["line"], 42)
        self.assertEqual(c["side"], "RIGHT")
        self.assertIn("[P1] wrong constant", c["body"])
        self.assertIn("should be 100 not 10", c["body"])
        self.assertIn("_suggestion:_ use MAX_FRAMES", c["body"])
        # Per-finding marker so the audit script can grep findings.
        self.assertIn(mod.FINDING_MARKER, c["body"])

    def test_finding_without_line_is_dropped_from_inline(self) -> None:
        # Un-anchorable findings must NOT ship inline — the API rejects the
        # whole review if any comment lacks a valid diff anchor. They still
        # count in the body's severity buckets so nothing is silently lost.
        r = {
            "approve": False,
            "findings": [
                {"severity": "P2", "file": "a.py", "line": None, "title": "no line"},
                {"severity": "P2", "file": "a.py", "line": 5, "title": "anchored"},
            ],
        }
        p = mod.format_review(r, head_sha="abc123")
        self.assertEqual(len(p["comments"]), 1)
        self.assertEqual(p["comments"][0]["line"], 5)
        # Both still counted in the body's P2 bucket.
        self.assertIn("### P2 (2)", p["body"])


class FormatReviewTruncationTests(unittest.TestCase):
    """Truncated diffs must ship as REQUEST_CHANGES via the synthetic-P1 hook.

    The synthetic-P1 injection lives in `main()`, not `format_review` — this
    verifies the piece `format_review` owns: a truncation banner in the body
    that a human reader sees before scrolling. Even without the injection,
    an APPROVE payload with truncated_bytes > 0 is a bug; the caller (main)
    is responsible for calling with a synthetic P1 first.
    """

    def test_truncation_banner_appears_in_body(self) -> None:
        r = {"approve": True, "summary": "s", "findings": []}
        body = mod.format_review(r, head_sha="abc123", truncated_bytes=500)["body"]
        self.assertIn("diff truncated at", body)
        self.assertIn("500 bytes omitted", body)

    def test_synthetic_p1_forces_REQUEST_CHANGES(self) -> None:
        # This is exactly the shape `main()` builds when a truncated diff
        # arrives with approve=true: inject a synthetic P1 at .github/reviewer,
        # flip approve to false. That combination must never emit APPROVE.
        review = {
            "approve": False,
            "findings": [
                {
                    "severity": "P1",
                    "file": ".github/reviewer",
                    "line": 1,
                    "title": "Diff truncated — cannot approve",
                }
            ],
        }
        p = mod.format_review(review, head_sha="abc123", truncated_bytes=500)
        self.assertEqual(p["event"], "REQUEST_CHANGES")
        # And the synthetic finding does anchor inline (it has a line).
        self.assertEqual(len(p["comments"]), 1)
        self.assertEqual(p["comments"][0]["path"], ".github/reviewer")


class DismissThenPostSequenceTests(unittest.TestCase):
    """Integration-style: mock subprocess.run and assert the call sequence.

    Contract we're locking down:
      1. Prior bot-authored reviews are looked up first (`gh api ... /reviews`).
      2. Each prior review is dismissed via PUT /reviews/{id}/dismissals.
      3. The new review is POSTed to /reviews with the full payload.
    Order matters — see main()'s comment on the dismiss-first rationale.
    """

    def _run_returns(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        r = mock.MagicMock()
        r.stdout = stdout
        r.stderr = stderr
        r.returncode = returncode
        return r

    def test_main_dismisses_prior_then_posts_new(self) -> None:
        # Mock everything main() shells out to. Order of side_effect matches
        # the order of subprocess.run / sh() calls in main().
        env_stub = {"GH_TOKEN": "stub", "GITHUB_REPOSITORY": "o/r", "PR_NUMBER": "5"}

        # Fake review the model would produce (no truncation, one P2 anchored).
        fake_review = {
            "approve": True,
            "summary": "looks good",
            "findings": [
                {
                    "severity": "P2",
                    "file": "scripts/x.py",
                    "line": 10,
                    "title": "nit",
                    "reasoning": "small polish",
                    "suggestion": "",
                }
            ],
        }

        # Track the order in which subprocess-shaped calls happen. We watch
        # BOTH `subprocess.run` (used by sh() and by dismiss_review /
        # post_review) so we can assert the whole sequence in one list.
        calls: list[tuple[str, list[str]]] = []

        def _fake_subprocess_run(cmd, **kw):
            # Record the (tag, cmd) so we can pattern-match. `input` (JSON
            # payload) is captured off `kw` for the POST assertion.
            input_data = kw.get("input", "")
            calls.append(("run", list(cmd), input_data))
            # Dispatch based on URL shape.
            joined = " ".join(cmd)
            if "/pr diff" in joined or ("gh" in cmd and "pr" in cmd and "diff" in cmd):
                return self._run_returns(stdout="diff --git a/x b/x\n+1\n")
            if "/reviews/" in joined and "dismissals" in joined:
                return self._run_returns()  # dismiss OK
            if joined.endswith("/reviews") or "/pulls/5/reviews" in joined and "-X" in cmd and "POST" in cmd:
                return self._run_returns(stdout='{"id": 999}')
            if "/pulls/5/reviews" in joined and "--jq" in cmd:
                # find_prior_reviews — return one review id.
                return self._run_returns(stdout="12345\n")
            # Default: empty OK.
            return self._run_returns()

        with mock.patch.dict("os.environ", env_stub, clear=True), \
             mock.patch.object(mod, "get_installation_token", return_value="stub"), \
             mock.patch.object(mod, "call_claude", return_value=fake_review), \
             mock.patch.object(mod, "load_context", return_value=""), \
             mock.patch("pathlib.Path.exists", return_value=False), \
             mock.patch("subprocess.run", side_effect=_fake_subprocess_run):
            rc = mod.main()

        self.assertEqual(rc, 0)

        # Extract just the (cmd) sequence to assert order/content.
        cmd_seq = [c[1] for c in calls]

        # 1. `gh pr diff` should fire once to fetch the diff.
        self.assertTrue(
            any(c[:3] == ["gh", "pr", "diff"] for c in cmd_seq),
            f"expected `gh pr diff` in {cmd_seq}",
        )

        # 2. find_prior_reviews should fire before any dismissal.
        list_idxs = [
            i for i, c in enumerate(cmd_seq)
            if "gh" in c and "api" in c and any("/pulls/5/reviews" in x for x in c) and "--jq" in c
        ]
        dismiss_idxs = [
            i for i, c in enumerate(cmd_seq)
            if any("/reviews/" in x and "dismissals" in x for x in c)
        ]
        post_idxs = [
            i for i, c in enumerate(cmd_seq)
            if "gh" in c and "api" in c
            and any(x.endswith("/pulls/5/reviews") for x in c)
            and "-X" in c and "POST" in c
        ]
        self.assertTrue(list_idxs, "expected a list-prior-reviews call")
        self.assertTrue(dismiss_idxs, "expected at least one dismissal call")
        self.assertTrue(post_idxs, "expected a POST /reviews call")
        # Ordering contract: list → dismiss → post.
        self.assertLess(list_idxs[0], dismiss_idxs[0])
        self.assertLess(dismiss_idxs[-1], post_idxs[0])

        # 3. The POST payload must be well-formed JSON with the three fields.
        post_input = calls[post_idxs[0]][2]
        payload = json.loads(post_input)
        self.assertEqual(set(payload.keys()), {"body", "event", "comments"})
        # Given the fake_review (approve=True + only P2), event is APPROVE.
        self.assertEqual(payload["event"], "APPROVE")
        # One inline comment anchored to scripts/x.py:10.
        self.assertEqual(len(payload["comments"]), 1)
        self.assertEqual(payload["comments"][0]["path"], "scripts/x.py")
        self.assertEqual(payload["comments"][0]["line"], 10)


if __name__ == "__main__":
    unittest.main()
