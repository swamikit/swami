#!/usr/bin/env python3
"""Builder pickup for `ready`-labeled issues.

Fires from `.github/workflows/builder.yml`'s `ready` job. The issue body is
the spec. This script asks Claude for a plan (files to write / edit + commit
message + PR title/body), applies it, pushes a branch, and opens the PR.

The workflow already:
  - checked out main
  - configured swami-builder git identity
  - fetched /tmp/issue.json (issue payload)
  - staged /tmp/context.md (AGENTS.md + ADRs)
  - set BRANCH=ready/issue-<N>

Env: GITHUB_REPOSITORY, BRANCH, ANTHROPIC_API_KEY, GH_TOKEN.
Optional: ISSUE_JSON_FILE (default /tmp/issue.json),
CONTEXT_FILE (default /tmp/context.md).
"""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import anthropic

MODEL = "claude-opus-5"
MAX_TOKENS = 16000

# Cap the number of files Claude can ask Builder to touch in one PR. Wide
# multi-file edits from a single issue are almost always a sign that the
# issue should have been split during triage — the cap forces that split
# rather than papering over it with a giant Builder PR.
MAX_FILES = 20
MAX_TOTAL_BYTES = 200_000

# Paths Builder must never write to. Rewriting workflows or secrets from a
# ready-issue plan would let a crafted issue body escalate privileges via
# self-modifying CI. Keep this list strict; widen only with a paired ADR.
FORBIDDEN_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    "scripts/run-triage.py",
    "scripts/run-claude-review.py",
    "scripts/run-builder-from-issue.py",
)


def sh(cmd: list[str]) -> str:
    r = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return r.stdout


def sh_ok(cmd: list[str]) -> bool:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(
            f"cmd failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr}\n"
        )
    return r.returncode == 0


def load_issue() -> dict:
    p = Path(os.environ.get("ISSUE_JSON_FILE", "/tmp/issue.json"))
    if not p.exists():
        raise RuntimeError(f"issue payload not found at {p}")
    return json.loads(p.read_text())


def load_context() -> str:
    p = Path(os.environ.get("CONTEXT_FILE", "/tmp/context.md"))
    return p.read_text() if p.exists() else ""


def build_system(context: str) -> str:
    return (
        "You are the Builder GA for the swami repository. A tracking issue "
        "has been triaged and labeled `ready`, meaning it is actionable as "
        "written. The issue body IS the spec — read it, and produce a plan "
        "for the smallest correct change that satisfies it.\n\n"
        "Rules:\n"
        "  - Produce the change as a set of file writes. Emit COMPLETE file "
        "    contents (not diffs) for each file you touch — Builder applies "
        "    them as full-file writes.\n"
        f"  - Touch at most {MAX_FILES} files. If the issue is wider than "
        "    that, return `plan=null` and explain in `reasoning` that the "
        "    issue should be split.\n"
        "  - Never touch these paths (return `plan=null` if the issue asks "
        f"    you to): {', '.join(FORBIDDEN_PREFIXES)}. Workflow / script "
        "    self-modification from an issue body is a privilege-escalation "
        "    vector — that must go through a human PR.\n"
        "  - If the issue is ambiguous or you cannot produce a confident "
        "    plan, return `plan=null`. Builder will comment on the issue "
        "    asking for clarification rather than opening a wrong PR.\n\n"
        "Respond with a SINGLE JSON object and nothing else, matching this shape:\n"
        '{"plan": null | {'
        ' "files": [{"path": "<repo-relative>", "contents": "<full file>"}],'
        ' "commit_message": "<one-line, conventional-commit style>",'
        ' "pr_title": "<short title>",'
        ' "pr_body": "<markdown body — link back to the tracking issue>"'
        ' },'
        ' "reasoning": "<one-paragraph read of the issue and what you built (or why you refused)>"}'
        "\n\n===== REPO CONTEXT =====\n" + context
    )


def build_user(issue: dict) -> str:
    return (
        f"## Issue #{issue.get('number')} — {issue.get('title')}\n\n"
        f"{issue.get('body') or '(empty body)'}\n"
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


def validate_plan(plan: dict) -> tuple[bool, str]:
    """Return (ok, reason). Reason is the message posted back on refusal."""
    files = plan.get("files")
    if not isinstance(files, list) or not files:
        return False, "plan.files is empty — nothing to write."
    if len(files) > MAX_FILES:
        return False, f"plan.files has {len(files)} entries (cap {MAX_FILES})."
    total = 0
    for i, f in enumerate(files):
        if not isinstance(f, dict):
            return False, f"plan.files[{i}] is not an object."
        path = f.get("path")
        contents = f.get("contents")
        if not isinstance(path, str) or not path:
            return False, f"plan.files[{i}].path missing or not a string."
        if not isinstance(contents, str):
            return False, f"plan.files[{i}].contents missing or not a string."
        # Reject traversal, absolute paths, and forbidden prefixes.
        norm = os.path.normpath(path)
        if norm.startswith("..") or os.path.isabs(norm) or norm == ".":
            return False, f"plan.files[{i}].path escapes the repo root: {path!r}."
        for pref in FORBIDDEN_PREFIXES:
            if norm == pref or norm.startswith(pref):
                return False, (
                    f"plan.files[{i}].path {path!r} touches a forbidden path "
                    f"({pref}). Workflow / script self-modification must go "
                    "through a human PR."
                )
        total += len(contents.encode("utf-8", errors="replace"))
    if total > MAX_TOTAL_BYTES:
        return False, f"plan writes {total} bytes across all files (cap {MAX_TOTAL_BYTES})."
    if not isinstance(plan.get("commit_message"), str) or not plan["commit_message"].strip():
        return False, "plan.commit_message missing."
    if not isinstance(plan.get("pr_title"), str) or not plan["pr_title"].strip():
        return False, "plan.pr_title missing."
    if not isinstance(plan.get("pr_body"), str):
        return False, "plan.pr_body missing."
    return True, ""


def apply_plan(plan: dict) -> list[str]:
    """Write plan files to disk. Returns the list of paths written."""
    written: list[str] = []
    for f in plan["files"]:
        path = Path(f["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f["contents"])
        written.append(str(path))
    return written


def post_issue_comment(repo: str, issue_num: int, body: str) -> None:
    body_path = Path("/tmp/builder-issue-comment.md")
    body_path.write_text(body)
    sh_ok(["gh", "issue", "comment", str(issue_num),
           "--repo", repo, "--body-file", str(body_path)])


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ["BRANCH"]
    issue = load_issue()
    issue_num = int(issue["number"])
    context = load_context()

    system = build_system(context)
    user = build_user(issue)

    try:
        raw = call_claude(system, user)
    except Exception as exc:  # noqa: BLE001
        print(f"claude planner failed: {exc}", file=sys.stderr)
        post_issue_comment(repo, issue_num, (
            f"Builder GA planner failed: `{type(exc).__name__}: {exc}`. "
            "See the workflow logs. Re-label with `ready` (remove and re-add) "
            "to retry, or drop the `ready` label to hand back to triage."
        ))
        return 1

    plan = raw.get("plan")
    reasoning = str(raw.get("reasoning") or "").strip()

    if plan is None:
        post_issue_comment(repo, issue_num, (
            "Builder GA saw the `ready` label but the planner refused to "
            "act on this issue.\n\n"
            f"**Reasoning:** {reasoning or '(none returned)'}\n\n"
            "Please expand the issue (repro, scope, expected behavior) or "
            "split it into smaller work items, then re-label with `ready`."
        ))
        return 0  # not a failure — refusal is a valid outcome

    ok, why = validate_plan(plan)
    if not ok:
        post_issue_comment(repo, issue_num, (
            f"Builder GA rejected the planner's output: {why}\n\n"
            f"**Planner reasoning:** {reasoning or '(none returned)'}\n\n"
            "This is usually a sign the issue is too wide or under-specified "
            "for a single-PR pickup. Consider splitting it."
        ))
        return 1

    # Create the working branch off main. `-B` is deliberate: rerunning after
    # a failed push should reset the branch to main and re-apply cleanly,
    # not carry stale files from a previous attempt.
    sh(["git", "checkout", "-B", branch])
    written = apply_plan(plan)

    # Stage only the files Claude asked to write — mirrors the translate job's
    # "never git add -A" invariant so a stray tempfile can't leak into the PR.
    for p in written:
        sh(["git", "add", "--", p])

    diff_check = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], capture_output=True
    )
    if diff_check.returncode == 0:
        # Nothing staged — the plan's file writes matched main verbatim.
        post_issue_comment(repo, issue_num, (
            "Builder GA applied the planner's output but the working tree "
            "matched `main` — no diff to commit.\n\n"
            f"**Planner reasoning:** {reasoning or '(none returned)'}\n\n"
            "The change may already be present. Verify and close if so."
        ))
        return 0

    sh(["git", "commit", "-m", plan["commit_message"]])
    sh(["git", "push", "--set-upstream", "origin", branch])

    pr_body = (
        plan["pr_body"].rstrip()
        + f"\n\n---\n\nTracking issue: #{issue_num}\n\n"
        + f"_Opened by Builder GA (ready path). Planner: {MODEL}._"
    )
    pr_body_path = Path("/tmp/builder-pr-body.md")
    pr_body_path.write_text(pr_body)

    sh(["gh", "pr", "create",
        "--repo", repo,
        "--base", "main",
        "--head", branch,
        "--title", plan["pr_title"],
        "--body-file", str(pr_body_path)])

    # Best-effort: get the PR URL back for the tracking-issue comment.
    try:
        url = sh(["gh", "pr", "view", branch, "--repo", repo,
                  "--json", "url", "--jq", ".url"]).strip()
    except subprocess.CalledProcessError:
        url = f"(branch {branch})"

    post_issue_comment(repo, issue_num, (
        f"Builder GA opened a PR for this issue: {url}\n\n"
        f"Branch: `{branch}`\n\n"
        f"**Planner reasoning:** {reasoning or '(none returned)'}\n\n"
        "Review, iterate, or close — the `ready` label has done its job."
    ))
    print(f"opened PR from {branch} with {len(written)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
