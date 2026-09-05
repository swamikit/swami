from __future__ import annotations

import io
import json
import subprocess
import unittest
from contextlib import redirect_stderr
from unittest import mock

from scripts import review_posting


def _result(returncode: int, *, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class PostReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "body": "summary",
            "event": "APPROVE",
            "commit_id": "abc123",
            "comments": [
                {"path": "x.py", "line": 4, "side": "RIGHT", "body": "[P2] secret finding"}
            ],
        }

    def test_422_retries_summary_only_and_preserves_findings(self) -> None:
        calls: list[dict] = []

        def fake_run(_cmd, **kwargs):
            calls.append(json.loads(kwargs["input"]))
            if len(calls) == 1:
                return _result(1, stderr="gh: invalid anchor (HTTP 422)")
            return _result(0, stdout='{"id": 42}')

        log = io.StringIO()
        with mock.patch("subprocess.run", side_effect=fake_run), redirect_stderr(log):
            result = review_posting.post_review("o/r", "5", self.payload, reviewer="fast")

        self.assertEqual(result, {"id": 42})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["comments"], [])
        self.assertEqual(calls[1]["event"], "APPROVE")
        self.assertIn("secret finding", calls[1]["body"])
        self.assertIn("event=APPROVE commit_id=abc123 comments=1", log.getvalue())
        self.assertNotIn("secret finding", log.getvalue())

    def test_non_422_logs_shape_and_does_not_retry(self) -> None:
        log = io.StringIO()
        with mock.patch(
            "subprocess.run", return_value=_result(1, stderr="gh: forbidden (HTTP 403)")
        ) as run, redirect_stderr(log):
            with self.assertRaises(RuntimeError):
                review_posting.post_review("o/r", "5", self.payload, reviewer="claude")

        run.assert_called_once()
        self.assertIn("HTTP 403", log.getvalue())
        self.assertIn("comments=1", log.getvalue())

    def test_422_status_parser_accepts_cli_and_header_forms(self) -> None:
        self.assertEqual(review_posting._http_status("gh: invalid (HTTP 422)"), 422)
        self.assertEqual(review_posting._http_status("HTTP/2.0 422 Unprocessable"), 422)
        self.assertIsNone(review_posting._http_status("network unavailable"))

    def test_summary_only_body_is_bounded_and_fails_closed_if_truncated(self) -> None:
        payload = dict(self.payload)
        payload["body"] = "<!-- reviewer:claude -->\n\nsummary"
        payload["comments"] = [
            {"path": f"src/file_{i}.py", "line": i + 1, "body": "[P2] title\n\n" + "x" * 1000}
            for i in range(200)
        ]
        degraded = review_posting._summary_only(payload)

        self.assertLessEqual(
            len(degraded["body"].encode("utf-8")),
            review_posting.MAX_REVIEW_BODY_BYTES,
        )
        self.assertIn("[P1] Summary-only fallback was truncated", degraded["body"])
        self.assertIn("<!-- reviewer:claude -->", degraded["body"])
        heading = degraded["body"].rfind("### Inline findings (summary-only fallback)")
        marker = degraded["body"].rfind("[P1] Summary-only fallback was truncated")
        self.assertGreater(heading, -1)
        self.assertGreater(marker, heading)

    def test_missing_line_keeps_a_clean_path(self) -> None:
        payload = dict(self.payload)
        payload["comments"] = [{"path": "x.py", "body": "[P3] no line"}]
        degraded = review_posting._summary_only(payload)
        self.assertIn("#### `x.py`", degraded["body"])
        self.assertNotIn("x.py:?", degraded["body"])

    def test_unpreservable_comments_leave_a_blocking_artifact(self) -> None:
        payload = dict(self.payload)
        payload["comments"] = ["malformed"]
        degraded = review_posting._summary_only(payload)
        self.assertIn("could not preserve 1 inline finding(s)", degraded["body"])
        self.assertIn("[P1] Summary-only fallback could not preserve", degraded["body"])

    def test_noncanonical_headline_becomes_a_blocking_artifact(self) -> None:
        payload = dict(self.payload)
        payload["comments"] = [{"path": "x.py", "line": 3, "body": "no severity"}]
        degraded = review_posting._summary_only(payload)
        self.assertIn("[P1] Summary-only fallback could not preserve", degraded["body"])
        self.assertNotIn("no severity", degraded["body"])

    def test_nested_finding_syntax_is_quoted_in_preserved_prose(self) -> None:
        body = review_posting._self_test_fixture()
        self.assertIn("> #### `scripts/phantom-nested.py:97`", body)
        self.assertNotIn("\n#### `scripts/phantom-nested.py:97`", body)


if __name__ == "__main__":
    unittest.main()
