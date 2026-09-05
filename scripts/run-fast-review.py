#!/usr/bin/env python3
"""Fast pre-pass PR review, posted as a formal GitHub PR Review.

This is the cheap Gemini 2.0 Flash pre-pass that runs *before* the deeper
Claude Opus review (`run-claude-review.py`). It surfaces surface bugs, fake
API references, obvious typos, and prose that doesn't parse — the low-hanging
finds — so the deeper reviewer can focus on architecture / ADR alignment.

Coordination points:
- Uses `scripts.model_client.chat_with_fallback` (introduced in a sibling PR).
  If that module is not yet on the branch this script runs from, the import
  fails LOUDLY with an install hint instead of silently no-op'ing.
- Uses a distinct summary marker (`<!-- reviewer:fast -->`) and per-finding
  marker (`<!-- reviewer:fast:finding -->`) so it never fights with the
  deep-review markers.
- Finding schema mirrors run-claude-review.py (P1/P2/P3, {file, line, severity,
  title, reasoning, suggestion}) so cross-reviewer tooling stays happy.

Refactor B (issue #36): posts findings via the Reviews API — one call creates
a formal Review (APPROVE / REQUEST_CHANGES / COMMENT) with per-finding inline
comments anchored to file:line, dismissing any prior review the bot authored
first. See run-claude-review.py for the full rationale.

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
# Per-finding marker on each inline PR-review comment. Distinct from the
# summary marker so tooling can grep the two independently.
FINDING_MARKER = "<!-- reviewer:fast:finding -->"
# Distinct failure marker on the fallback ISSUE comment posted when the
# Reviews API call fails. Merge-gate distinguishes "review failed" from
# "review succeeded with no P1s".
FAILURE_MARKER = "<!-- reviewer:fast-failure -->"
# Sentinel `path` we tell the model to use when it wants to file a P1 that
# isn't tied to a real file in the diff (currently only the truncation P1).
# URL-scheme-style so it can't collide with any real repo path — an earlier
# form (`.github/reviewer`) collided with the real file `.github/reviewers.yml`
# once that was added, tripping `_assert_no_synthetic_paths_in_comments` and
# blocking every review on PRs that touched it. Any comment carrying this
# exact path is a routing bug; the assertion below catches that regression
# before it reaches the Reviews API.
SYNTHETIC_TRUNCATION_PATH = "quibble-review://truncation"
# App login the bot identifies as when it authors reviews. Filter for prior
# reviews we can dismiss — never touch a human review.
BOT_LOGIN = "quibble-review[bot]"
# quibble is preferred; github-actions is our documented fallback when App
# auth is unavailable. `_resolve_gh_env` falls back to GITHUB_TOKEN when the
# App install is missing or JWT signing fails — reviews posted under that
# token are authored by `github-actions[bot]`. If `find_prior_reviews` only
# matched `quibble-review[bot]`, a fallback-authored CHANGES_REQUESTED would
# never get dismissed and could keep blocking merge after App auth is
# restored. Combined with the MARKER body check, matching either identity
# keeps us scoped to reviews THIS script actually posted.
SUPPORTED_BOT_IDENTITIES = ("quibble-review[bot]", "github-actions[bot]")
PRIMARY = ("gemini", "gemini-2.0-flash-exp")
FALLBACK = ("anthropic", "claude-opus-5")
MAX_TOKENS = 8000
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["P1", "P2", "P3"]},
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "title": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["severity", "file", "title", "reasoning", "suggestion"],
            },
        },
        "approve": {"type": "boolean"},
    },
    "required": ["summary", "findings", "approve"],
}
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
            f"finding at `{SYNTHETIC_TRUNCATION_PATH}` line 1 noting the fast "
            "pre-pass could not see the whole diff.\n"
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
            f"`{SYNTHETIC_TRUNCATION_PATH}:1` explaining the fast pre-pass "
            "could not see the whole diff."
        )
    user_parts.append("## PR diff\n\n```diff\n" + diff + "\n```")
    user_content = "\n\n".join(user_parts)

    # model_client returns (reply_or_validated_value, provider_used). With the
    # validate hook below, the first element is the parsed review object.
    # Unpack it directly; treating the tuple like an object makes every
    # successful response look empty and prevents this worker from ever
    # reaching the Reviews API (issue #89).
    review, provider = chat_with_fallback(
        primary=PRIMARY,
        fallback=FALLBACK,
        system=system,
        user=user_content,
        max_tokens=MAX_TOKENS,
        schema=REVIEW_SCHEMA,
        validate=_extract_json,
    )
    if provider != PRIMARY[0]:
        # Surface fallback events in the workflow log so we can grep for them
        # and see how often the free tier is capping out.
        print(
            f"::warning::gemini rate-limited or errored; served by {provider}",
            file=sys.stderr,
        )
    return review, provider


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
    """Bucket findings into P1/P2/P3, folding legacy severity words in."""
    legacy = {"blocking": "P1", "nit": "P2", "nice-to-have": "P3"}
    buckets: dict[str, list[dict]] = {"P1": [], "P2": [], "P3": []}
    for f in findings:
        raw = str(f.get("severity") or "").strip()
        sev = raw.upper() if raw.upper() in buckets else legacy.get(raw.lower(), "P3")
        buckets[sev].append(f)
    return buckets


def compute_event(review: dict) -> str:
    """Fast pre-pass is advisory only — always returns COMMENT.

    Codex P1 round 2: both the fast pre-pass and the deep Claude review post
    as the same App identity (`quibble-review[bot]`), so branch protection
    cannot tell them apart. If the fast pre-pass emitted `APPROVE`, that
    verdict would count toward merge-eligibility during the ~60s gap before
    the deep reviewer lands — and would stay approving if the deep pass
    failed entirely. Symmetrically, a fast `REQUEST_CHANGES` would block
    even when the deep reviewer disagrees.

    Fix: the fast pre-pass NEVER submits a binding verdict. All fast reviews
    ship as COMMENT (no stance for branch protection). Only the deep
    reviewer's `compute_event` (in `run-claude-review.py`) may emit APPROVE
    or REQUEST_CHANGES. The `review` argument is intentionally unused — the
    approve/P1 signal still surfaces in the body's bucket headers and in
    inline finding comments, just not as a gate-able Reviews-API event.
    """
    del review  # advisory only — see docstring
    return "COMMENT"


def format_review_body(
    review: dict, head_sha: str, provider: str, truncated_bytes: int = 0,
    unanchored_findings: list[dict] | None = None,
) -> str:
    """Build the summary body posted as the Review's top-level `body`.

    Preserves MARKER + `### P1/P2/P3 (N)` count headers so downstream tooling
    (merge-gate, audit-p2s.sh) can grep counts. Provider stays on the HEAD
    line so fast-pass fallback events (gemini → anthropic) surface on the PR.
    """
    findings = review.get("findings") or []
    summary = (review.get("summary") or "").strip()
    event = compute_event(review)
    verdict = {
        "APPROVE": "approve",
        "REQUEST_CHANGES": "request changes",
        "COMMENT": "comment (no verdict)",
    }[event]
    lines = [MARKER, "", "## Fast pre-pass review"]
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
    buckets = _normalize_findings(findings)
    total = sum(len(v) for v in buckets.values())
    if total == 0:
        lines.append("_No findings from the fast pre-pass._")
    else:
        # Always emit all three count headers so downstream regex greps find
        # them predictably (merge-gate keys off these).
        for sev in ("P1", "P2", "P3"):
            lines.append(f"### {sev} ({len(buckets[sev])})")
        lines += ["", "_Findings inline in Files changed._"]
    lines += _format_unanchored_block(unanchored_findings or [])
    lines += [
        "",
        "_fast pre-pass — a deeper Claude Opus review runs after this._",
    ]
    return "\n".join(lines)


def _severity_of(f: dict) -> str:
    """Return P1/P2/P3 for a finding, folding legacy severity words in."""
    raw = str(f.get("severity") or "").strip()
    legacy = {"blocking": "P1", "nit": "P2", "nice-to-have": "P3"}
    return raw.upper() if raw.upper() in {"P1", "P2", "P3"} else legacy.get(raw.lower(), "P3")


def _parse_hunk_right_lines(patch: str) -> set[int]:
    """Return the set of RIGHT-side line numbers referenced in a unified patch.

    Walks each hunk from its `@@ -a,b +c,d @@` header, incrementing the
    RIGHT counter on context (` `) and added (`+`) lines and skipping
    removed (`-`) lines. `\\ No newline at end of file` meta ignored.

    A line is anchorable on RIGHT if it appears in a hunk as either a
    context line or an added line — those are exactly the positions the
    Reviews API accepts as `side: RIGHT` anchors.
    """
    return _parse_hunk_sided_lines(patch)["RIGHT"]


def _parse_hunk_sided_lines(patch: str) -> dict[str, set[int]]:
    """Return `{"RIGHT": {lines}, "LEFT": {lines}}` for a unified patch.

    Codex P1 round 2: the Reviews API distinguishes `side: RIGHT` (post-
    change file — additions and context) from `side: LEFT` (pre-change
    file — deletions and context). Posting a finding on a deleted line
    with `side: RIGHT` 422s the whole atomic review; symmetric for LEFT.

    Walk each hunk from its `@@ -a,b +c,d @@` header:
      - Context (` `): exists on BOTH sides — advance both counters.
      - Added (`+`): RIGHT only — advance RIGHT.
      - Removed (`-`): LEFT only — advance LEFT.
    `\\ No newline at end of file` meta is ignored on both sides.
    """
    right_out: set[int] = set()
    left_out: set[int] = set()
    right = 0
    left = 0
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("@@"):
            try:
                minus_field = line.split("-", 1)[1].split(" ", 1)[0]
                left = int(minus_field.split(",", 1)[0])
                plus_field = line.split("+", 1)[1].split(" ", 1)[0]
                right = int(plus_field.split(",", 1)[0])
            except (IndexError, ValueError):
                in_hunk = False
                continue
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            right_out.add(right)
            right += 1
        elif line.startswith("-") and not line.startswith("---"):
            left_out.add(left)
            left += 1
        elif line.startswith("\\"):
            continue
        else:
            right_out.add(right)
            left_out.add(left)
            right += 1
            left += 1
    return {"RIGHT": right_out, "LEFT": left_out}


def get_diff_anchors(
    repo: str, pr: str, env: dict[str, str] | None = None
) -> dict[str, dict[str, set[int]]]:
    """Return `{filename: {"RIGHT": {lines}, "LEFT": {lines}}}` per PR file.

    Codex P1 round 2: the Reviews API is atomic on POST and rejects a
    comment whose `side` doesn't match the side the line actually lives
    on (deleted line with `side: RIGHT` = 422). We return both sides so
    `partition_findings` can pick the correct `side` per finding.

    Legacy `dict[str, set[int]]` (RIGHT-only) callers are handled by
    `_resolve_side` in `partition_findings` — no callsite breakage.
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
    anchors: dict[str, dict[str, set[int]]] = {}
    for f in files:
        path = f.get("filename")
        patch = f.get("patch")
        if not path or not patch:
            continue
        sided = _parse_hunk_sided_lines(patch)
        bucket = anchors.setdefault(path, {"RIGHT": set(), "LEFT": set()})
        bucket["RIGHT"].update(sided["RIGHT"])
        bucket["LEFT"].update(sided["LEFT"])
    return anchors


def _resolve_side(entry: object, line_int: int) -> str | None:
    """Return "RIGHT", "LEFT", or None for a `(anchor entry, line)` pair.

    Accepts BOTH the new sided shape (`{"RIGHT": {lines}, "LEFT": {lines}}`)
    and the legacy RIGHT-only set for callers that predate P1 round 2.
    Prefers RIGHT because additions + context both live there — LEFT is
    picked only for a line that exists on LEFT but not RIGHT (i.e. a
    removed line).
    """
    if isinstance(entry, dict):
        right = entry.get("RIGHT") or set()
        left = entry.get("LEFT") or set()
        if line_int in right:
            return "RIGHT"
        if line_int in left:
            return "LEFT"
        return None
    if isinstance(entry, set):
        return "RIGHT" if line_int in entry else None
    return None


def partition_findings(
    findings: list[dict],
    anchors: dict[str, dict[str, set[int]]] | dict[str, set[int]],
) -> tuple[list[dict], list[dict]]:
    """Split findings into (anchorable, un-anchorable) using the diff anchors.

    Anchorable = has `file` + integer `line` AND that `(file, line)` pair
    appears on either side of the PR diff. The picked side is stored on
    the finding as `_side` so `format_review_comments` posts it with the
    correct `side` field (RIGHT for additions/context, LEFT for
    deletions). Codex P1 round 2 — mismatched `side` 422s the whole
    atomic POST.

    Everything else (missing line, hallucinated path, line outside every
    hunk, or the synthetic truncation P1 with `file: null`) routes to
    un-anchorable so it can be appended to the review body.
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
        entry = anchors.get(str(path))
        if entry is None:
            unanchored.append(f)
            continue
        side = _resolve_side(entry, line_int)
        if side is None:
            unanchored.append(f)
            continue
        inline.append({**f, "line": line_int, "_side": side})
    return inline, unanchored


def format_review_comments(inline_findings: list[dict]) -> list[dict]:
    """Per-finding inline comments for the Reviews API.

    Accepts findings already partitioned by `partition_findings` — every
    entry carries `_side` (RIGHT/LEFT). Emits `path`+`line`+`side` inline
    comments with FINDING_MARKER for grep-ability.
    """
    out: list[dict] = []
    for f in inline_findings:
        path = f.get("file")
        line = f.get("line")
        if not path or line is None:
            # Belt-and-suspenders: partition should have filtered these.
            continue
        side = str(f.get("_side") or "RIGHT")
        if side not in {"RIGHT", "LEFT"}:
            side = "RIGHT"
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
                "side": side,
                "body": "\n".join(body_parts),
            }
        )
    return out


def _format_unanchored_block(unanchored: list[dict]) -> list[str]:
    """Render un-anchorable findings as a `### Unanchored findings` section.

    Without this section a finding the model tied to a file/line outside
    the diff would vanish: `format_review_comments` drops it and the
    summary only carries bucket counts. Keep the text on the PR.
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
    review: dict, head_sha: str, provider: str, truncated_bytes: int = 0,
    anchors: dict[str, dict[str, set[int]]] | dict[str, set[int]] | None = None,
) -> dict:
    """Full Reviews-API payload: `{body, event, comments}`.

    `anchors` accepts the sided shape
    (`{filename: {"RIGHT": {lines}, "LEFT": {lines}}}`) or the legacy
    RIGHT-only shape (`{filename: {lines}}`). `partition_findings`
    disambiguates transparently.

    When `anchors` is absent (unit-test path or fetch failure) defaults
    to `{}` — everything routes to the body's `### Unanchored findings`,
    no inline comments. Safer than trusting model-supplied `path:line`
    values against a diff we haven't checked: one bad anchor 422s the
    whole POST.
    """
    anchors = anchors if anchors is not None else {}
    all_findings = review.get("findings") or []
    inline_findings, unanchored = partition_findings(all_findings, anchors)
    return {
        "body": format_review_body(
            review, head_sha, provider,
            truncated_bytes=truncated_bytes,
            unanchored_findings=unanchored,
        ),
        "event": compute_event(review),
        "comments": format_review_comments(inline_findings),
    }


def find_prior_reviews(
    repo: str, pr: str, env: dict[str, str] | None = None
) -> list[int]:
    """IDs of THIS reviewer's prior reviews on `pr`.

    Two filters combined — bot identity alone is not enough:

    - `user.login` is in SUPPORTED_BOT_IDENTITIES: never touch human
      reviews. The set includes both the preferred App identity
      (`quibble-review[bot]`) AND the documented fallback identity
      (`github-actions[bot]`) that `_resolve_gh_env` produces when App
      auth is unavailable. Without the fallback identity, a
      CHANGES_REQUESTED review posted under GITHUB_TOKEN would never be
      dismissed and could keep blocking merge forever after App auth is
      restored.
    - `body contains MARKER` (`<!-- reviewer:fast -->` here): the fast
      pre-pass and the deep reviewer BOTH post as `quibble-review[bot]`
      (and both fall back to `github-actions[bot]` the same way), so
      identity-only would let each dismiss the other's reviews. MARKER
      keeps each script scoped to its own history — and also keeps this
      filter from touching any OTHER workflow's `github-actions[bot]`
      reviews.

    State filter: only APPROVED / CHANGES_REQUESTED — those are the only
    gate-able states, and the only ones the dismissals endpoint accepts
    (COMMENTED reviews 422 on dismiss). DISMISSED/PENDING are already
    outside the gate.
    """
    # jq array of supported identities; select if .user.login is in it.
    # `.user.login as $l` binds the login BEFORE the array pipeline —
    # otherwise `index(.user.login)` runs against the array as `.` and
    # errors with "Cannot index array with string 'user'".
    identities_json = json.dumps(list(SUPPORTED_BOT_IDENTITIES))
    out = sh(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{repo}/pulls/{pr}/reviews",
            "--jq",
            (
                f'.[] | select((.user.login as $l | {identities_json} '
                f'| index($l)) '
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
    """PUT /pulls/{N}/reviews/{id}/dismissals with an explanatory message.

    Dismissed reviews remain visible in the timeline but no longer count for
    branch protection. Only the bot's own reviews are dismissed — the caller
    filters via `find_prior_reviews`.
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
    """POST a new PR review (body + event + inline comments) atomically."""
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
    """Best-effort: post a small marker-tagged ISSUE comment so the PR sees
    the failure instead of a silent workflow-status miss. Never raises.

    Uses FAILURE_MARKER (distinct from MARKER) so the merge-gate can tell
    "review failed, retry" apart from "review succeeded with no P1s". Falls
    back to an issue comment because the Reviews API call is what just
    failed — retrying it here would likely re-fail for the same reason.
    """
    lines = [FAILURE_MARKER, "", "## Fast pre-pass review"]
    if head_sha:
        lines += ["", f"HEAD: `{head_sha}` · fast-review"]
    lines += [
        "",
        "_fast reviewer failed — no findings this run._",
        "",
        f"`{type(exc).__name__}: {exc}`",
        "",
        "See the workflow logs for the full trace. The deeper Claude review "
        "still runs; a retry will post a new review (this comment stays as history).",
    ]
    body = "\n".join(lines)
    try:
        out_path = Path("/tmp/fast-review-failure.md")
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


def fetch_current_head_sha(
    repo: str, pr: str, env: dict[str, str] | None = None
) -> str:
    """Return the current HEAD SHA of `pr` via `gh pr view`.

    Codex P1 round 2 — mirrors the deep reviewer's helper. Two review.yml
    runs can be in flight after rapid pushes; call this immediately
    before POST and abort when the fetched SHA differs from the SHA we've
    been reviewing.

    Returns an empty string on any error — the caller treats "cannot
    verify" as "proceed" so a fetch-failure loop can't silence reviews.
    """
    try:
        out = sh(
            [
                "gh", "pr", "view", pr,
                "--repo", repo,
                "--json", "commits",
                "--jq", ".commits | last | .oid",
            ],
            env=env,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"::warning::could not fetch current PR HEAD for staleness check: {exc}",
            file=sys.stderr,
        )
        return ""
    return out.strip()


def _assert_no_synthetic_paths_in_comments(comments: list[dict]) -> None:
    """Raise if any comment carries the `SYNTHETIC_TRUNCATION_PATH` anchor.

    The truncation-guard P1 is built with `file=None, line=None` so it
    routes to the body's Unanchored section. If a future refactor ever
    re-anchors it to `SYNTHETIC_TRUNCATION_PATH:1`, the atomic POST
    would 422 (path never in a real diff) and drop the entire verdict.
    This guard catches that regression before it reaches the API.

    Match is EXACT against the sentinel string, not a prefix — an earlier
    `startswith(".github/reviewer")` check collided with the real file
    `.github/reviewers.yml` once that landed, tripping the assertion on
    every legitimate finding against that file.
    """
    for c in comments:
        path = str(c.get("path") or "")
        if path == SYNTHETIC_TRUNCATION_PATH:
            raise RuntimeError(
                f"pre-POST safety check: synthetic path in comments — {path!r}. "
                "A truncation-guard finding leaked past partition_findings; "
                "this would 422 the whole Reviews-API POST."
            )


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
        # `file: null, line: null` deliberately — the truncation P1 is a
        # review-meta finding, not tied to any file in the diff, so it
        # MUST land in `### Unanchored findings` in the body, never as an
        # inline comment. An earlier draft anchored it to a real-looking
        # path like `.github/reviewer:1`, a path never in a real diff; the
        # Reviews API 422'd the whole POST and dropped the REQUEST_CHANGES
        # verdict along with it. `SYNTHETIC_TRUNCATION_PATH` above is the
        # sentinel we tell the model to use; the assertion below catches
        # any leak of that exact path into `comments`.
        synthetic = {
            "severity": "P1",
            "file": None,
            "line": None,
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

    # Fetch anchorable `(file, RIGHT-line)` pairs before formatting so
    # hallucinated `path:line` values from the fast model get routed to
    # the body's `### Unanchored findings` instead of 422'ing the POST.
    # On fetch failure we log and continue with an empty anchor set —
    # everything routes to unanchored, the POST still lands with body +
    # event, no finding text lost.
    try:
        anchors = get_diff_anchors(repo, pr, env=gh_env)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::could not fetch diff anchors: {exc}", file=sys.stderr)
        anchors = {}

    payload = format_review(
        review, head_sha, provider,
        truncated_bytes=omitted_bytes, anchors=anchors,
    )

    # Codex P1 round 2: pin the Review to the SHA we actually reviewed
    # (`commit_id`) so a late-finishing stale run can't have its verdict
    # recorded against a newer HEAD. Fast pre-pass never emits APPROVE
    # (see `compute_event`), but pinning still keeps the review row
    # accurate for humans reading the timeline.
    reviewed_sha = head_sha or os.environ.get("GITHUB_SHA", "")
    if reviewed_sha:
        payload["commit_id"] = reviewed_sha

    # Pre-POST safety check: a synthetic `SYNTHETIC_TRUNCATION_PATH` anchor
    # would 422 the whole atomic review.
    _assert_no_synthetic_paths_in_comments(payload.get("comments") or [])

    # Codex P1 round 2: reject stale runs. If HEAD has advanced since the
    # fast reviewer started, abort — the newer run will handle the current
    # state. Exit 0 (not an error) because stale-run abort is expected.
    if reviewed_sha:
        current_sha = fetch_current_head_sha(repo, pr, env=gh_env)
        if current_sha and current_sha != reviewed_sha:
            print(
                f"::warning::HEAD advanced during review "
                f"(reviewed={reviewed_sha}, current={current_sha}); "
                "another run will handle current state",
                file=sys.stderr,
            )
            return 0

    # Dismiss any prior bot-authored review BEFORE posting the new one — a
    # standing REQUEST_CHANGES review from the previous push would keep
    # branch-protection blocking even after a fresh APPROVE lands.
    try:
        prior_ids = find_prior_reviews(repo, pr, env=gh_env)
    except Exception as exc:  # noqa: BLE001
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
            print(f"::warning::could not dismiss review {rid}: {exc}", file=sys.stderr)

    try:
        result = post_review(repo, pr, payload, env=gh_env)
    except Exception as exc:  # noqa: BLE001
        print(f"fast reviews-API post failed: {exc}", file=sys.stderr)
        _post_failure_comment(repo, pr, head_sha, exc, env=gh_env)
        return 1

    n = len(review.get("findings") or [])
    inline = len(payload["comments"])
    review_id = result.get("id", "?")
    print(
        f"posted fast review {review_id} with {n} finding(s) ({inline} inline); "
        f"event={payload['event']}; provider={provider}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
