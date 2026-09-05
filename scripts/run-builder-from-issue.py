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

# Paths Builder must never write to. Rewriting anything that CI executes —
# workflows, actions, script helpers, or Xcode build phases embedded in the
# project file — would let a crafted issue body escalate privileges via
# self-modifying CI. This is deny-by-shape (not by named script) so a new
# helper landing under scripts/ or a new workflow under .github/ is protected
# on day one without a paired edit here (Codex P1 review round 2).
FORBIDDEN_PREFIXES = (
    ".github/",          # every workflow, action, CODEOWNERS, PR templates,
                         # issue templates — any config CI reads
    "scripts/",          # every helper builder.yml / verify.yml / review.yml
                         # run with repo secrets in scope
)

# Paths matched by exact filename or path substring — used for the Xcode
# project shell-build-phase escalation path Codex called out (a plan can add
# a "Run Script" phase to project.pbxproj that executes on any subsequent
# build). Also covers .xcworkspace shared data.
FORBIDDEN_SUBSTRINGS = (
    ".xcodeproj/",       # anything inside an Xcode project bundle
    ".xcworkspace/",
)

FORBIDDEN_SUFFIXES = (
    ".pbxproj",          # Xcode project files carry shell build phases
)


def _forbidden_reason(norm: str) -> str | None:
    """Return the reason `norm` is forbidden, or None if it is allowed.

    `norm` must already be `os.path.normpath`ed. Root-level dotfiles
    (`.gitignore`, `.gitattributes`, `.mailmap`, `.env*`, …) are refused as a
    class — they configure the whole repo and have no business being emitted
    from an issue body.
    """
    for pref in FORBIDDEN_PREFIXES:
        if norm == pref.rstrip("/") or norm.startswith(pref):
            return f"forbidden prefix `{pref}`"
    for sub in FORBIDDEN_SUBSTRINGS:
        if sub in norm:
            return f"forbidden substring `{sub}` (Xcode project bundles execute build phases)"
    for suf in FORBIDDEN_SUFFIXES:
        if norm.endswith(suf):
            return f"forbidden suffix `{suf}` (Xcode project files execute build phases)"
    # Root-level dotfile (no `/` in normpath, name starts with `.`).
    if "/" not in norm and norm.startswith("."):
        return "root-level dotfile (repo-wide config must go through a human PR)"
    return None


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
        "  - CREATION-ONLY: only emit paths that do NOT yet exist in the "
        "    repo. You are not shown the current contents of any file, so "
        "    editing an existing file would mean inventing its current "
        "    contents and clobbering the real file with the invention. If "
        "    the issue requires editing an existing file, return `plan=null` "
        "    and say so in `reasoning`.\n"
        f"  - Touch at most {MAX_FILES} files. If the issue is wider than "
        "    that, return `plan=null` and explain in `reasoning` that the "
        "    issue should be split.\n"
        "  - Never touch anything CI executes — every path under `.github/` "
        "    or `scripts/`, any `.xcodeproj/` or `.xcworkspace/` bundle, any "
        "    `.pbxproj` file, or any root-level dotfile. Return `plan=null` "
        "    if the issue asks you to; that class of change is a "
        "    privilege-escalation vector and must go through a human PR.\n"
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
        reason = _forbidden_reason(norm)
        if reason is not None:
            return False, (
                f"plan.files[{i}].path {path!r} is forbidden: {reason}. "
                "Anything CI executes — workflows, script helpers, or Xcode "
                "build phases — must go through a human PR."
            )
        # Creation-only until read-back lands. `build_system` tells Claude to
        # emit COMPLETE file contents, but `Load builder context` in the ready
        # job only supplies AGENTS.md + docs/decisions/*.md — never the file
        # being overwritten. That means every "edit existing file F" issue
        # asks the planner to invent F's current contents and Builder would
        # silently clobber the real file with the invention. Guard by
        # refusing to write over anything that exists at HEAD; a follow-up
        # PR can lift this once the workflow reads the target files back into
        # /tmp/context.md and hands them to the planner (Codex P1 round 2,
        # Claude review sticky P1 #1).
        if Path(norm).exists():
            return False, (
                f"plan.files[{i}].path {path!r} already exists at HEAD, and "
                "the ready-path planner is CREATION-ONLY until it is given "
                "the file's current contents. Builder was asked to emit "
                "COMPLETE file contents but never saw this file, so writing "
                "it would clobber real code with a hallucination. Split the "
                "issue into a create-a-new-file task, or wait until the "
                "planner's context includes the target files."
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

    # PRs opened with the workflow's GITHUB_TOKEN do NOT emit `pull_request`
    # events (GitHub's recursion guard on the automatic token). Without an
    # explicit dispatch, verify.yml's pixel gate and review.yml's Claude
    # review would never wake on this PR — the double-green gate AGENTS.md
    # Beat 3/4 and ADR-0014 put the merge decision behind would be
    # structurally unreachable. Fire both by workflow_dispatch after the PR
    # is created; each dispatch is best-effort — a warning on failure, not a
    # hard fail, so the PR still lands on the tracking issue even if a gate
    # is temporarily unreachable (Codex P1 round 2, Claude sticky P1 #3).
    pr_body = (
        plan["pr_body"].rstrip()
        + f"\n\n---\n\nTracking issue: #{issue_num}\n\n"
        + f"_Opened by Builder GA (ready path). Planner: {MODEL}._\n\n"
        + "_This PR was opened by a workflow's GITHUB_TOKEN, so GitHub's "
        + "recursion guard suppresses the automatic `pull_request` event. "
        + "Builder explicitly dispatches `verify.yml` (against the ready "
        + "branch) and `review.yml` (against this PR number) after PR "
        + "creation — check the workflow-run list on the head SHA to "
        + "distinguish a missing gate from a skipped one._"
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
    # Also grab the PR number for review.yml's workflow_dispatch input.
    try:
        pr_view = sh(["gh", "pr", "view", branch, "--repo", repo,
                      "--json", "url,number", "--jq", "."]).strip()
        pr_meta = json.loads(pr_view)
        url = pr_meta.get("url", f"(branch {branch})")
        pr_number = pr_meta.get("number")
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        url = f"(branch {branch})"
        pr_number = None

    # Dispatch verify.yml against the ready branch (its workflow_dispatch
    # trigger has no required inputs — see .github/workflows/verify.yml). It
    # runs the pixel gate on macos-15 and posts its own sticky comment.
    if not sh_ok(["gh", "workflow", "run", "verify.yml",
                  "--repo", repo, "--ref", branch]):
        sys.stderr.write(
            f"::warning::gh workflow run verify.yml --ref {branch} failed — "
            "pixel gate must be triggered manually.\n"
        )

    # Dispatch review.yml with the PR number. review.yml's workflow_dispatch
    # takes `pr_number` (added in the same round of fixes) so Review GA can
    # be woken on Builder-opened PRs.
    if pr_number is None:
        sys.stderr.write(
            "::warning::could not resolve PR number after `gh pr create` — "
            "skipping review.yml dispatch. A maintainer can trigger it via "
            "`gh workflow run review.yml -f pr_number=<N>`.\n"
        )
    else:
        if not sh_ok(["gh", "workflow", "run", "review.yml",
                      "--repo", repo,
                      "-f", f"pr_number={pr_number}"]):
            sys.stderr.write(
                f"::warning::gh workflow run review.yml -f pr_number={pr_number} "
                "failed — Review GA must be triggered manually (comment "
                "`@claude review` on the PR).\n"
            )

    post_issue_comment(repo, issue_num, (
        f"Builder GA opened a PR for this issue: {url}\n\n"
        f"Branch: `{branch}`\n\n"
        f"**Planner reasoning:** {reasoning or '(none returned)'}\n\n"
        "Review, iterate, or close — the `ready` label has done its job. "
        "Builder dispatched `verify.yml` and `review.yml` explicitly on the "
        "new PR (GITHUB_TOKEN-opened PRs don't fire those events on their "
        "own); check the PR's Checks tab for the runs."
    ))
    print(f"opened PR from {branch} with {len(written)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
