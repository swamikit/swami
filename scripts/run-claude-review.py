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


def build_system(context: str) -> str:
    return (
        "You are the Reviewer GA for the swami repository. Follow the Reviewer skill "
        "below. Findings are testable claims tied to a file and (where possible) a "
        "line — no vibes, no manager-report tone. Cite the ADR or skill section that "
        "grounds each finding. SSIM alone is evidence, not verdict (ADR-0014). Do "
        "NOT propose edits to the pixel-gate sticky comment (verify.yml owns it).\n\n"
        "Severity taxonomy (aligns with Codex so cross-reviewer tooling can grep a "
        "single set of tokens):\n"
        "  P1 = must-fix before merge (correctness, safety, ADR violation, gate failure)\n"
        "  P2 = should-fix (design smell, unclear code, non-blocking risk)\n"
        "  P3 = nice-to-have (polish, wording, small refactor)\n\n"
        "Respond with a SINGLE JSON object and nothing else, matching this shape:\n"
        '{"summary": "<one paragraph read of the PR>",'
        ' "findings": [{"severity": "P1"|"P2"|"P3",'
        ' "file": "path/from/repo/root", "line": <int or null>,'
        ' "title": "<short title>",'
        ' "reasoning": "<why — cite ADR/skill/beat>",'
        ' "suggestion": "<suggested fix or rebuttal hook, may be empty>"}],'
        ' "approve": <bool — true only when no P1 findings>}\n'
        "If the diff is empty or trivial, return findings=[] and approve=true.\n\n"
        "===== REPO CONTEXT =====\n" + context
    )


def call_claude(system: str, diff: str, sticky: str) -> dict:
    client = anthropic.Anthropic()
    user = ["## PR diff\n\n```diff\n" + diff + "\n```"]
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


def format_comment(review: dict, head_sha: str) -> str:
    findings = review.get("findings") or []
    approve = bool(review.get("approve"))
    summary = (review.get("summary") or "").strip()
    verdict = "approve" if approve else "request changes"
    lines = [MARKER, "", "## Claude review"]
    # Verdict rides on the HEAD line — a single header row at the top so tooling
    # that greps for the marker can read HEAD + verdict without scanning the
    # whole comment. Codex's format does the same.
    head_bits = []
    if head_sha:
        head_bits.append(f"HEAD: `{head_sha}`")
    head_bits.append(f"verdict: **{verdict}**")
    lines += [" · ".join(head_bits), ""]
    if summary:
        lines += [summary, ""]
    if not findings:
        lines.append("_No findings._")
    else:
        # Normalize severity to P1/P2/P3 (aligned with Codex). Unknown / null /
        # legacy values (blocking/nit/nice-to-have from older runs) fold into P3
        # so the render loop — which iterates the three known buckets — never
        # silently drops a finding.
        legacy = {"blocking": "P1", "nit": "P2", "nice-to-have": "P3"}
        buckets: dict[str, list[dict]] = {"P1": [], "P2": [], "P3": []}
        for f in findings:
            raw = str(f.get("severity") or "").strip()
            sev = raw.upper() if raw.upper() in buckets else legacy.get(raw.lower(), "P3")
            buckets[sev].append(f)
        for sev in ("P1", "P2", "P3"):
            items = buckets.get(sev) or []
            if not items:
                continue
            lines += [f"### {sev} ({len(items)})"]
            for f in items:
                loc = str(f.get("file") or "?")
                if f.get("line"):
                    loc += f":{f['line']}"
                # Accept both new (`title`/`reasoning`) and legacy (`claim`/
                # `evidence`) field names so a cached prompt-side or replayed
                # response still renders cleanly during the transition.
                title = (f.get("title") or f.get("claim") or "").strip()
                reasoning = (f.get("reasoning") or f.get("evidence") or "").strip()
                suggestion = (f.get("suggestion") or "").strip()
                lines.append(f"- **`{loc}` — [{sev}] {title}**")
                if reasoning:
                    lines.append(f"  - {reasoning}")
                if suggestion:
                    lines.append(f"  - {suggestion}")
            lines.append("")
    lines += ["_reviewer skill: `skill/review/SKILL.md`_"]
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


def _cap_diff(diff: str, limit: int = MAX_DIFF_BYTES) -> str:
    raw = diff.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return diff
    kept = raw[:limit].decode("utf-8", errors="replace")
    omitted = len(raw) - limit
    return kept + f"\n\n[diff truncated — {omitted} bytes omitted]\n"


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
    diff = _cap_diff(diff)

    sticky_path = Path(os.environ.get("STICKY_FILE", "/tmp/sticky.md"))
    sticky = sticky_path.read_text() if sticky_path.exists() else ""

    system = build_system(load_context(repo_root))
    try:
        review = call_claude(system, diff, sticky)
    except Exception as exc:  # noqa: BLE001
        print(f"claude review failed: {exc}", file=sys.stderr)
        _post_failure_comment(repo, pr, head_sha, exc)
        return 1

    body = format_comment(review, head_sha)
    out_path = Path("/tmp/claude-review-body.md")
    out_path.write_text(body)
    post_or_update(repo, pr, out_path)
    n = len(review.get("findings") or [])
    print(f"posted review with {n} finding(s); approve={bool(review.get('approve'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
