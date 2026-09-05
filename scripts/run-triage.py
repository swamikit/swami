#!/usr/bin/env python3
"""Claude triage of a newly opened/edited issue.

Fires from `.github/workflows/triage.yml`. Loads the issue payload, the triage
skill and AGENTS.md, an open-issues corpus (for duplicate detection), and asks
Claude to categorize the issue into a fixed label + severity + status
taxonomy. The status decides side effects:

    ready       → add `ready` label (Builder trigger)
    needs-info  → comment asking for the specific missing information
    blocked     → add `blocked` label + comment citing the blocker
    duplicate   → add `duplicate` label + comment naming the suspected dupe

Never edits the issue body. Never closes the issue. Label + comment side
effects only — a human still owns the close decision.

Env: GITHUB_REPOSITORY, GITHUB_EVENT_PATH, ANTHROPIC_API_KEY, GH_TOKEN.
Optional: ISSUE_JSON_FILE (default /tmp/issue.json),
OPEN_ISSUES_FILE (default /tmp/open-issues.json),
CONTEXT_FILE (default /tmp/context.md).
"""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import anthropic

MARKER = "<!-- claude-triage -->"
MODEL = "claude-opus-5"
MAX_TOKENS = 8000

# The label vocabulary the task pins for GA. Anything the model returns outside
# these sets is discarded — labels are load-bearing (Builder gates on `ready`),
# so a hallucinated label must never leak into `gh issue edit --add-label`.
TYPE_LABELS = {
    "type:bug", "type:feat", "type:refactor", "type:docs",
    "type:ci", "type:security", "type:meta",
}
SEVERITY_LABELS = {"P1", "P2", "P3"}
STATUS_VALUES = {"ready", "needs-info", "blocked", "duplicate"}


def sh(cmd: list[str]) -> str:
    r = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return r.stdout


def sh_ok(cmd: list[str]) -> bool:
    """Run a command; return True on exit 0, False otherwise. No raise."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(
            f"cmd failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr}\n"
        )
    return r.returncode == 0


def load_event_issue() -> dict:
    """Read the triggering issue from the GitHub event payload.

    Prefer the workflow-provided /tmp/issue.json (rendered by `gh issue view`
    in triage.yml — same schema every run), fall back to GITHUB_EVENT_PATH's
    `issue` field for local testing / re-invocation off a captured payload.
    """
    override = Path(os.environ.get("ISSUE_JSON_FILE", "/tmp/issue.json"))
    if override.exists():
        return json.loads(override.read_text())
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        raise RuntimeError(
            "no issue payload — set ISSUE_JSON_FILE or GITHUB_EVENT_PATH"
        )
    event = json.loads(Path(event_path).read_text())
    issue = event.get("issue") or {}
    if not issue:
        raise RuntimeError("GITHUB_EVENT_PATH has no `issue` field")
    return issue


def load_open_issues() -> list[dict]:
    """Corpus of open issues for dedup analysis (bounded to 100 in triage.yml)."""
    p = Path(os.environ.get("OPEN_ISSUES_FILE", "/tmp/open-issues.json"))
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def load_context() -> str:
    """AGENTS.md + skill/triage/SKILL.md + ADRs, pre-rendered by triage.yml."""
    p = Path(os.environ.get("CONTEXT_FILE", "/tmp/context.md"))
    if p.exists():
        return p.read_text()
    # Fallback: assemble from repo root if the workflow prep step was skipped
    # (local run, follow-up debug). Same paths triage.yml would have used.
    parts: list[str] = []
    for rel in ("AGENTS.md", "skill/triage/SKILL.md"):
        f = Path(rel)
        if f.exists():
            parts.append(f"===== {rel} =====\n{f.read_text()}")
    return "\n\n".join(parts)


def build_system(context: str) -> str:
    return (
        "You are the Triage GA for the swami repository. Follow the triage "
        "skill below. Read before writing (the open-issue corpus is provided), "
        "prefer the update path over the new-issue path, and be explicit about "
        "duplicates — never guess a dupe number without a concrete match.\n\n"
        "You must classify the issue into these fixed vocabularies:\n"
        f"  type    ∈ {{{', '.join(sorted(TYPE_LABELS))}}}  (exactly one)\n"
        f"  severity ∈ {{P1, P2, P3}}  (exactly one — P1 blocks something real)\n"
        f"  status  ∈ {{ready, needs-info, blocked, duplicate}}  (exactly one)\n\n"
        "Status semantics:\n"
        "  ready       — issue is actionable as written (repro/scope/DoD clear).\n"
        "                Emits the `ready` label which Builder GA gates on.\n"
        "  needs-info  — issue is missing repro / scope / expected behavior.\n"
        "                Provide a specific `comment` asking for what's missing.\n"
        "  blocked     — cannot be worked on until a named blocker resolves.\n"
        "                Provide a `comment` citing the blocker (issue #, PR #,\n"
        "                or external dependency).\n"
        "  duplicate   — matches an open issue in the corpus. Provide the\n"
        "                integer `duplicate_of` (issue number from the corpus)\n"
        "                and a short `comment` naming why it's a dupe.\n\n"
        "Respond with a SINGLE JSON object and nothing else, matching this shape:\n"
        '{"type": "type:bug"|"type:feat"|"type:refactor"|"type:docs"|"type:ci"|"type:security"|"type:meta",'
        ' "severity": "P1"|"P2"|"P3",'
        ' "status": "ready"|"needs-info"|"blocked"|"duplicate",'
        ' "duplicate_of": <int or null — required if status=duplicate>,'
        ' "comment": "<string — required for needs-info/blocked/duplicate, may be empty for ready>",'
        ' "reasoning": "<one-paragraph read of the issue and why these labels>"}'
        "\n\n===== REPO CONTEXT =====\n" + context
    )


def build_user(issue: dict, open_issues: list[dict]) -> str:
    body = issue.get("body") or ""
    title = issue.get("title") or ""
    num = issue.get("number")
    author = (issue.get("author") or {}).get("login") or issue.get("user", {}).get("login") or "?"
    labels = [l.get("name") for l in (issue.get("labels") or []) if isinstance(l, dict)]
    # Slim the corpus to the fields Claude actually needs — full bodies would
    # blow context on a large tracker. Number + title + labels is enough to
    # decide "is this the same failure mode as #N".
    corpus = [
        {
            "number": o.get("number"),
            "title": o.get("title"),
            "labels": [l.get("name") for l in (o.get("labels") or []) if isinstance(l, dict)],
            "url": o.get("url"),
        }
        for o in open_issues
        if o.get("number") != num  # never let the issue self-match
    ]
    return (
        f"## Issue #{num} by @{author}\n\n"
        f"**Title:** {title}\n\n"
        f"**Existing labels:** {labels or '(none)'}\n\n"
        f"**Body:**\n\n{body}\n\n"
        "---\n\n"
        "## Open-issue corpus (dedup candidates)\n\n"
        f"```json\n{json.dumps(corpus, indent=2)}\n```\n"
    )


def call_claude(system: str, user: str) -> dict:
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": user}],
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


def sanitize(decision: dict) -> dict:
    """Coerce Claude's output into the fixed vocabulary; drop stray labels."""
    out: dict = {}
    t = str(decision.get("type") or "").strip()
    out["type"] = t if t in TYPE_LABELS else None
    sev = str(decision.get("severity") or "").strip().upper()
    out["severity"] = sev if sev in SEVERITY_LABELS else None
    st = str(decision.get("status") or "").strip().lower()
    out["status"] = st if st in STATUS_VALUES else None
    dup = decision.get("duplicate_of")
    try:
        out["duplicate_of"] = int(dup) if dup is not None else None
    except (TypeError, ValueError):
        out["duplicate_of"] = None
    out["comment"] = str(decision.get("comment") or "").strip()
    out["reasoning"] = str(decision.get("reasoning") or "").strip()
    return out


def apply_labels(repo: str, issue: int, labels: list[str]) -> None:
    """Add labels one at a time — `gh issue edit --add-label a,b` fails the
    whole batch on the first missing label. Adding singly is idempotent and
    survives a partial vocabulary in the target repo."""
    for name in labels:
        if not name:
            continue
        sh_ok(["gh", "issue", "edit", str(issue),
               "--repo", repo, "--add-label", name])


def post_comment(repo: str, issue: int, body: str) -> None:
    """Post a marker-tagged comment. Idempotency (edit-in-place across
    triage.yml reruns) is deliberately not implemented here — issues events
    fire on `opened` + `edited`, and successive comments carry different
    reasoning (the issue changed). One comment per triage pass is the
    contract; humans can collapse noise if it happens.
    """
    body_path = Path("/tmp/claude-triage-comment.md")
    body_path.write_text(body)
    sh_ok(["gh", "issue", "comment", str(issue),
           "--repo", repo, "--body-file", str(body_path)])


def format_comment(kind: str, decision: dict, extra: str = "") -> str:
    """Marker-tagged comment body. `kind` labels the block so a human skim
    of the thread reads as "Triage: needs-info — <reason>"."""
    reasoning = decision.get("reasoning") or ""
    parts = [MARKER, "", f"## Triage — {kind}", ""]
    if extra:
        parts += [extra, ""]
    if reasoning:
        parts += ["**Reasoning:**", "", reasoning, ""]
    parts += ["_triage skill: `skill/triage/SKILL.md`_"]
    return "\n".join(parts)


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    issue = load_event_issue()
    issue_num = int(issue["number"])
    open_issues = load_open_issues()
    context = load_context()

    system = build_system(context)
    user = build_user(issue, open_issues)

    try:
        raw = call_claude(system, user)
    except Exception as exc:  # noqa: BLE001
        print(f"claude triage failed: {exc}", file=sys.stderr)
        # Best-effort surface so the failure is visible on the issue itself
        # rather than only in the workflow logs.
        post_comment(
            repo, issue_num,
            "\n".join([
                MARKER, "",
                "## Triage — failed",
                "",
                f"`{type(exc).__name__}: {exc}`",
                "",
                "See the workflow logs for the full trace. Retry by editing "
                "the issue (triage.yml fires on `edited` too).",
            ]),
        )
        return 1

    decision = sanitize(raw)
    labels_to_apply: list[str] = []
    if decision["type"]:
        labels_to_apply.append(decision["type"])
    if decision["severity"]:
        labels_to_apply.append(decision["severity"])

    status = decision["status"]
    # Status-specific label additions and comments. Every branch below is
    # independent of the others — a duplicate is still typed and severity'd
    # (so if a human reopens it as non-dupe those labels stand).
    if status == "ready":
        labels_to_apply.append("ready")
    elif status == "blocked":
        labels_to_apply.append("blocked")
    elif status == "duplicate":
        labels_to_apply.append("duplicate")

    apply_labels(repo, issue_num, labels_to_apply)

    if status == "needs-info":
        extra = (
            "**Missing information — please add before this can be picked up:**\n\n"
            f"> {decision['comment'] or '(triage returned no specifics — please expand the issue with a repro, expected vs actual, and scope.)'}"
        )
        post_comment(repo, issue_num, format_comment("needs-info", decision, extra))
    elif status == "blocked":
        extra = (
            "**Blocked by:**\n\n"
            f"> {decision['comment'] or '(triage returned no specifics — please investigate what is holding this back.)'}"
        )
        post_comment(repo, issue_num, format_comment("blocked", decision, extra))
    elif status == "duplicate":
        dup = decision["duplicate_of"]
        if dup:
            extra = (
                f"**Suspected duplicate of #{dup}.**\n\n"
                f"> {decision['comment'] or 'Same failure mode — consolidate discussion there.'}\n\n"
                "_Human gate: close as duplicate only after eyeballing #"
                f"{dup} — Triage does not auto-close._"
            )
        else:
            extra = (
                "**Marked duplicate but Triage could not resolve a target issue number.**\n\n"
                "Please review the open-issue list and either close as dup of the "
                "correct issue or remove the `duplicate` label."
            )
        post_comment(repo, issue_num, format_comment("duplicate", decision, extra))
    elif status == "ready":
        # `ready` deliberately does not comment. The `ready` label is the
        # signal — piling on a "ready!" comment is noise. Builder GA (which
        # fires on the label) will comment on its own when it opens a PR.
        pass

    print(
        f"triaged #{issue_num}: type={decision['type']} sev={decision['severity']} "
        f"status={status} dup_of={decision['duplicate_of']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
