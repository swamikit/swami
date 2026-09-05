#!/usr/bin/env bash
# safe-merge.sh — pre-merge gate for swami PRs.
#
# Runs the reviewer-freshness + P1 check inline and only invokes `gh pr merge`
# when every condition passes. Fixes the failure mode where a human runs a
# "no P1?" check, then merges minutes later after new P1s (or a new push that
# invalidated the reviewer read) have arrived: the check must run immediately
# before the merge call, atomically, from a single command.
#
# Usage: scripts/safe-merge.sh <PR-NUMBER> [--dry-run] [--squash|--merge|--rebase]
#
# Exit 0 = safe (merged, or dry-run passed). Exit >0 = aborted with reason.

set -euo pipefail

# ---------- args ----------

PR=""
DRY_RUN=0
MERGE_STYLE="--squash"

usage() {
  echo "Usage: $0 <PR-NUMBER> [--dry-run] [--squash|--merge|--rebase]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --squash|--merge|--rebase) MERGE_STYLE="$1" ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [[ -z "$PR" ]]; then
        PR="$1"
      else
        echo "unexpected argument: $1" >&2; usage; exit 2
      fi
      ;;
  esac
  shift
done

if [[ -z "$PR" ]]; then
  usage; exit 2
fi
if ! [[ "$PR" =~ ^[0-9]+$ ]]; then
  echo "PR number must be numeric, got: $PR" >&2; exit 2
fi

# ---------- helpers ----------

REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"

abort() {
  # $1 = short reason, $2+ = remediation lines
  echo "ABORT: $1" >&2
  shift || true
  for line in "$@"; do
    echo "  -> $line" >&2
  done
  exit 1
}

note() { echo "NOTE: $*"; }
ok()   { echo "OK:   $*"; }

# ---------- step 1: HEAD SHA ----------

HEAD_SHA="$(gh pr view "$PR" --repo "$REPO" --json commits \
  --jq '.commits | last | .oid')"
if [[ -z "$HEAD_SHA" || "$HEAD_SHA" == "null" ]]; then
  abort "could not resolve HEAD SHA for PR #$PR"
fi
HEAD_SHORT="${HEAD_SHA:0:7}"
echo "PR #$PR HEAD: $HEAD_SHA"

# ---------- step 2: state + mergeability ----------

STATE_JSON="$(gh pr view "$PR" --repo "$REPO" --json state,mergeable)"
STATE="$(echo "$STATE_JSON" | jq -r '.state')"
MERGEABLE="$(echo "$STATE_JSON" | jq -r '.mergeable')"

if [[ "$STATE" != "OPEN" ]]; then
  abort "PR state is $STATE, expected OPEN" \
    "Reopen the PR or pick a different one."
fi
if [[ "$MERGEABLE" != "MERGEABLE" ]]; then
  abort "PR mergeability is $MERGEABLE, expected MERGEABLE" \
    "Rebase onto main and resolve conflicts, then re-run this script."
fi
ok "state=OPEN, mergeable=MERGEABLE"

# ---------- step 3: required checks ----------

CHECKS_JSON="$(gh pr view "$PR" --repo "$REPO" --json statusCheckRollup)"
# Each entry is a CheckRun or StatusContext. CheckRun uses .conclusion,
# StatusContext uses .state. Treat SUCCESS / SKIPPED / NEUTRAL as green;
# anything else (FAILURE, CANCELLED, TIMED_OUT, ACTION_REQUIRED, PENDING,
# IN_PROGRESS, QUEUED, "") is not.
FAILING_CHECKS="$(echo "$CHECKS_JSON" | jq -r '
  .statusCheckRollup[]
  | . as $c
  | ( .conclusion // .state // "" ) as $verdict
  | select( ($verdict | ascii_upcase) as $v
            | ($v == "SUCCESS" or $v == "SKIPPED" or $v == "NEUTRAL") | not )
  | ( .name // .context // "unnamed" ) + " (" + ( ($verdict | tostring) | ascii_upcase ) + ")"
')"

if [[ -n "$FAILING_CHECKS" ]]; then
  {
    echo "ABORT: required checks not green:" >&2
    while IFS= read -r line; do
      [[ -n "$line" ]] && echo "  - $line" >&2
    done <<< "$FAILING_CHECKS"
    echo "  -> Wait for pending checks or push a fix; re-run when green." >&2
  }
  exit 1
fi
ok "all required checks SUCCESS or SKIPPED"

# ---------- step 4: Codex summary card ----------

COMMENTS_JSON="$(gh api --paginate "repos/$REPO/issues/$PR/comments")"

CODEX_BODY="$(echo "$COMMENTS_JSON" | jq -r '
  [ .[]
    | select( ((.user.login // "") | ascii_downcase | test("codex|chatgpt-codex"))
              and (.body | contains("codex-pull-request-review-summary")) ) ]
  | sort_by(.created_at)
  | last
  | .body // ""
')"

if [[ -z "$CODEX_BODY" || "$CODEX_BODY" == "null" ]]; then
  note "no Codex summary found on PR #$PR — Codex is external and not always active; continuing."
  CODEX_ACTIVE=0
else
  CODEX_ACTIVE=1
  # First `<7-40 hex>` span in the body is the SHA Codex reviewed.
  CODEX_SHA="$(echo "$CODEX_BODY" | grep -oE '`[a-f0-9]{7,40}`' | head -n1 | tr -d '`')"
  if [[ -z "$CODEX_SHA" ]]; then
    abort "Codex summary found but no reviewed-SHA span in it" \
      "Re-trigger Codex with '@codex review' as a PR comment."
  fi
  if [[ "$CODEX_SHA" != "${HEAD_SHORT}" && "${CODEX_SHA:0:7}" != "$HEAD_SHORT" ]]; then
    abort "Codex review stale (reviewed $CODEX_SHA, HEAD is $HEAD_SHORT)" \
      "Re-trigger Codex with '@codex review' as a PR comment, then re-run."
  fi
  ok "Codex review current at $CODEX_SHA"
fi

# ---------- step 5: Claude sticky ----------

# Trust only comments posted by the workflow itself: run-claude-review.py runs
# under GH_TOKEN=github.token, so `.user.login` is `github-actions[bot]` and
# `.user.type` is `Bot`. Filtering solely on the `<!-- claude-review -->`
# marker would let any commenter (including a fork PR author) post a fake
# "approve, no P1s" sticky and slip past this gate.
CLAUDE_BODY="$(echo "$COMMENTS_JSON" | jq -r '
  [ .[]
    | select(.body | contains("<!-- claude-review -->"))
    | select( ((.user.login // "") == "github-actions[bot]")
              and ((.user.type // "") == "Bot") ) ]
  | sort_by(.created_at)
  | last
  | .body // ""
')"

CLAUDE_REQUIRED=1
# If ANTHROPIC_API_KEY is not configured as a repo secret, Claude review is
# skipped intentionally by the workflow and its absence is not a merge blocker.
# `gh secret list` requires admin scope on the repo, which reviewers and most
# CI tokens don't have; distinguish "call failed" (fail closed — we cannot
# tell) from "call succeeded and secret is absent" (fail open — genuine skip).
if secrets_out="$(gh secret list --repo "$REPO" 2>&1)"; then
  case "$secrets_out" in
    *ANTHROPIC_API_KEY*) CLAUDE_REQUIRED=1 ;;
    *) CLAUDE_REQUIRED=0 ;;
  esac
else
  abort "cannot enumerate repo secrets to check ANTHROPIC_API_KEY: $secrets_out" \
    "Re-run with a token that has admin scope on $REPO, or set ANTHROPIC_API_KEY so the Claude gate is unambiguously required."
fi

if [[ -z "$CLAUDE_BODY" || "$CLAUDE_BODY" == "null" ]]; then
  if [[ "$CLAUDE_REQUIRED" -eq 1 ]]; then
    abort "Claude review not posted on PR #$PR" \
      "Re-run the 'review' workflow (Actions tab -> review -> Re-run all jobs)."
  fi
  note "Claude review sticky absent but ANTHROPIC_API_KEY not configured on repo — skipping Claude gate."
  CLAUDE_ACTIVE=0
else
  CLAUDE_ACTIVE=1
  # Match a HEAD line like: HEAD: `<sha>` (may be inline with verdict).
  CLAUDE_SHA="$(echo "$CLAUDE_BODY" | grep -oE 'HEAD:[[:space:]]*`[a-f0-9]{7,40}`' \
    | head -n1 | grep -oE '`[a-f0-9]{7,40}`' | tr -d '`')"
  if [[ -z "$CLAUDE_SHA" ]]; then
    abort "Claude sticky present but no HEAD: <sha> line found" \
      "Re-run the 'review' workflow to refresh the sticky."
  fi
  if [[ "$CLAUDE_SHA" != "$HEAD_SHA" && "${CLAUDE_SHA:0:7}" != "$HEAD_SHORT" ]]; then
    abort "Claude review stale (reviewed $CLAUDE_SHA, HEAD is $HEAD_SHA)" \
      "Push a fix (which re-triggers) or re-run the 'review' workflow, then re-run this script."
  fi
  ok "Claude review current at $CLAUDE_SHA"
fi

# ---------- step 6: Codex line-level P1 badges ----------

# Run this scan unconditionally, independent of CODEX_ACTIVE. The existence of a
# `P1 Badge` line comment from Codex is itself proof Codex is active — gating the
# scan on the summary card (step 4) would let a PR with live P1 line comments
# merge whenever the card is missing for any reason: marker drift on Codex's
# side, a review posted as a `pulls/{n}/reviews` body rather than an issue
# comment, a deleted/collapsed card, or a review still mid-flight. That is the
# same fail-open class as the earlier secret-probe P1, in a code path the round-2
# fix didn't touch.
CODEX_P1S="$(gh api --paginate "repos/$REPO/pulls/$PR/comments" --jq '
  .[]
  | select( ((.user.login // "") | ascii_downcase | test("codex|chatgpt-codex"))
            and (.body | contains("P1 Badge")) )
  | ( (.path // "?") + ":" + ((.line // .original_line // 0) | tostring) )
')"
if [[ -n "$CODEX_P1S" ]]; then
  {
    echo "ABORT: Codex posted P1 findings on:" >&2
    while IFS= read -r line; do
      [[ -n "$line" ]] && echo "  - $line" >&2
    done <<< "$CODEX_P1S"
    if [[ "$CODEX_ACTIVE" -eq 0 ]]; then
      echo "  -> (No Codex summary card was found on this PR; P1 line comments were still discovered directly.)" >&2
    fi
    echo "  -> Fix each P1 and push; Codex re-reviews on the new SHA." >&2
  }
  exit 1
fi
if [[ "$CODEX_ACTIVE" -eq 0 ]]; then
  ok "no Codex P1 line-level findings (summary card absent)"
else
  ok "no Codex P1 line-level findings"
fi

# ---------- step 7: Claude P1 count ----------

if [[ "$CLAUDE_ACTIVE" -eq 1 ]]; then
  # The sticky's header line looks like: `verdict: **approve**` or
  # `verdict: **request changes**` (see scripts/run-claude-review.py:135, 143).
  # Trust the verdict as the primary gate — a `request changes` verdict must
  # abort even when the response is malformed and no `### P1 (N)` header was
  # emitted (e.g. P2-only body, or diff-truncated auto-request-changes at
  # scripts/run-claude-review.py:295 which posts a synthetic P1 in a different
  # format). Otherwise the count defaults to 0 and the gate lets a
  # request-changes review merge.
  CLAUDE_VERDICT="$(echo "$CLAUDE_BODY" \
    | grep -oE 'verdict:[[:space:]]*\*\*(approve|request changes)\*\*' \
    | head -n1 | sed -E 's/.*\*\*(approve|request changes)\*\*/\1/')"
  if [[ -z "$CLAUDE_VERDICT" ]]; then
    abort "Claude sticky present but has no 'verdict: **approve|request changes**' line" \
      "Re-run the 'review' workflow to refresh the sticky."
  fi
  if [[ "$CLAUDE_VERDICT" != "approve" ]]; then
    abort "Claude review verdict is '$CLAUDE_VERDICT'" \
      "Read the sticky, address the findings, push; sticky updates in place."
  fi
  # Matches "### P1 (N)" header; N is the count Claude wrote itself. Belt and
  # suspenders after the verdict check: a valid `approve` sticky should always
  # have zero P1s, so any P1 count on an approve verdict is itself a red flag.
  CLAUDE_P1_N="$(echo "$CLAUDE_BODY" | grep -oE '^###[[:space:]]+P1[[:space:]]*\([0-9]+\)' \
    | head -n1 | grep -oE '[0-9]+' | head -n1 || true)"
  CLAUDE_P1_N="${CLAUDE_P1_N:-0}"
  if [[ "$CLAUDE_P1_N" -gt 0 ]]; then
    abort "Claude review lists $CLAUDE_P1_N P1 finding(s)" \
      "Read the sticky, fix each P1, push; sticky updates in place."
  fi
  ok "Claude review verdict=approve, no Claude P1 findings"
fi

# ---------- step 8: merge (or dry-run) ----------

SUMMARY="reviews current at $HEAD_SHORT, no P1s"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "OK: $SUMMARY. (dry-run — skipping merge)"
  exit 0
fi

echo "OK: $SUMMARY. Merging with $MERGE_STYLE."
# --match-head-commit pins the merge to the SHA we just reviewed: if a push
# lands between the freshness checks above and this call, GitHub rejects the
# merge server-side instead of silently merging an unreviewed tip.
gh pr merge "$PR" --repo "$REPO" "$MERGE_STYLE" --delete-branch \
  --match-head-commit "$HEAD_SHA"
