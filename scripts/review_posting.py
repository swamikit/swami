"""Shared, diagnosable GitHub Reviews API posting."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any

MAX_REVIEW_BODY_BYTES = 60_000


def _shape(payload: dict[str, Any]) -> str:
    comments = payload.get("comments")
    count = len(comments) if isinstance(comments, list) else 0
    return (
        f"event={payload.get('event', '<absent>')} "
        f"commit_id={payload.get('commit_id', '<absent>')} comments={count}"
    )


def _error_text(result: subprocess.CompletedProcess[str]) -> str:
    raw = (result.stderr or result.stdout or "<empty response>").strip()
    return " ".join(raw.splitlines())[:2000]


def _http_status(error: str) -> int | None:
    match = re.search(r"\bHTTP(?:/\S+)?\s+(\d{3})\b", error)
    return int(match.group(1)) if match else None


def _post(
    repo: str,
    pr: str,
    payload: dict[str, Any],
    env: dict[str, str] | None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/pulls/{pr}/reviews",
            "-X",
            "POST",
            "--input",
            "-",
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _summary_only(payload: dict[str, Any]) -> dict[str, Any]:
    degraded = dict(payload)
    comments = payload.get("comments")
    comment_list = comments if isinstance(comments, list) else []
    preserved: list[str] = []
    unpreserved = 0
    for comment in comment_list:
        if not isinstance(comment, dict):
            unpreserved += 1
            continue
        path = str(comment.get("path") or "unknown path")
        line = comment.get("line") or comment.get("start_line")
        body = str(comment.get("body") or "").strip()
        if not body:
            unpreserved += 1
            continue
        location = f"{path}:{line}" if line is not None else path
        headline, *details = body.splitlines()
        if re.match(r"^\[P[123]\]\s+\S", headline) is None:
            unpreserved += 1
            continue
        quoted_details = "\n".join(f"> {part}" if part else ">" for part in details)
        entry = f"#### `{location}`\n\n{headline}"
        if quoted_details:
            entry += "\n\n" + quoted_details
        preserved.append(entry)
    if unpreserved:
        preserved.append(
            "#### `review-body`\n\n"
            f"[P1] Summary-only fallback could not preserve {unpreserved} "
            "inline finding(s)"
        )
    if preserved:
        fallback_section = (
            str(payload.get("body") or "")
            + "\n\n### Inline findings (summary-only fallback)\n\n"
            + "_GitHub rejected at least one inline anchor; finding text is "
            "preserved here._\n\n"
            + "\n\n".join(preserved)
        )
    else:
        fallback_section = (
            str(payload.get("body") or "")
            + "\n\n### Inline findings (summary-only fallback)\n\n"
            + f"_GitHub rejected the inline anchors; {len(comment_list)} "
            "finding(s) could not be preserved._\n\n"
            + "#### `review-body`\n\n"
            + "[P1] Summary-only fallback could not preserve inline findings"
        )
    encoded = fallback_section.encode("utf-8")
    if len(encoded) > MAX_REVIEW_BODY_BYTES:
        omitted = len(encoded) - MAX_REVIEW_BODY_BYTES
        while True:
            marker = (
                "\n\n_Content truncated to fit the GitHub review-body limit "
                f"({omitted} bytes omitted)._\n\n"
                "### Inline findings (summary-only fallback)\n\n"
                "#### `review-body`\n\n"
                "[P1] Summary-only fallback was truncated; inspect and rerun "
                "the reviewer with fewer findings"
            )
            budget = MAX_REVIEW_BODY_BYTES - len(marker.encode("utf-8"))
            actual_omitted = len(encoded) - budget
            if actual_omitted == omitted:
                break
            omitted = actual_omitted
        fallback_section = encoded[:budget].decode("utf-8", errors="ignore") + marker
    degraded["body"] = fallback_section
    degraded["comments"] = []
    return degraded


def _self_test_fixture() -> str:
    """Render the production fallback format for merge-gate's shell test."""
    return _summary_only(
        {
            "body": "<!-- reviewer:claude -->\n\nfixture",
            "comments": [
                {
                    "path": "scripts/fallback.py",
                    "line": 34,
                    "body": (
                        "[P3] Preserve rejected inline detail\n\n"
                        "A quoted nested example follows.\n"
                        "#### `scripts/phantom-nested.py:97`\n\n"
                        "[P1] Do not collect nested prose"
                    ),
                },
                {
                    "path": "scripts/blocking.py",
                    "line": 56,
                    "body": "[P1] Preserve rejected blocking detail",
                },
            ],
        }
    )["body"]


def post_review(
    repo: str,
    pr: str,
    payload: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
    reviewer: str = "reviewer",
) -> dict[str, Any]:
    """Post atomically, degrading a 422 to a summary-only review once.

    ``reviewer`` is used only as a diagnostic label; it never dispatches
    reviewer-specific behavior.
    """
    result = _post(repo, pr, payload, env)
    if result.returncode == 0:
        return json.loads(result.stdout) if result.stdout.strip() else {}

    first_error = _error_text(result)
    print(
        f"::error::{reviewer} Reviews API POST failed: {first_error}; "
        f"payload-shape: {_shape(payload)}",
        file=sys.stderr,
    )

    comments = payload.get("comments")
    if _http_status(first_error) == 422 and isinstance(comments, list) and comments:
        degraded = _summary_only(payload)
        print(
            f"::warning::{reviewer} retrying Reviews API without inline anchors; "
            f"payload-shape: {_shape(degraded)}",
            file=sys.stderr,
        )
        retry = _post(repo, pr, degraded, env)
        if retry.returncode == 0:
            return json.loads(retry.stdout) if retry.stdout.strip() else {}
        retry_error = _error_text(retry)
        print(
            f"::error::{reviewer} summary-only Reviews API retry failed: "
            f"{retry_error}; payload-shape: {_shape(degraded)}",
            file=sys.stderr,
        )
        raise RuntimeError(
            f"POST /pulls/{pr}/reviews failed after summary-only retry "
            f"(rc={retry.returncode}): {retry_error}"
        )

    raise RuntimeError(
        f"POST /pulls/{pr}/reviews failed (rc={result.returncode}): {first_error}"
    )


if __name__ == "__main__" and sys.argv[1:] == ["--self-test-fixture"]:
    print(_self_test_fixture())
