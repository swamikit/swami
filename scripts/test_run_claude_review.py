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

from scripts import review_posting


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


class FailureMarkerContractTests(unittest.TestCase):
    def test_missing_credential_workflow_uses_python_owned_marker(self) -> None:
        workflow = (
            Path(__file__).resolve().parent.parent
            / ".github"
            / "workflows"
            / "review.yml"
        ).read_text()
        self.assertIn(mod.FAILURE_MARKER, workflow)


class SummaryFallbackFormatContractTests(unittest.TestCase):
    def test_deep_inline_comment_format_survives_summary_only_fallback(self) -> None:
        # Cover the remaining deep reviewer's original P1 contract and the P2
        # case previously exercised only by the deleted secondary-review test.
        for severity in ("P1", "P2"):
            with self.subTest(severity=severity):
                comments = mod.format_review_comments(
                    [{
                        "severity": severity,
                        "file": "x.py",
                        "line": 4,
                        "_side": "RIGHT",
                        "title": "deep formatter title",
                        "reasoning": "evidence",
                        "suggestion": "fix it",
                    }]
                )
                degraded = review_posting._summary_only({"body": "summary", "comments": comments})
                self.assertIn(
                    f"#### `x.py:4`\n\n[{severity}] deep formatter title",
                    degraded["body"],
                )

    def test_deep_unanchored_formatter_matches_gate_contract(self) -> None:
        payload = mod.format_review(
            {
                "approve": False,
                "summary": "summary",
                "findings": [{
                    "severity": "P2",
                    "file": "outside.py",
                    "line": 9,
                    "title": "unanchored formatter title",
                    "reasoning": "evidence",
                    "suggestion": "fix it",
                }],
            },
            head_sha="abc123",
            anchors={},
        )
        self.assertIn(
            "- **[P2] `outside.py:9`** unanchored formatter title",
            payload["body"],
        )


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
        # Legacy RIGHT-only anchor shape — still accepted for back-compat.
        anchors = {"a.py": {3}, "b.py": {4}}
        body = mod.format_review(r, head_sha="abc123", anchors=anchors)["body"]
        # Marker must be first line so merge-gate greps still match.
        self.assertTrue(body.startswith(mod.MARKER))
        self.assertIn("## Quibble Review Summary", body)
        self.assertIn("status: **request changes**", body)
        # Count headers for all three severities are always emitted so
        # downstream regex greps work regardless of which severities the
        # reviewer actually raised.
        self.assertIn("### P1 (1)", body)
        self.assertIn("### P2 (1)", body)
        self.assertIn("### P3 (0)", body)
        # "inline in Files changed" pointer so a human reader knows where to
        # look for the actual finding text.
        self.assertIn("Findings inline in Files changed.", body)
        self.assertIn("<summary>What Quibble checked</summary>", body)

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
        anchors = {"scripts/x.py": {42}}
        comments = mod.format_review(r, head_sha="abc123", anchors=anchors)["comments"]
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
        # count in the body's severity buckets so nothing is silently lost,
        # and now also get echoed in an `### Unanchored findings` section.
        r = {
            "approve": False,
            "findings": [
                {"severity": "P2", "file": "a.py", "line": None, "title": "no line"},
                {"severity": "P2", "file": "a.py", "line": 5, "title": "anchored"},
            ],
        }
        anchors = {"a.py": {5}}
        p = mod.format_review(r, head_sha="abc123", anchors=anchors)
        self.assertEqual(len(p["comments"]), 1)
        self.assertEqual(p["comments"][0]["line"], 5)
        # Both still counted in the body's P2 bucket.
        self.assertIn("### P2 (2)", p["body"])
        # The dropped one still shows up under Unanchored findings.
        self.assertIn("### Unanchored findings", p["body"])
        self.assertIn("no line", p["body"])

    def test_hallucinated_file_routes_to_unanchored(self) -> None:
        # Reviewers routinely cite a file that isn't in this PR's diff — the
        # atomic POST would 422 the whole review. Validate against anchors
        # and route bad references to the body instead of dropping the review.
        r = {
            "approve": False,
            "findings": [
                {
                    "severity": "P1",
                    "file": "does/not/exist.py",
                    "line": 10,
                    "title": "hallucinated",
                    "reasoning": "model made this file up",
                },
                {
                    "severity": "P2",
                    "file": "real.py",
                    "line": 999,  # file real but line outside any hunk
                    "title": "line beyond hunk",
                },
            ],
        }
        anchors = {"real.py": {1, 2, 3}}
        p = mod.format_review(r, head_sha="abc123", anchors=anchors)
        # Neither anchors — both must route to the body.
        self.assertEqual(p["comments"], [])
        self.assertIn("### Unanchored findings", p["body"])
        self.assertIn("hallucinated", p["body"])
        self.assertIn("line beyond hunk", p["body"])
        # Event still respects the P1 → REQUEST_CHANGES contract even when
        # the P1 could not be anchored inline.
        self.assertEqual(p["event"], "REQUEST_CHANGES")


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

    def test_synthetic_p1_forces_REQUEST_CHANGES_and_stays_in_body(self) -> None:
        # `main()` builds the synthetic P1 with `file: null, line: null` so
        # it MUST land in the body's `### Unanchored findings` section,
        # never as an inline comment. Anchoring it against any non-diff
        # path (an earlier draft used `.github/reviewer:1`) was the bug
        # that 422'd every truncated-diff review — the whole POST failed
        # atomically, dropping the REQUEST_CHANGES verdict along with it.
        # The path is now `SYNTHETIC_TRUNCATION_PATH`, a URL-scheme sentinel
        # that can't collide with real files like `.github/reviewers.yml`.
        review = {
            "approve": False,
            "findings": [
                {
                    "severity": "P1",
                    "file": None,
                    "line": None,
                    "title": "Diff truncated — cannot approve",
                    "reasoning": "reviewer saw a partial diff",
                }
            ],
        }
        p = mod.format_review(review, head_sha="abc123", truncated_bytes=500)
        self.assertEqual(p["event"], "REQUEST_CHANGES")
        # Synthetic finding must NOT anchor inline — one bad anchor 422s
        # the whole review.
        self.assertEqual(p["comments"], [])
        # Text still reaches the PR via the body section.
        self.assertIn("### Unanchored findings", p["body"])
        self.assertIn("Diff truncated", p["body"])


class DiffAnchorParsingTests(unittest.TestCase):
    """`_parse_hunk_right_lines` is the truth we validate anchors against."""

    def test_basic_hunk_lines(self) -> None:
        patch = (
            "@@ -1,3 +1,4 @@\n"
            " context1\n"
            "+added1\n"
            "+added2\n"
            " context2\n"
        )
        # RIGHT lines: 1 (context1), 2 (added1), 3 (added2), 4 (context2).
        self.assertEqual(mod._parse_hunk_right_lines(patch), {1, 2, 3, 4})

    def test_removed_lines_are_not_on_right(self) -> None:
        patch = (
            "@@ -10,4 +12,3 @@\n"
            " ctx\n"
            "-removed1\n"
            "-removed2\n"
            "+added\n"
        )
        # Only ctx (12) and added (13) exist on RIGHT.
        self.assertEqual(mod._parse_hunk_right_lines(patch), {12, 13})

    def test_multiple_hunks(self) -> None:
        patch = (
            "@@ -1,1 +1,1 @@\n"
            "+a\n"
            "@@ -50,2 +60,3 @@\n"
            " x\n"
            "+y\n"
            " z\n"
        )
        self.assertEqual(mod._parse_hunk_right_lines(patch), {1, 60, 61, 62})

    def test_no_newline_meta_is_ignored(self) -> None:
        patch = (
            "@@ -1,1 +1,2 @@\n"
            "+one\n"
            "+two\n"
            "\\ No newline at end of file\n"
        )
        self.assertEqual(mod._parse_hunk_right_lines(patch), {1, 2})


class PartitionFindingsTests(unittest.TestCase):
    """`partition_findings` gates the Reviews API POST — must be tight."""

    def test_anchorable_goes_inline_others_go_body(self) -> None:
        findings = [
            {"severity": "P2", "file": "a.py", "line": 5, "title": "ok"},
            {"severity": "P2", "file": "a.py", "line": 999, "title": "beyond"},
            {"severity": "P2", "file": "nope.py", "line": 1, "title": "hallucinated"},
            {"severity": "P2", "file": "a.py", "line": None, "title": "no line"},
            {"severity": "P2", "file": None, "line": 5, "title": "no file"},
        ]
        anchors = {"a.py": {5, 6}}
        inline, unanchored = mod.partition_findings(findings, anchors)
        self.assertEqual([f["title"] for f in inline], ["ok"])
        self.assertEqual(
            [f["title"] for f in unanchored],
            ["beyond", "hallucinated", "no line", "no file"],
        )

    def test_empty_anchors_routes_everything_to_body(self) -> None:
        # get_diff_anchors failure path: better to lose inline placement
        # than to lose the whole review to a bad anchor.
        findings = [{"severity": "P1", "file": "a.py", "line": 5, "title": "x"}]
        inline, unanchored = mod.partition_findings(findings, {})
        self.assertEqual(inline, [])
        self.assertEqual(len(unanchored), 1)


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

        # Anchor for scripts/x.py line 10 must be present in the fake files
        # payload — otherwise partition_findings routes it to the body and
        # the "one inline comment" assertion below fails.
        files_payload = json.dumps([
            {
                "filename": "scripts/x.py",
                "patch": "@@ -8,3 +8,5 @@\n ctx8\n ctx9\n+added10\n+added11\n ctx12\n",
            }
        ])

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
            if "/pulls/5/files" in joined:
                # get_diff_anchors — return a fake files listing.
                return self._run_returns(stdout=files_payload)
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


class FindPriorReviewsFilterTests(unittest.TestCase):
    """`find_prior_reviews` must filter by marker AND state, not just login.

    Historically, both Quibble passes posted as `quibble-review[bot]`.
    Filtering on login alone let one pass dismiss the other's reviews — the
    exact bug this marker test guards against. It also verifies the state
    filter that keeps COMMENTED reviews (not dismiss-able) out of the list.

    Also guards the fallback-identity widening (Codex P1 round 3):
    `_resolve_gh_env` falls back to `GITHUB_TOKEN` when App auth is
    unavailable — reviews posted under that token are authored by
    `github-actions[bot]`, not `quibble-review[bot]`. The filter must match
    EITHER identity so a fallback-authored CHANGES_REQUESTED can be
    dismissed after App auth is restored.
    """

    def test_jq_expression_includes_marker_and_state_filter(self) -> None:
        captured: dict[str, list[str]] = {"cmd": []}

        def _fake_run(cmd, **kw):
            captured["cmd"] = list(cmd)
            r = mock.MagicMock()
            r.stdout = ""
            r.stderr = ""
            r.returncode = 0
            return r

        with mock.patch("subprocess.run", side_effect=_fake_run):
            mod.find_prior_reviews("o/r", "5", env={})

        # The `--jq` value must reference this reviewer's marker so the script
        # never dismisses another marker-scoped review sharing its identity.
        self.assertIn("--jq", captured["cmd"])
        jq_expr = captured["cmd"][captured["cmd"].index("--jq") + 1]
        self.assertIn(mod.MARKER, jq_expr)
        # Both supported identities (preferred + documented fallback) must
        # appear in the jq expression — the fallback identity is the whole
        # point of SUPPORTED_BOT_IDENTITIES.
        for identity in mod.SUPPORTED_BOT_IDENTITIES:
            self.assertIn(identity, jq_expr)
        self.assertIn("quibble-review[bot]", jq_expr)
        self.assertIn("github-actions[bot]", jq_expr)
        # State filter must exclude COMMENTED (the dismissals endpoint 422s
        # on it) and stick to the two gate-able states.
        self.assertIn("APPROVED", jq_expr)
        self.assertIn("CHANGES_REQUESTED", jq_expr)

    def test_supported_bot_identities_constant_shape(self) -> None:
        """The constant is a tuple with quibble preferred, github-actions fallback."""
        self.assertIsInstance(mod.SUPPORTED_BOT_IDENTITIES, tuple)
        self.assertEqual(
            mod.SUPPORTED_BOT_IDENTITIES,
            ("quibble-review[bot]", "github-actions[bot]"),
        )

    def test_fallback_authored_review_with_marker_is_returned(self) -> None:
        """The fix: a `github-actions[bot]` review carrying our MARKER MUST
        be returned by `find_prior_reviews` so `main()` can dismiss it.

        Also guards the negatives:
        - `github-actions[bot]` WITHOUT the marker (some OTHER workflow's
          review) is NOT returned — the MARKER body check scopes us.
        - `quibble-review[bot]` with a different workflow marker is not returned.
        - Human reviews are NEVER returned.

        Runs `gh api --paginate ... --jq <expr>` end-to-end by mocking
        subprocess.run to feed a fake `gh api` response through the REAL
        jq binary (via a second subprocess). Skips if jq is unavailable.
        """
        import shutil
        if shutil.which("jq") is None:
            self.skipTest("jq not on PATH")

        # Realistic mixed cast: a fallback-authored CHANGES_REQUESTED with
        # OUR marker (must dismiss), a fallback-authored review from some
        # unrelated workflow (must NOT dismiss), another quibble-authored
        # workflow review (different marker, must NOT dismiss), a COMMENTED review
        # (wrong state, must NOT dismiss), and a human review.
        fake_reviews = [
            {  # id=1: fallback-authored, our marker, gate-able state → DISMISS
                "id": 1,
                "user": {"login": "github-actions[bot]"},
                "state": "CHANGES_REQUESTED",
                "body": f"{mod.MARKER}\n\n## Quibble Review Summary\n### P1 (1)\n- bad",
            },
            {  # id=2: some OTHER github-actions workflow's review → skip
                "id": 2,
                "user": {"login": "github-actions[bot]"},
                "state": "CHANGES_REQUESTED",
                "body": "<!-- some-other-workflow --> Unrelated CI review",
            },
            {  # id=3: another workflow (quibble login, wrong marker) → skip
                "id": 3,
                "user": {"login": "quibble-review[bot]"},
                "state": "CHANGES_REQUESTED",
                "body": "<!-- reviewer:other -->\n\n## Other workflow review",
            },
            {  # id=4: quibble + our marker + gate-able state → DISMISS
                "id": 4,
                "user": {"login": "quibble-review[bot]"},
                "state": "APPROVED",
                "body": f"{mod.MARKER}\n\nlooks good",
            },
            {  # id=5: COMMENTED (wrong state) even w/ our marker → skip
                "id": 5,
                "user": {"login": "quibble-review[bot]"},
                "state": "COMMENTED",
                "body": f"{mod.MARKER}\n\ncommentary",
            },
            {  # id=6: human review, even with our marker copy-pasted → skip
                "id": 6,
                "user": {"login": "some-human"},
                "state": "CHANGES_REQUESTED",
                "body": f"{mod.MARKER}\n\nhuman said no",
            },
        ]

        # Mock subprocess.run to intercept the gh api call, then run the
        # REAL jq binary against the fake payload with the SAME --jq
        # expression the script constructed. Whatever jq prints is what
        # the script would have parsed from gh. `real_run` captures the
        # real function BEFORE the patch so the test's own jq invocation
        # isn't re-intercepted.
        import subprocess as _subprocess
        real_run = _subprocess.run

        def _fake_run(cmd, **kw):
            self.assertIn("--jq", cmd)
            jq_expr = cmd[cmd.index("--jq") + 1]
            # Feed the fake reviews array into real jq.
            proc = real_run(
                ["jq", "-r", jq_expr],
                input=json.dumps(fake_reviews),
                capture_output=True,
                text=True,
                check=True,
            )
            r = mock.MagicMock()
            r.stdout = proc.stdout
            r.stderr = ""
            r.returncode = 0
            return r

        with mock.patch("subprocess.run", side_effect=_fake_run):
            ids = mod.find_prior_reviews("o/r", "5", env={})

        # Sorted for stable comparison — order of ids from jq is input
        # order, but this asserts the SET is right regardless.
        self.assertEqual(sorted(ids), [1, 4])


class GetDiffAnchorsIntegrationTests(unittest.TestCase):
    """`get_diff_anchors` shells out to `gh api /pulls/{N}/files`.

    Mock the shell layer and check the returned mapping matches what
    `_parse_hunk_right_lines` would produce for the fake `patch` field.
    """

    def test_parses_gh_files_output(self) -> None:
        files_json = json.dumps([
            {
                "filename": "a.py",
                "patch": "@@ -1,2 +1,3 @@\n one\n+two\n three\n",
            },
            {
                "filename": "b.md",
                "patch": "@@ -10,1 +10,2 @@\n x\n+y\n",
            },
            {
                "filename": "vendored.bin",
                # binary / no patch — must contribute no anchors.
            },
        ])

        def _fake_run(cmd, **kw):
            r = mock.MagicMock()
            r.stdout = files_json
            r.stderr = ""
            r.returncode = 0
            return r

        with mock.patch("subprocess.run", side_effect=_fake_run):
            anchors = mod.get_diff_anchors("o/r", "5", env={})

        # New sided shape: {filename: {"RIGHT": {lines}, "LEFT": {lines}}}
        self.assertEqual(anchors["a.py"]["RIGHT"], {1, 2, 3})
        self.assertEqual(anchors["b.md"]["RIGHT"], {10, 11})
        self.assertNotIn("vendored.bin", anchors)


class ParseHunkSidedLinesTests(unittest.TestCase):
    """`_parse_hunk_sided_lines` must return both sides correctly.

    Codex P1 round 2: the Reviews API rejects a `side: RIGHT` comment on
    a deleted line. This function is the truth we validate against — its
    output feeds `partition_findings` which picks the side per finding.
    """

    def test_context_lines_appear_on_both_sides(self) -> None:
        # Pure context — same line on LEFT and RIGHT.
        patch = "@@ -1,2 +1,2 @@\n one\n two\n"
        sided = mod._parse_hunk_sided_lines(patch)
        self.assertEqual(sided["RIGHT"], {1, 2})
        self.assertEqual(sided["LEFT"], {1, 2})

    def test_added_lines_only_on_right(self) -> None:
        patch = "@@ -1,0 +1,2 @@\n+a\n+b\n"
        sided = mod._parse_hunk_sided_lines(patch)
        self.assertEqual(sided["RIGHT"], {1, 2})
        self.assertEqual(sided["LEFT"], set())

    def test_removed_lines_only_on_left(self) -> None:
        # Two deleted lines starting at LEFT line 5; RIGHT stays empty
        # because nothing lands on the post-change side.
        patch = "@@ -5,2 +5,0 @@\n-old1\n-old2\n"
        sided = mod._parse_hunk_sided_lines(patch)
        self.assertEqual(sided["RIGHT"], set())
        self.assertEqual(sided["LEFT"], {5, 6})

    def test_mixed_hunk_partitions_correctly(self) -> None:
        # A hunk with context + one deletion + one addition.
        patch = (
            "@@ -10,3 +12,3 @@\n"
            " ctx\n"        # LEFT 10, RIGHT 12
            "-removed\n"    # LEFT 11
            "+added\n"      # RIGHT 13
            " tail\n"       # LEFT 12, RIGHT 14
        )
        sided = mod._parse_hunk_sided_lines(patch)
        self.assertEqual(sided["RIGHT"], {12, 13, 14})
        self.assertEqual(sided["LEFT"], {10, 11, 12})


class PartitionSidedAnchorsTests(unittest.TestCase):
    """`partition_findings` must pick the correct side per finding.

    Sending a deleted-line finding as `side: RIGHT` 422s the whole
    atomic POST — this is Codex P1 round 2. Assert per-side resolution.
    """

    def test_removed_line_routes_to_left_side(self) -> None:
        findings = [
            {"severity": "P2", "file": "a.py", "line": 11, "title": "deleted"},
        ]
        # LEFT-only line 11 (a deletion), RIGHT has different lines.
        anchors = {"a.py": {"RIGHT": {12, 13}, "LEFT": {10, 11}}}
        inline, unanchored = mod.partition_findings(findings, anchors)
        self.assertEqual(len(inline), 1)
        self.assertEqual(inline[0]["_side"], "LEFT")
        self.assertEqual(unanchored, [])

    def test_added_line_routes_to_right_side(self) -> None:
        findings = [
            {"severity": "P1", "file": "a.py", "line": 13, "title": "new"},
        ]
        anchors = {"a.py": {"RIGHT": {12, 13}, "LEFT": {10, 11}}}
        inline, unanchored = mod.partition_findings(findings, anchors)
        self.assertEqual(len(inline), 1)
        self.assertEqual(inline[0]["_side"], "RIGHT")

    def test_context_line_prefers_right(self) -> None:
        # Context lines appear on both sides — RIGHT is the preferred
        # anchor because reviewers overwhelmingly comment on the new file.
        findings = [
            {"severity": "P2", "file": "a.py", "line": 12, "title": "context"},
        ]
        anchors = {"a.py": {"RIGHT": {12, 13}, "LEFT": {10, 12}}}
        inline, unanchored = mod.partition_findings(findings, anchors)
        self.assertEqual(inline[0]["_side"], "RIGHT")

    def test_legacy_set_anchors_treated_as_right(self) -> None:
        # Pre-P1-round-2 callers still pass `dict[str, set[int]]`. Those
        # sets are RIGHT-only by construction; partition treats them so.
        findings = [
            {"severity": "P2", "file": "a.py", "line": 5, "title": "x"},
        ]
        anchors = {"a.py": {5, 6}}
        inline, _ = mod.partition_findings(findings, anchors)
        self.assertEqual(inline[0]["_side"], "RIGHT")

    def test_comment_uses_left_side_when_partition_says_left(self) -> None:
        # End-to-end: format_review_comments must emit `side: LEFT` for a
        # LEFT-anchored finding. This is the whole point of the fix.
        r = {
            "approve": False,
            "findings": [
                {"severity": "P1", "file": "a.py", "line": 11, "title": "deleted"},
            ],
        }
        anchors = {"a.py": {"RIGHT": {12}, "LEFT": {10, 11}}}
        p = mod.format_review(r, head_sha="abc123", anchors=anchors)
        self.assertEqual(len(p["comments"]), 1)
        self.assertEqual(p["comments"][0]["side"], "LEFT")
        self.assertEqual(p["comments"][0]["line"], 11)


class SyntheticPathAssertionTests(unittest.TestCase):
    """`_assert_no_synthetic_paths_in_comments` guards the truncation-P1 route."""

    def test_raises_on_synthetic_truncation_path(self) -> None:
        # The exact sentinel we tell the model to use for the truncation P1.
        # If it ever leaks into `comments` (should have routed to the body's
        # Unanchored section) the atomic POST would 422 — this is what the
        # assertion catches before the API sees it.
        comments = [
            {
                "path": mod.SYNTHETIC_TRUNCATION_PATH,
                "line": 1,
                "side": "RIGHT",
                "body": "x",
            },
        ]
        with self.assertRaises(RuntimeError):
            mod._assert_no_synthetic_paths_in_comments(comments)

    def test_ok_when_all_paths_are_real(self) -> None:
        comments = [
            {"path": "scripts/x.py", "line": 5, "side": "RIGHT", "body": "y"},
        ]
        mod._assert_no_synthetic_paths_in_comments(comments)  # no raise

    def test_ok_on_real_dot_github_reviewers_yml(self) -> None:
        # Regression: an earlier `startswith(".github/reviewer")` prefix
        # check tripped on the legitimate new file `.github/reviewers.yml`
        # (added by PR #76 for the CODEOWNERS-style reviewer roster),
        # blocking every review that flagged it. The sentinel is now a
        # distinct string matched exactly, so real repo paths that happen
        # to share the old prefix pass cleanly.
        comments = [
            {
                "path": ".github/reviewers.yml",
                "line": 3,
                "side": "RIGHT",
                "body": "flag",
            },
            {"path": ".github/reviewers", "line": 1, "side": "RIGHT", "body": "b"},
            {
                "path": ".github/reviewer-config",
                "line": 1,
                "side": "RIGHT",
                "body": "c",
            },
        ]
        mod._assert_no_synthetic_paths_in_comments(comments)  # no raise

    def test_sentinel_is_not_a_valid_filesystem_path(self) -> None:
        # Sanity: the sentinel we ship must be structurally impossible for
        # anyone to introduce as a real file, or the collision that caused
        # PR #76's outage comes right back. `//` inside the path is not a
        # filename most tooling will ever produce; the URL-scheme prefix is
        # not a legal path component on any real filesystem.
        self.assertIn("://", mod.SYNTHETIC_TRUNCATION_PATH)
        self.assertFalse(mod.SYNTHETIC_TRUNCATION_PATH.startswith("."))


class HeadRecheckTests(unittest.TestCase):
    """`fetch_current_head_sha` shells out to `gh pr view` and returns the SHA."""

    def test_returns_stripped_sha_from_gh_output(self) -> None:
        def _fake_run(cmd, **kw):
            r = mock.MagicMock()
            r.stdout = "deadbeef1234\n"
            r.stderr = ""
            r.returncode = 0
            return r

        with mock.patch("subprocess.run", side_effect=_fake_run):
            sha = mod.fetch_current_head_sha("o/r", "5", env={})
        self.assertEqual(sha, "deadbeef1234")

    def test_returns_empty_on_error_never_raises(self) -> None:
        # Fetch failure must not crash the reviewer — the caller treats
        # empty as "cannot verify, proceed with POST".
        def _fake_run(cmd, **kw):
            raise RuntimeError("gh exploded")

        with mock.patch("subprocess.run", side_effect=_fake_run):
            sha = mod.fetch_current_head_sha("o/r", "5", env={})
        self.assertEqual(sha, "")


if __name__ == "__main__":
    unittest.main()
