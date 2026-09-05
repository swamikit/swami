#!/usr/bin/env python3
"""Claude review of the current PR, posted as a formal GitHub PR Review.

Refactor B (issue #36): posts findings via the Reviews API — one call creates a
formal Review (APPROVE / REQUEST_CHANGES / COMMENT) with per-finding inline
comments anchored to file:line. That gives branch protection something legally
gate-able (an approving Review), which a sticky ISSUE comment cannot provide.

The summary body still carries the marker `<!-- reviewer:claude -->` and the
`### P1/P2/P3 (N)` count headers so downstream tooling (merge-gate,
audit-p2s.sh) can grep counts without walking each inline comment.

Update semantics: Reviews are timeline entries — they cannot be edited in
place the way an issue comment can. On a new push we DISMISS any prior review
authored by `quibble-review[bot]` (never a human review) and post a fresh one.
Dismissed reviews stay visible in the timeline but no longer count toward
branch protection.

Env: GITHUB_REPOSITORY, PR_NUMBER, HEAD_SHA (opt), GITHUB_WORKSPACE (repo
root), ANTHROPIC_API_KEY, GH_TOKEN. Optional: PR_DIFF_FILE (default
/tmp/pr.diff), STICKY_FILE (default /tmp/sticky.md).
"""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import anthropic

# Bootstrap sys.path so `gh_app_auth` resolves whether invoked as
# `python3 scripts/run-claude-review.py` (scripts/ on sys.path[0]) or
# `python3 -m scripts.run_claude_review` from the repo root. Mirrors the
# sibling run-fast-review.py bootstrap.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# Import the App-auth helper via its script directory too — the module lives
# at scripts/gh_app_auth.py.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from gh_app_auth import AppAuthError, get_installation_token  # noqa: E402

# New marker (refactor A: agent-agnostic naming). LEGACY_MARKERS still get
# recognized on comment lookup so a mid-flight rename doesn't leave orphan
# stickies on open PRs — the sticky flips to the new marker on next update.
MARKER = "<!-- reviewer:claude -->"
LEGACY_MARKERS = ("<!-- claude-review -->",)
# Per-finding marker embedded in each inline PR-review comment. Distinct from
# the summary MARKER so tooling can grep the two independently — the summary
# says "one review was posted"; the per-finding markers say "N findings".
FINDING_MARKER = "<!-- reviewer:claude:finding -->"
# Distinct failure marker on the fallback ISSUE comment we post when the
# Reviews API call fails after retries. Refactor B: the merge-gate needs to
# tell "review failed, retry" apart from "review succeeded with no P1s".
FAILURE_MARKER = "<!-- reviewer:claude-failure -->"
# GitHub App login the App identifies as when it authors reviews. Used to
# filter prior reviews for dismissal — we ONLY ever dismiss reviews authored
# by the bot; human reviews are never touched.
BOT_LOGIN = "quibble-review[bot]"
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
            f"{MAX_DIFF_BYTES} bytes ({truncated_bytes} bytes omitted). A "
            "`[diff truncated — N bytes omitted]` marker appears at the end of "
            "the diff. You have NOT seen the whole PR. Per ADR-0014 (Reviewer "
            "approval is the merge gate) you MUST NOT return `approve=true`. "
            "Return `approve=false` with a P1 finding at "
            "`.github/reviewer` line 1 explaining that the PR must be split or "
            "reviewed manually because the diff exceeds the review cap.\n"
        )
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
        "  P3 = nice-to-have (polish, wording, small refactor)\n"
        + trunc_block +
        "\nRespond with a SINGLE JSON object and nothing else, matching this shape:\n"
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


def call_claude(system: str, diff: str, sticky: str, truncated_bytes: int = 0) -> dict:
    client = anthropic.Anthropic()
    user_parts: list[str] = []
    if truncated_bytes > 0:
        user_parts.append(
            "## Truncation notice\n\n"
            f"The diff below was truncated at {MAX_DIFF_BYTES} bytes "
            f"({truncated_bytes} bytes omitted). You have NOT seen the whole "
            "PR. Per ADR-0014 you MUST return `approve=false` with a P1 "
            "finding at `.github/reviewer:1` saying the PR must be split or "
            "reviewed manually."
        )
    user_parts.append("## PR diff\n\n```diff\n" + diff + "\n```")
    if sticky.strip():
        user_parts.append(
            "## Pixel-gate sticky (read-only context — do NOT propose edits to it)\n\n"
            + sticky
        )
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": "\n\n".join(user_parts)}],
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


def _normalize_findings(findings: list[dict]) -> dict[str, list[dict]]:
    """Sort findings into P1/P2/P3 buckets.

    Legacy severity words (`blocking`/`nit`/`nice-to-have` from older runs)
    fold into P1/P2/P3 respectively; unknown values default to P3 so no
    finding is silently dropped by callers that only iterate the three known
    buckets.
    """
    legacy = {"blocking": "P1", "nit": "P2", "nice-to-have": "P3"}
    buckets: dict[str, list[dict]] = {"P1": [], "P2": [], "P3": []}
    for f in findings:
        raw = str(f.get("severity") or "").strip()
        sev = raw.upper() if raw.upper() in buckets else legacy.get(raw.lower(), "P3")
        buckets[sev].append(f)
    return buckets


def compute_event(review: dict) -> str:
    """Map the model's `approve` bool + P1 count to a Reviews-API event.

    Event mapping (refactor B):
      APPROVE          — `approve is True` AND no P1 findings.
      REQUEST_CHANGES  — any P1 finding exists, OR `approve is False`.
      COMMENT          — everything else: `approve` was neither True nor
                         False (missing / null), and no P1s. Treated as
                         "reviewer took no stance" so branch protection does
                         not consider the review approving OR blocking.
    """
    buckets = _normalize_findings(review.get("findings") or [])
    p1_count = len(buckets["P1"])
    approve = review.get("approve")
    if approve is True and p1_count == 0:
        return "APPROVE"
    if p1_count > 0 or approve is False:
        return "REQUEST_CHANGES"
    return "COMMENT"


def format_review_body(
    review: dict, head_sha: str, truncated_bytes: int = 0,
    unanchored_findings: list[dict] | None = None,
) -> str:
    """Build the summary body posted as the Review's top-level `body`.

    Keeps MARKER + `### P1/P2/P3 (N)` headers so merge-gate / audit-p2s can
    grep counts on the review body without walking each inline comment.
    Anchorable findings ship inline in Files changed; un-anchorable ones
    are appended as `### Unanchored findings` so they still reach the
    reader (see `_format_unanchored_block`).
    """
    findings = review.get("findings") or []
    summary = (review.get("summary") or "").strip()
    event = compute_event(review)
    verdict = {
        "APPROVE": "approve",
        "REQUEST_CHANGES": "request changes",
        "COMMENT": "comment (no verdict)",
    }[event]
    lines = [MARKER, "", "## Claude review"]
    head_bits = []
    if head_sha:
        head_bits.append(f"HEAD: `{head_sha}`")
    head_bits.append(f"verdict: **{verdict}**")
    lines += [" · ".join(head_bits), ""]
    if truncated_bytes > 0:
        # Visible banner so a human reader sees the truncation immediately.
        # Pair with the main()-level enforcement that overrides approve to
        # REQUEST_CHANGES when the diff was truncated (see ADR-0014).
        lines += [
            f"> ⚠ diff truncated at {MAX_DIFF_BYTES} bytes "
            f"({truncated_bytes} bytes omitted) — full review requires "
            "splitting the PR.",
            "",
        ]
    if summary:
        lines += [summary, ""]
    buckets = _normalize_findings(findings)
    total = sum(len(v) for v in buckets.values())
    if total == 0:
        lines.append("_No findings._")
    else:
        # Emit count headers even with zero items so downstream regex greps
        # find `### P1 (0)` predictably. Merge-gate keys off these lines.
        for sev in ("P1", "P2", "P3"):
            lines.append(f"### {sev} ({len(buckets[sev])})")
        lines += ["", "_Findings inline in Files changed._"]
    lines += _format_unanchored_block(unanchored_findings or [])
    lines += ["", "_reviewer skill: `skill/review/SKILL.md`_"]
    return "\n".join(lines)


def _severity_of(f: dict) -> str:
    """Return P1/P2/P3 for a finding, folding legacy words in."""
    raw = str(f.get("severity") or "").strip()
    legacy = {"blocking": "P1", "nit": "P2", "nice-to-have": "P3"}
    return raw.upper() if raw.upper() in {"P1", "P2", "P3"} else legacy.get(raw.lower(), "P3")


def _parse_hunk_right_lines(patch: str) -> set[int]:
    """Return the set of RIGHT-side line numbers referenced in a unified patch.

    Walks each hunk starting from its `@@ -a,b +c,d @@` header, incrementing
    the RIGHT counter on context (` `) and added (`+`) lines, skipping
    removed (`-`) lines (they don't exist on RIGHT). `\\ No newline at end
    of file` meta lines are ignored.

    A line is anchorable on RIGHT if it appears in a hunk as either a
    context line or an added line — those are exactly the positions the
    Reviews API accepts as `side: RIGHT` anchors.
    """
    out: set[int] = set()
    right = 0
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("@@"):
            # Parse the `+c[,d]` field from `@@ -a,b +c,d @@ context`.
            try:
                plus = line.split("+", 1)[1]
                right = int(plus.split(",", 1)[0].split(" ", 1)[0])
            except (IndexError, ValueError):
                in_hunk = False
                continue
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            out.add(right)
            right += 1
        elif line.startswith("-") and not line.startswith("---"):
            # Removed line — not on RIGHT.
            continue
        elif line.startswith("\\"):
            # "\ No newline at end of file" meta — not a real line.
            continue
        else:
            # Context line (leading space, or a blank line inside a hunk).
            out.add(right)
            right += 1
    return out


def get_diff_anchors(
    repo: str, pr: str, env: dict[str, str] | None = None
) -> dict[str, set[int]]:
    """Return `{filename: {anchorable RIGHT line, ...}}` for this PR's diff.

    The formal Reviews API is atomic on POST: one inline comment whose
    `path:line` is outside the diff 422s the WHOLE review, dropping the
    verdict (including any REQUEST_CHANGES the merge-gate depends on). We
    fetch the PR files listing, parse each `patch` field, and hand the
    result to `partition_findings` so we can drop bad anchors before POST
    instead of losing the review to a single hallucinated file:line.

    Files without a `patch` (renames-only, binary, oversize) contribute no
    anchors — findings against them will always route to the body.
    """
    out = sh(
        [
            "gh", "api", "--paginate",
            f"repos/{repo}/pulls/{pr}/files",
        ],
        env=env,
    )
    text = out.strip()
    if not text:
        return {}
    files: list[dict] = []
    # `gh api --paginate` on an array-returning endpoint concatenates pages
    # into a single array. Try that shape first; fall back to line-oriented
    # parsing if a gh variant emits per-page arrays back-to-back.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            files = parsed
        elif isinstance(parsed, dict):
            files = [parsed]
    except json.JSONDecodeError:
        for chunk in text.splitlines():
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                p = json.loads(chunk)
                if isinstance(p, list):
                    files.extend(p)
                elif isinstance(p, dict):
                    files.append(p)
            except json.JSONDecodeError:
                continue
    anchors: dict[str, set[int]] = {}
    for f in files:
        path = f.get("filename")
        patch = f.get("patch")
        if not path or not patch:
            continue
        anchors.setdefault(path, set()).update(_parse_hunk_right_lines(patch))
    return anchors


def partition_findings(
    findings: list[dict], anchors: dict[str, set[int]]
) -> tuple[list[dict], list[dict]]:
    """Split findings into (anchorable, un-anchorable) using the diff anchors.

    A finding is anchorable when it has a `file` + integer `line` AND the
    `(file, line)` pair appears as a valid RIGHT-side anchor in the PR
    diff. Everything else (no line, no file, hallucinated file, line beyond
    the file's changed hunks) routes to the un-anchorable list so it can be
    appended to the review body instead of 422'ing the POST or being
    silently dropped.

    Mirrors the truncation-guard intent in `main()`: the synthetic
    `.github/reviewer` P1 always lands here because that path is never in
    a real PR's diff — so it renders in the body, never inline.
    """
    inline: list[dict] = []
    unanchored: list[dict] = []
    for f in findings:
        path = f.get("file")
        line = f.get("line")
        if not path or line is None:
            unanchored.append(f)
            continue
        try:
            line_int = int(line)
        except (TypeError, ValueError):
            unanchored.append(f)
            continue
        valid = anchors.get(str(path))
        if not valid or line_int not in valid:
            unanchored.append(f)
            continue
        inline.append({**f, "line": line_int})
    return inline, unanchored


def format_review_comments(inline_findings: list[dict]) -> list[dict]:
    """Build the `comments` array for the Reviews API.

    Accepts findings already partitioned by `partition_findings` — every
    entry here IS anchorable. Each becomes a `path`+`line` inline comment
    on the RIGHT side of the diff with the FINDING_MARKER so the audit
    script can grep individual findings out of the review's comment list.
    """
    out: list[dict] = []
    for f in inline_findings:
        path = f.get("file")
        line = f.get("line")
        if not path or line is None:
            # Belt-and-suspenders: partition should have filtered these.
            continue
        sev = _severity_of(f)
        title = (f.get("title") or f.get("claim") or "").strip()
        reasoning = (f.get("reasoning") or f.get("evidence") or "").strip()
        suggestion = (f.get("suggestion") or "").strip()
        body_parts = [f"[{sev}] {title}"]
        if reasoning:
            body_parts += ["", reasoning]
        if suggestion:
            body_parts += ["", f"_suggestion:_ {suggestion}"]
        body_parts += ["", FINDING_MARKER]
        out.append(
            {
                "path": str(path),
                "line": int(line),
                "side": "RIGHT",
                "body": "\n".join(body_parts),
            }
        )
    return out


def _format_unanchored_block(unanchored: list[dict]) -> list[str]:
    """Render un-anchorable findings as a `### Unanchored findings` section.

    Findings appear here when their `(file, line)` isn't in the PR diff
    (hallucinated path, line beyond a hunk, or no line at all — including
    the synthetic truncation P1). Without this section the finding text
    would vanish from the PR entirely: `format_review_comments` drops it
    from the inline set and the summary body only carries bucket counts.
    """
    if not unanchored:
        return []
    lines: list[str] = ["", "### Unanchored findings", ""]
    lines.append(
        "_These findings could not be anchored to a diff line — kept here "
        "so nothing is dropped._"
    )
    lines.append("")
    for f in unanchored:
        sev = _severity_of(f)
        title = (f.get("title") or f.get("claim") or "").strip() or "(no title)"
        path = str(f.get("file") or "").strip()
        line = f.get("line")
        loc = ""
        if path and line is not None:
            loc = f" `{path}:{line}`"
        elif path:
            loc = f" `{path}`"
        lines.append(f"- **[{sev}]{loc}** {title}")
        reasoning = (f.get("reasoning") or f.get("evidence") or "").strip()
        if reasoning:
            lines.append(f"  - {reasoning}")
        suggestion = (f.get("suggestion") or "").strip()
        if suggestion:
            lines.append(f"  - _suggestion:_ {suggestion}")
    return lines


def format_review(
    review: dict, head_sha: str, truncated_bytes: int = 0,
    anchors: dict[str, set[int]] | None = None,
) -> dict:
    """Build the full Reviews-API payload: `{body, event, comments}`.

    This is what `POST /repos/{o}/{r}/pulls/{N}/reviews` accepts as its JSON
    body. Keep the return type a plain dict so callers can json.dumps it
    straight into the API call or a test can inspect the shape without
    parsing markdown.

    `anchors` is `{filename: {RIGHT-line, ...}}` from `get_diff_anchors`.
    When absent (unit test not exercising the API path, or the fetch
    failed) we default to `{}` — every finding routes to un-anchored, no
    inline comments. That's safer than trusting model-supplied `path:line`
    against a diff we haven't checked: one bad anchor 422s the whole POST.
    """
    anchors = anchors if anchors is not None else {}
    all_findings = review.get("findings") or []
    inline_findings, unanchored = partition_findings(all_findings, anchors)
    return {
        "body": format_review_body(
            review, head_sha,
            truncated_bytes=truncated_bytes,
            unanchored_findings=unanchored,
        ),
        "event": compute_event(review),
        "comments": format_review_comments(inline_findings),
    }


def find_prior_reviews(
    repo: str, pr: str, env: dict[str, str] | None = None
) -> list[int]:
    """Return the ids of THIS reviewer's prior reviews on `pr`.

    Two filters are combined — bot login is not enough:

    - `user.login == BOT_LOGIN`: never touch a human review.
    - `body contains MARKER`: the deep and fast reviewers BOTH post as
      `quibble-review[bot]`, so login alone would let each reviewer dismiss
      the other's reviews (last-to-post wins). The MARKER (`<!-- reviewer:claude
      -->` here; `<!-- reviewer:fast -->` in the sibling script) is what
      keeps each script scoped to its own history.

    State filter: only APPROVED and CHANGES_REQUESTED are returned.
    COMMENTED reviews aren't dismiss-able (the dismissals endpoint 422s on
    them) and don't affect branch protection anyway; DISMISSED/PENDING are
    already outside the gate. Filtering here is cheaper than swallowing the
    422 in `dismiss_review`.
    """
    out = sh(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{repo}/pulls/{pr}/reviews",
            "--jq",
            (
                f'.[] | select(.user.login == "{BOT_LOGIN}" '
                f'and (.state == "APPROVED" or .state == "CHANGES_REQUESTED") '
                f'and ((.body // "") | contains("{MARKER}"))) | .id'
            ),
        ],
        env=env,
    )
    ids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                ids.append(int(line))
            except ValueError:
                continue
    return ids


def dismiss_review(
    repo: str,
    pr: str,
    review_id: int,
    message: str,
    env: dict[str, str] | None = None,
) -> None:
    """PUT /repos/.../pulls/{N}/reviews/{id}/dismissals with a short message.

    Only the bot's own reviews are dismissed — the caller (`main`) filters
    for `user.login == BOT_LOGIN` via `find_prior_reviews`. A dismissed
    review stays in the timeline (so history is visible) but no longer
    satisfies / blocks branch protection.
    """
    payload = json.dumps({"message": message, "event": "DISMISS"})
    subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/pulls/{pr}/reviews/{review_id}/dismissals",
            "-X",
            "PUT",
            "--input",
            "-",
        ],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )


def post_review(
    repo: str,
    pr: str,
    payload: dict,
    env: dict[str, str] | None = None,
) -> dict:
    """POST a new PR review with body + event + inline comments atomically.

    One call creates the Review timeline entry AND all its inline comments.
    Returns the parsed API response so the caller can log the new review id.
    """
    body_json = json.dumps(payload)
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/pulls/{pr}/reviews",
            "-X",
            "POST",
            "--input",
            "-",
        ],
        input=body_json,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"POST /pulls/{pr}/reviews failed (rc={result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def _cap_diff(diff: str, limit: int = MAX_DIFF_BYTES) -> tuple[str, int]:
    """Truncate the diff to `limit` bytes if oversize.

    Returns `(diff, omitted_bytes)` — `omitted_bytes == 0` means the caller
    saw the whole diff. `omitted_bytes > 0` is the truncation signal every
    downstream layer (prompt, main-level enforcement, sticky banner) keys
    off of; per ADR-0014 an approve verdict on a truncated diff is a false
    green because the Reviewer read IS the merge gate.

    NOTE: return type is `tuple[str, int]`, not `str`. `main()` is the only
    caller inside this module (grep `_cap_diff` — nothing else imports it),
    but if you add a caller elsewhere, remember to unpack both values or the
    truncation signal will silently vanish.
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
    """Best-effort: post a small marker-tagged ISSUE comment so the PR sees the
    failure instead of a silent workflow-status miss. Never raises — a broken
    poster should not compound the original error.

    Uses FAILURE_MARKER (distinct from MARKER) so the merge-gate can tell
    "review failed, retry" apart from "review succeeded with no P1s". Falls
    back to an issue comment (not a Review) because Review posting is what
    just failed; retrying that here would likely re-fail for the same reason.
    """
    lines = [FAILURE_MARKER, "", "## Claude review"]
    if head_sha:
        lines += ["", f"HEAD: `{head_sha}`"]
    lines += [
        "",
        "_reviewer failed — no findings this run._",
        "",
        f"`{type(exc).__name__}: {exc}`",
        "",
        "See the workflow logs for the full trace. A retry will post a new "
        "review (and this comment stays as history).",
    ]
    body = "\n".join(lines)
    try:
        out_path = Path("/tmp/claude-review-failure.md")
        out_path.write_text(body)
        subprocess.run(
            ["gh", "pr", "comment", pr, "--body-file", str(out_path)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except Exception as post_exc:  # noqa: BLE001
        print(f"could not post failure comment: {post_exc}", file=sys.stderr)


def _resolve_gh_env(repo: str) -> dict[str, str]:
    """Return the env to pass into every `gh` subprocess.

    Prefers the `quibble-review` App installation token so review comments post
    as `quibble-review[bot]`. Falls back to `GITHUB_TOKEN` when App auth is
    unavailable (missing secrets in local dev, or the App is not yet installed
    on a fork) so the script stays runnable — a fallback logs a `::warning`
    that CI surfaces on the run page.
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

    sticky_path = Path(os.environ.get("STICKY_FILE", "/tmp/sticky.md"))
    sticky = sticky_path.read_text() if sticky_path.exists() else ""

    system = build_system(load_context(repo_root), truncated_bytes=omitted_bytes)
    try:
        review = call_claude(system, diff, sticky, truncated_bytes=omitted_bytes)
    except Exception as exc:  # noqa: BLE001
        print(f"claude review failed: {exc}", file=sys.stderr)
        _post_failure_comment(repo, pr, head_sha, exc, env=gh_env)
        return 1

    # Suspenders: even with the prompt telling the model not to approve a
    # truncated diff, we do not trust the model on a merge-gate question.
    # If the diff was truncated AND the model still returned approve=true,
    # override to false and prepend a synthetic P1 finding using the same
    # schema the render loop expects. Any existing findings are preserved.
    #
    # `file: null, line: null` deliberately: the truncation P1 is a review-
    # meta finding, not tied to any file in the diff, so it MUST land in
    # the body's `### Unanchored findings` section — never as an inline
    # comment. An earlier draft anchored it to `.github/reviewer:1`, a
    # path that was never in the diff; the Reviews API 422'd the whole
    # POST for that reason, dropping the very REQUEST_CHANGES verdict
    # ADR-0014 says must block. Keep line=None to preserve body-routing
    # even if the anchor lookup later returns something unexpected.
    if omitted_bytes > 0 and bool(review.get("approve")):
        review["approve"] = False
        synthetic = {
            "severity": "P1",
            "file": None,
            "line": None,
            "title": "Diff truncated — cannot approve",
            "reasoning": (
                f"The PR diff exceeded the {MAX_DIFF_BYTES}-byte review cap "
                f"({omitted_bytes} bytes omitted), so the reviewer did not "
                "see the whole change. Under ADR-0014 the Reviewer read is "
                "the merge gate; approving on a partial diff is a false "
                "green. Split the PR into smaller changes or route it to a "
                "manual reviewer."
            ),
            "suggestion": (
                "Follow the escape-hatch procedure in `skill/review/SKILL.md` "
                "under \"When the diff exceeds the reviewer cap\": (a) split "
                "the PR into smaller topic-scoped PRs that fit under the diff "
                "cap; or (b) if it's one-pattern-one-PR with unavoidable "
                "size, do a manual full-diff review (generated Swift + IR "
                "included — those are the shipped pattern, not vendored "
                "noise) and merge manually with an explicit rebuttal "
                "comment. Do not filter generated paths out of the diff to "
                "get under the cap."
            ),
        }
        existing = review.get("findings") or []
        review["findings"] = [synthetic] + list(existing)

    # Fetch the diff's anchorable `(file, RIGHT-line)` pairs so we can drop
    # hallucinated anchors before POST — one bad anchor 422s the whole
    # review. On fetch failure we log and continue with an empty anchor
    # set: every finding routes to the body's `### Unanchored findings`,
    # the POST still lands with body + event (esp. REQUEST_CHANGES), and
    # no finding text is lost.
    try:
        anchors = get_diff_anchors(repo, pr, env=gh_env)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::could not fetch diff anchors: {exc}", file=sys.stderr)
        anchors = {}

    payload = format_review(review, head_sha, truncated_bytes=omitted_bytes, anchors=anchors)

    # Dismiss any prior review authored by the bot BEFORE posting the new one.
    # Order matters: if a prior REQUEST_CHANGES review is still standing when
    # the new APPROVE lands, branch protection will still see the block. Only
    # the bot's own reviews are ever touched — filter is in find_prior_reviews.
    try:
        prior_ids = find_prior_reviews(repo, pr, env=gh_env)
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: a failed listing means we'll post an additional review,
        # not the wrong review. Log and continue.
        print(f"::warning::could not list prior reviews: {exc}", file=sys.stderr)
        prior_ids = []
    for rid in prior_ids:
        try:
            dismiss_review(
                repo,
                pr,
                rid,
                "Superseded by a newer quibble-review run.",
                env=gh_env,
            )
            print(f"dismissed prior review {rid}")
        except Exception as exc:  # noqa: BLE001
            # A dismissal failure is not fatal — the new review still posts.
            # Log so a manual sweep can see it.
            print(f"::warning::could not dismiss review {rid}: {exc}", file=sys.stderr)

    try:
        result = post_review(repo, pr, payload, env=gh_env)
    except Exception as exc:  # noqa: BLE001
        print(f"claude reviews-API post failed: {exc}", file=sys.stderr)
        _post_failure_comment(repo, pr, head_sha, exc, env=gh_env)
        return 1

    n = len(review.get("findings") or [])
    inline = len(payload["comments"])
    review_id = result.get("id", "?")
    print(
        f"posted review {review_id} with {n} finding(s) ({inline} inline); "
        f"event={payload['event']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
