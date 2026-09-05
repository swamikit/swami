#!/usr/bin/env python3
"""Claude review of the current PR, posted as a marker-tagged sticky comment.

Env: GITHUB_REPOSITORY, PR_NUMBER, HEAD_SHA (opt), GITHUB_WORKSPACE (repo root),
ANTHROPIC_API_KEY, GH_TOKEN. Optional: PR_DIFF_FILE (default /tmp/pr.diff),
STICKY_FILE (default /tmp/sticky.md).
"""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import anthropic

MARKER = "<!-- claude-review -->"
MODEL = "claude-opus-5"
MAX_TOKENS = 16000
# Cap the diff we send to Claude. Origami-Patterns-scale PRs comfortably fit;
# a runaway diff (generated files, vendored trees) would otherwise blow past
# the model context and either fail the call or waste budget on noise.
MAX_DIFF_BYTES = 200_000

CONTEXT_PATHS = (
    "AGENTS.md",
    "skill/review/SKILL.md",
    "docs/decisions/0009-native-first-helpers-for-recurring-mismatches.md",
    "docs/decisions/0010-helper-naming-and-faithful-patch-mapping.md",
    "docs/decisions/0013-runner-installs-origami-live-render.md",
    "docs/decisions/0014-ssim-informational-not-gating.md",
)


def sh(cmd: list[str]) -> str:
    r = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return r.stdout


def load_context(repo_root: Path) -> str:
    parts: list[str] = []
    for rel in CONTEXT_PATHS:
        p = repo_root / rel
        if p.exists():
            parts.append(f"===== {rel} =====\n{p.read_text()}")
        else:
            parts.append(f"===== {rel} =====\n(not present on this branch)")
    return "\n\n".join(parts)


def build_system(context: str, truncated_bytes: int = 0) -> str:
    truncation_note = ""
    if truncated_bytes > 0:
        # Belt: tell the model directly it cannot approve on a partial read. The
        # code below is the suspenders — we override the verdict either way,
        # but a well-behaved model should not put us in that position.
        truncation_note = (
            "\n\nIMPORTANT — DIFF TRUNCATED: The PR diff shown to you was truncated "
            f"at {MAX_DIFF_BYTES} bytes ({truncated_bytes} bytes omitted). You have "
            "NOT seen the whole change. Under ADR-0014 the Reviewer read IS the "
            "merge gate — approving on a partial read is a false green. You MUST "
            'return approve=false and include a blocking finding at file '
            '".github/reviewer" line 1 explaining that the PR must be split or '
            "reviewed manually. Do not approve.\n"
        )
    return (
        "You are the Reviewer GA for the swami repository. Follow the Reviewer skill "
        "below. Findings are testable claims tied to a file and (where possible) a "
        "line — no vibes, no manager-report tone. Cite the ADR or skill section that "
        "grounds each finding. SSIM alone is evidence, not verdict (ADR-0014). Do "
        "NOT propose edits to the pixel-gate sticky comment (verify.yml owns it).\n\n"
        "Respond with a SINGLE JSON object and nothing else, matching this shape:\n"
        '{"summary": "<one paragraph read of the PR>",'
        ' "findings": [{"severity": "blocking"|"nit"|"nice-to-have",'
        ' "file": "path/from/repo/root", "line": <int or null>,'
        ' "claim": "<short claim>", "evidence": "<why — cite ADR/skill/beat>"}],'
        ' "approve": <bool — true only when no blocking findings>}\n'
        "If the diff is empty or trivial, return findings=[] and approve=true."
        + truncation_note
        + "\n\n===== REPO CONTEXT =====\n" + context
    )


def call_claude(system: str, diff: str, sticky: str, truncated_bytes: int = 0) -> dict:
    client = anthropic.Anthropic()
    user = ["## PR diff\n\n```diff\n" + diff + "\n```"]
    if truncated_bytes > 0:
        user.append(
            "## Diff was truncated\n\n"
            f"The diff above was cut at {MAX_DIFF_BYTES} bytes; "
            f"{truncated_bytes} bytes were omitted. You have not seen the whole "
            "PR. Per the system prompt and ADR-0014 you must return "
            'approve=false with a blocking finding at ".github/reviewer" line 1 '
            "stating that the PR must be split or reviewed manually."
        )
    if sticky.strip():
        user.append(
            "## Pixel-gate sticky (read-only context — do NOT propose edits to it)\n\n"
            + sticky
        )
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": "\n\n".join(user)}],
    ) as stream:
        msg = stream.get_final_message()
    for block in msg.content:
        if getattr(block, "type", None) == "text" and block.text.strip():
            return _extract_json(block.text)
    raise RuntimeError("no text block in Claude response")


def _extract_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(f"no JSON object in response: {text[:200]!r}")
    return json.loads(t[start : end + 1])


def format_comment(review: dict, head_sha: str, truncated_bytes: int = 0) -> str:
    findings = review.get("findings") or []
    approve = bool(review.get("approve"))
    summary = (review.get("summary") or "").strip()
    lines = [MARKER, "", "## Claude review", ""]
    if head_sha:
        lines += [f"HEAD: `{head_sha}`", ""]
    if truncated_bytes > 0:
        # Human-visible banner so a reader of the PR comment sees the constraint
        # without having to dig into the workflow logs.
        lines += [
            f"> ⚠ diff truncated at {MAX_DIFF_BYTES} bytes "
            f"({truncated_bytes} bytes omitted) — full review requires "
            "splitting the PR.",
            "",
        ]
    if summary:
        lines += [summary, ""]
    if not findings:
        lines.append("_No findings._")
    else:
        buckets: dict[str, list[dict]] = {"blocking": [], "nit": [], "nice-to-have": []}
        for f in findings:
            # Normalize severity — unknown / null / oddly-cased values fold into
            # "nice-to-have" so the render loop (which iterates the three known
            # buckets) never silently drops a finding.
            sev = str(f.get("severity") or "").strip().lower()
            if sev not in buckets:
                sev = "nice-to-have"
            buckets[sev].append(f)
        for sev in ("blocking", "nit", "nice-to-have"):
            items = buckets.get(sev) or []
            if not items:
                continue
            lines += [f"### {sev.capitalize()} ({len(items)})"]
            for f in items:
                loc = str(f.get("file") or "?")
                if f.get("line"):
                    loc += f":{f['line']}"
                claim = (f.get("claim") or "").strip()
                evidence = (f.get("evidence") or "").strip()
                lines.append(f"- `{loc}` — {claim}")
                if evidence:
                    lines.append(f"  - {evidence}")
            lines.append("")
    verdict = "approve" if approve else "request changes"
    lines += ["", f"_verdict: **{verdict}**_ · reviewer skill: `skill/review/SKILL.md`"]
    return "\n".join(lines)


def find_existing_comment(repo: str, pr: str) -> str | None:
    # Let gh do the filtering: `--paginate` walks every page and `--jq` runs on
    # each page's array, so we get back a plain newline-separated list of ids
    # (one per matching comment) instead of the concatenated-JSON-arrays blob
    # that `json.loads` chokes on once the PR has more than one page of
    # comments.
    out = sh([
        "gh", "api", "--paginate",
        f"repos/{repo}/issues/{pr}/comments",
        "--jq", f'.[] | select(.body | contains("{MARKER}")) | .id',
    ])
    for line in out.splitlines():
        line = line.strip()
        if line:
            return line
    return None


def post_or_update(repo: str, pr: str, body_path: Path) -> None:
    existing = find_existing_comment(repo, pr)
    if existing:
        sh([
            "gh", "api", "--method", "PATCH",
            f"repos/{repo}/issues/comments/{existing}",
            "-F", f"body=@{body_path}",
        ])
        print(f"updated comment {existing}")
    else:
        sh(["gh", "pr", "comment", pr, "--body-file", str(body_path)])
        print("created new comment")


def _cap_diff(diff: str, limit: int = MAX_DIFF_BYTES) -> tuple[str, int]:
    """Return (capped_diff, omitted_bytes). omitted_bytes == 0 means no truncation.

    Callers MUST treat omitted_bytes > 0 as a gate: the reviewer has read only
    part of the change, so a downstream approve verdict is not honest. See
    ADR-0014 and the enforcement in `main`.
    """
    raw = diff.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return diff, 0
    kept = raw[:limit].decode("utf-8", errors="replace")
    omitted = len(raw) - limit
    return kept + f"\n\n[diff truncated — {omitted} bytes omitted]\n", omitted


def _post_failure_comment(repo: str, pr: str, head_sha: str, exc: BaseException) -> None:
    """Best-effort: post a small marker-tagged comment so the PR sees the failure
    instead of a silent workflow-status miss. Never raises — a broken poster
    should not compound the original error."""
    lines = [MARKER, "", "## Claude review"]
    if head_sha:
        lines += ["", f"HEAD: `{head_sha}`"]
    lines += [
        "",
        "_reviewer failed — no findings this run._",
        "",
        f"`{type(exc).__name__}: {exc}`",
        "",
        "See the workflow logs for the full trace. This comment updates in place on retry.",
    ]
    body = "\n".join(lines)
    try:
        out_path = Path("/tmp/claude-review-body.md")
        out_path.write_text(body)
        post_or_update(repo, pr, out_path)
    except Exception as post_exc:  # noqa: BLE001
        print(f"could not post failure comment: {post_exc}", file=sys.stderr)


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = os.environ["PR_NUMBER"]
    head_sha = os.environ.get("HEAD_SHA", "")
    repo_root = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()

    diff_path = Path(os.environ.get("PR_DIFF_FILE", "/tmp/pr.diff"))
    diff = diff_path.read_text() if diff_path.exists() else sh(["gh", "pr", "diff", pr])
    diff, truncated_bytes = _cap_diff(diff)

    sticky_path = Path(os.environ.get("STICKY_FILE", "/tmp/sticky.md"))
    sticky = sticky_path.read_text() if sticky_path.exists() else ""

    system = build_system(load_context(repo_root), truncated_bytes=truncated_bytes)
    try:
        review = call_claude(system, diff, sticky, truncated_bytes=truncated_bytes)
    except Exception as exc:  # noqa: BLE001
        print(f"claude review failed: {exc}", file=sys.stderr)
        _post_failure_comment(repo, pr, head_sha, exc)
        return 1

    # Suspenders: even with the prompt telling the model not to approve on a
    # truncated diff, we enforce it in code. ADR-0014 makes the Reviewer read
    # the merge gate — a partial-read approval would silently bypass it.
    if truncated_bytes > 0 and bool(review.get("approve")):
        print(
            f"overriding approve=true → false: diff truncated at "
            f"{MAX_DIFF_BYTES} bytes ({truncated_bytes} bytes omitted)",
            file=sys.stderr,
        )
        review["approve"] = False
        synthetic = {
            "severity": "blocking",
            "file": ".github/reviewer",
            "line": 1,
            "claim": (
                f"diff truncated at {MAX_DIFF_BYTES} bytes "
                f"({truncated_bytes} bytes omitted) — reviewer read partial; "
                "split the PR or review manually"
            ),
            "evidence": (
                "ADR-0014: Reviewer approval + no unresolved findings is the "
                "merge gate. An approve verdict on a partially-read diff is a "
                "false green. Enforced in scripts/run-claude-review.py::main."
            ),
        }
        review["findings"] = [synthetic] + list(review.get("findings") or [])

    body = format_comment(review, head_sha, truncated_bytes=truncated_bytes)
    out_path = Path("/tmp/claude-review-body.md")
    out_path.write_text(body)
    post_or_update(repo, pr, out_path)
    n = len(review.get("findings") or [])
    print(f"posted review with {n} finding(s); approve={bool(review.get('approve'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
