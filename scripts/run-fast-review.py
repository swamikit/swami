#!/usr/bin/env python3
"""Fast pre-pass PR review, posted as a marker-tagged sticky comment.

This is the cheap Gemini 2.0 Flash pre-pass that runs *before* the deeper
Claude Opus review (`run-claude-review.py`). It surfaces surface bugs, fake
API references, obvious typos, and prose that doesn't parse — the low-hanging
finds — so the deeper reviewer can focus on architecture / ADR alignment.

Coordination points:
- Uses `scripts.model_client.chat_with_fallback` (introduced in a sibling PR).
  If that module is not yet on the branch this script runs from, the import
  fails LOUDLY with an install hint instead of silently no-op'ing.
- Uses a distinct sticky marker (`<!-- fast-review -->`) so it never fights
  with the deep-review sticky (`<!-- claude-review -->`).
- Finding schema mirrors run-claude-review.py (P1/P2/P3, {file, line, severity,
  title, reasoning, suggestion}) so cross-reviewer tooling stays happy.

Env: GITHUB_REPOSITORY, PR_NUMBER, HEAD_SHA (opt), GITHUB_WORKSPACE (repo
root), GH_TOKEN. Provider credentials (GEMINI_API_KEY, ANTHROPIC_API_KEY) are
read by the underlying model_client. Optional: PR_DIFF_FILE (default
/tmp/pr.diff).
"""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

# Bootstrap sys.path so the packaged import resolves regardless of how the
# script is invoked. Running `python3 scripts/run-fast-review.py` (the shape
# implied by the shebang and the sibling `run-claude-review.py`) puts
# scripts/ on sys.path[0], not the repo root — so `from scripts.model_client`
# would ModuleNotFoundError with name='scripts' even when the sibling module
# is present. Inserting the repo root ahead of it makes both invocation modes
# (`python3 scripts/run-fast-review.py` and `python3 -m scripts.run_fast_review`
# from the repo root) resolve the packaged form the same way.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Sibling PR introduces scripts/model_client.py. Fail loudly with a hint if it
# is not yet on the branch this script is running from — a silent no-op review
# would be worse than a hard error, because the workflow would "green" without
# ever calling a model.
try:
    from scripts.model_client import chat_with_fallback  # type: ignore
except ModuleNotFoundError as exc:
    # Not just "any" ModuleNotFoundError — only the one triggered by the
    # sibling module being absent. Anything else (a broken transitive import
    # inside model_client itself) should propagate untouched so the failure
    # mode is diagnosable in workflow logs.
    if exc.name not in {"scripts", "scripts.model_client", "model_client"}:
        raise
    print(
        "ModuleNotFoundError: install model_client.py first "
        "(sibling PR introduces scripts/model_client.py; this script depends "
        "on scripts.model_client.chat_with_fallback).",
        file=sys.stderr,
    )
    sys.exit(2)

# App-auth helper — same swap the deep reviewer does. Falls back to
# GITHUB_TOKEN when App auth is unavailable so local runs stay usable.
from scripts.gh_app_auth import AppAuthError, get_installation_token  # noqa: E402

# New marker (refactor A: agent-agnostic naming). LEGACY_MARKERS still get
# recognized on comment lookup so a mid-rename sticky is updated in place
# rather than orphaned.
MARKER = "<!-- reviewer:fast -->"
LEGACY_MARKERS = ("<!-- fast-review -->",)
PRIMARY = ("gemini", "gemini-2.0-flash-exp")
FALLBACK = ("anthropic", "claude-opus-5")
MAX_TOKENS = 8000
# Cap the diff we send to the fast pre-pass. Deliberately smaller than the
# deep-review 200KB cap — this pass is meant to be cheap and quick, so an
# oversize diff gets truncated harder here and the deeper reviewer picks up
# whatever the fast pass missed.
MAX_DIFF_BYTES = 100_000

CONTEXT_PATHS = (
    "AGENTS.md",
    "skill/review/SKILL.md",
    "docs/decisions/0009-native-first-helpers-for-recurring-mismatches.md",
    "docs/decisions/0010-helper-naming-and-faithful-patch-mapping.md",
    "docs/decisions/0014-ssim-informational-not-gating.md",
)


def sh(cmd: list[str], *, env: dict[str, str] | None = None) -> str:
    r = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
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
    trunc_block = ""
    if truncated_bytes > 0:
        trunc_block = (
            "\nIMPORTANT — DIFF TRUNCATED: The diff below was truncated at "
            f"{MAX_DIFF_BYTES} bytes ({truncated_bytes} bytes omitted). You "
            "have NOT seen the whole PR. Return `approve=false` and add a P1 "
            "finding at `.github/reviewer` line 1 noting the fast pre-pass "
            "could not see the whole diff.\n"
        )
    return (
        "You are the FAST PRE-PASS reviewer for the swami repository. A deeper "
        "Claude Opus review runs after you — your job is to catch the "
        "low-hanging surface bugs FAST and CHEAP, not to argue architecture.\n\n"
        "FOCUS ON:\n"
        "  - Fake API references (calls to functions/methods that do not exist).\n"
        "  - Syntax issues the compiler will catch but a human reviewer might miss.\n"
        "  - Obvious typos in identifiers, strings, and prose.\n"
        "  - Prose in docs/comments that does not parse or contradicts itself.\n"
        "  - Missing null-checks / obvious off-by-one / trivially wrong constants.\n\n"
        "EXPLICITLY LEAVE FOR THE DEEPER REVIEW:\n"
        "  - Architecture / design smells.\n"
        "  - ADR alignment / methodology contradictions.\n"
        "  - Whether a helper 'should exist' or belongs elsewhere.\n"
        "  - Anything requiring a full read of the repo's decision history.\n\n"
        "Severity taxonomy (aligns with the deeper reviewer so cross-reviewer "
        "tooling can grep a single set of tokens):\n"
        "  P1 = must-fix before merge (broken call, syntax error, wrong constant)\n"
        "  P2 = should-fix (typo in an identifier, comment that misleads)\n"
        "  P3 = nice-to-have (prose polish, minor wording)\n"
        + trunc_block +
        "\nRespond with a SINGLE JSON object and nothing else, matching this shape:\n"
        '{"summary": "<one-sentence read of the PR — brief, this is the fast pass>",'
        ' "findings": [{"severity": "P1"|"P2"|"P3",'
        ' "file": "path/from/repo/root", "line": <int or null>,'
        ' "title": "<short title>",'
        ' "reasoning": "<why — keep it short, this is the fast pass>",'
        ' "suggestion": "<suggested fix, may be empty>"}],'
        ' "approve": <bool — true only when no P1 findings>}\n'
        "If the diff is empty or trivial, return findings=[] and approve=true.\n\n"
        "===== REPO CONTEXT =====\n" + context
    )


def call_model(system: str, diff: str, truncated_bytes: int = 0) -> tuple[dict, str]:
    """Call the fast reviewer, return (parsed_review, provider_that_served).

    `provider_that_served` is either "gemini" (primary hit) or "anthropic"
    (fallback fired) so the sticky comment and workflow log can report which
    tier actually served — that's the signal we use to see how often the free
    tier caps out.
    """
    user_parts: list[str] = []
    if truncated_bytes > 0:
        user_parts.append(
            "## Truncation notice\n\n"
            f"The diff below was truncated at {MAX_DIFF_BYTES} bytes "
            f"({truncated_bytes} bytes omitted). You have NOT seen the whole "
            "PR. Return `approve=false` with a P1 finding at "
            "`.github/reviewer:1` explaining the fast pre-pass could not see "
            "the whole diff."
        )
    user_parts.append("## PR diff\n\n```diff\n" + diff + "\n```")
    user_content = "\n\n".join(user_parts)

    result = chat_with_fallback(
        primary=PRIMARY,
        fallback=FALLBACK,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=MAX_TOKENS,
    )

    # Duck-type the response: model_client may return a dataclass, a dict, or
    # something with attrs. We need `text` and `provider` out of it either way.
    text = _get(result, "text")
    provider = _get(result, "provider") or PRIMARY[0]
    if provider != PRIMARY[0]:
        # Surface fallback events in the workflow log so we can grep for them
        # and see how often the free tier is capping out.
        print(
            f"::warning::gemini rate-limited or errored; served by {provider}",
            file=sys.stderr,
        )
    if not text:
        raise RuntimeError("empty text in model response")
    return _extract_json(text), provider


def _get(obj: object, name: str):
    """Pull a field off either an object with attrs or a dict, tolerantly."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


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


def format_comment(
    review: dict, head_sha: str, provider: str, truncated_bytes: int = 0
) -> str:
    findings = review.get("findings") or []
    approve = bool(review.get("approve"))
    summary = (review.get("summary") or "").strip()
    verdict = "approve" if approve else "request changes"
    lines = [MARKER, "", "## Fast pre-pass review"]
    # Verdict rides on the HEAD line — same one-header pattern the deep
    # reviewer uses so tooling can grep `HEAD:` and pick up the verdict + the
    # provider that served (so fallback events are visible in the PR itself,
    # not just workflow logs).
    head_bits = []
    if head_sha:
        head_bits.append(f"HEAD: `{head_sha}`")
    head_bits.append("fast-review")
    head_bits.append(f"provider: `{provider}`")
    head_bits.append(f"verdict: **{verdict}**")
    lines += [" · ".join(head_bits), ""]
    if truncated_bytes > 0:
        lines += [
            f"> ⚠ diff truncated at {MAX_DIFF_BYTES} bytes "
            f"({truncated_bytes} bytes omitted) — fast pre-pass did not see "
            "the whole change; deeper reviewer will run against the full diff.",
            "",
        ]
    if summary:
        lines += [summary, ""]
    if not findings:
        lines.append("_No findings from the fast pre-pass._")
    else:
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
                title = (f.get("title") or f.get("claim") or "").strip()
                reasoning = (f.get("reasoning") or f.get("evidence") or "").strip()
                suggestion = (f.get("suggestion") or "").strip()
                lines.append(f"- **`{loc}` — [{sev}] {title}**")
                if reasoning:
                    lines.append(f"  - {reasoning}")
                if suggestion:
                    lines.append(f"  - {suggestion}")
            lines.append("")
    lines += [
        "_fast pre-pass — a deeper Claude Opus review runs after this._",
    ]
    return "\n".join(lines)


def find_existing_comment(repo: str, pr: str, env: dict[str, str] | None = None) -> str | None:
    # Same pagination trick as the deep reviewer — let gh do the filtering so a
    # PR with more than one page of comments still parses. Looks for the new
    # marker AND LEGACY_MARKERS so a mid-rename sticky is updated in place
    # rather than orphaned; still bounded to fast-review stickies so the
    # deep-review sticky (`reviewer:claude` / `claude-review`) is untouched.
    markers = (MARKER, *LEGACY_MARKERS)
    contains_clause = " or ".join(
        f'(.body | contains("{m}"))' for m in markers
    )
    out = sh([
        "gh", "api", "--paginate",
        f"repos/{repo}/issues/{pr}/comments",
        "--jq", f'.[] | select({contains_clause}) | .id',
    ], env=env)
    for line in out.splitlines():
        line = line.strip()
        if line:
            return line
    return None


def post_or_update(repo: str, pr: str, body_path: Path, env: dict[str, str] | None = None) -> None:
    existing = find_existing_comment(repo, pr, env=env)
    if existing:
        sh([
            "gh", "api", "--method", "PATCH",
            f"repos/{repo}/issues/comments/{existing}",
            "-F", f"body=@{body_path}",
        ], env=env)
        print(f"updated fast-review comment {existing}")
    else:
        sh(["gh", "pr", "comment", pr, "--body-file", str(body_path)], env=env)
        print("created new fast-review comment")


def _cap_diff(diff: str, limit: int = MAX_DIFF_BYTES) -> tuple[str, int]:
    """Truncate the diff to `limit` bytes if oversize.

    Returns `(diff, omitted_bytes)`. `omitted_bytes > 0` is the truncation
    signal downstream layers (prompt, main-level enforcement, sticky banner)
    key off of. Same defense-in-depth as the deep reviewer.
    """
    raw = diff.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return diff, 0
    kept = raw[:limit].decode("utf-8", errors="replace")
    omitted = len(raw) - limit
    return kept + f"\n\n[diff truncated — {omitted} bytes omitted]\n", omitted


def _post_failure_comment(
    repo: str,
    pr: str,
    head_sha: str,
    exc: BaseException,
    env: dict[str, str] | None = None,
) -> None:
    """Best-effort: post a small marker-tagged failure comment so the PR sees
    the failure instead of a silent workflow-status miss. Never raises."""
    lines = [MARKER, "", "## Fast pre-pass review"]
    if head_sha:
        lines += ["", f"HEAD: `{head_sha}` · fast-review"]
    lines += [
        "",
        "_fast reviewer failed — no findings this run._",
        "",
        f"`{type(exc).__name__}: {exc}`",
        "",
        "See the workflow logs for the full trace. The deeper Claude review "
        "still runs; this comment updates in place on retry.",
    ]
    body = "\n".join(lines)
    try:
        out_path = Path("/tmp/fast-review-body.md")
        out_path.write_text(body)
        post_or_update(repo, pr, out_path, env=env)
    except Exception as post_exc:  # noqa: BLE001
        print(f"could not post failure comment: {post_exc}", file=sys.stderr)


def _resolve_gh_env(repo: str) -> dict[str, str]:
    """Return the env to pass into every `gh` subprocess.

    Prefers the `quibble-review` App installation token (posts as
    `quibble-review[bot]`); falls back to GITHUB_TOKEN when App auth is
    unavailable so local dev / uninstalled forks still work. Fallback logs a
    `::warning` for CI-side visibility.
    """
    env = os.environ.copy()
    try:
        env["GH_TOKEN"] = get_installation_token(repo)
    except AppAuthError as exc:
        print(
            "::warning::quibble-review App auth unavailable; falling back to "
            f"GITHUB_TOKEN ({exc})",
            file=sys.stderr,
        )
        fallback = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if fallback:
            env["GH_TOKEN"] = fallback
    return env


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        print("::error::GITHUB_REPOSITORY not set — required for App auth", file=sys.stderr)
        return 1
    pr = os.environ["PR_NUMBER"]
    head_sha = os.environ.get("HEAD_SHA", "")
    repo_root = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()

    gh_env = _resolve_gh_env(repo)

    diff_path = Path(os.environ.get("PR_DIFF_FILE", "/tmp/pr.diff"))
    diff = diff_path.read_text() if diff_path.exists() else sh(["gh", "pr", "diff", pr], env=gh_env)
    diff, omitted_bytes = _cap_diff(diff)

    system = build_system(load_context(repo_root), truncated_bytes=omitted_bytes)
    try:
        review, provider = call_model(system, diff, truncated_bytes=omitted_bytes)
    except Exception as exc:  # noqa: BLE001
        print(f"fast review failed: {exc}", file=sys.stderr)
        _post_failure_comment(repo, pr, head_sha, exc, env=gh_env)
        return 1

    # Suspenders: never approve a truncated diff, even if the model tried to.
    # Same defense-in-depth pattern as the deep reviewer — the fast pass runs
    # BEFORE the deep pass, so an approve here would prime a positive read for
    # anyone skimming; safer to force request-changes and let the deeper
    # reviewer re-decide on the full diff.
    if omitted_bytes > 0 and bool(review.get("approve")):
        review["approve"] = False
        synthetic = {
            "severity": "P1",
            "file": ".github/reviewer",
            "line": 1,
            "title": "Diff truncated — fast pre-pass cannot approve",
            "reasoning": (
                f"The PR diff exceeded the {MAX_DIFF_BYTES}-byte fast-pass "
                f"review cap ({omitted_bytes} bytes omitted). The fast "
                "pre-pass did not see the whole change and cannot approve. "
                "The deeper Claude review has a larger cap and may still "
                "cover the full diff."
            ),
            "suggestion": (
                "Wait for the deeper Claude review, or split the PR into "
                "smaller topic-scoped PRs so the fast pre-pass can cover it "
                "too."
            ),
        }
        existing = review.get("findings") or []
        review["findings"] = [synthetic] + list(existing)

    body = format_comment(review, head_sha, provider, truncated_bytes=omitted_bytes)
    out_path = Path("/tmp/fast-review-body.md")
    out_path.write_text(body)
    post_or_update(repo, pr, out_path, env=gh_env)
    n = len(review.get("findings") or [])
    print(
        f"posted fast review with {n} finding(s); "
        f"approve={bool(review.get('approve'))}; provider={provider}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
