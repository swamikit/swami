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

CLAUDE_BODY="$(echo "$COMMENTS_JSON" | jq -r '
  [ .[] | select(.body | contains("<!-- claude-review -->")) ]
  | sort_by(.created_at)
  | last
  | .body // ""
')"

CLAUDE_REQUIRED=1
# If ANTHROPIC_API_KEY is not configured as a repo secret, Claude review is
# skipped intentionally by the workflow and its absence is not a merge blocker.
if ! gh secret list --repo "$REPO" 2>/dev/null | awk '{print $1}' | grep -qx "ANTHROPIC_API_KEY"; then
  CLAUDE_REQUIRED=0
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

if [[ "$CODEX_ACTIVE" -eq 1 ]]; then
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
      echo "  -> Fix each P1 and push; Codex re-reviews on the new SHA." >&2
    }
    exit 1
  fi
  ok "no Codex P1 line-level findings"
fi

# ---------- step 7: Claude P1 count ----------

if [[ "$CLAUDE_ACTIVE" -eq 1 ]]; then
  # Matches "### P1 (N)" header; N is the count Claude wrote itself.
  CLAUDE_P1_N="$(echo "$CLAUDE_BODY" | grep -oE '^###[[:space:]]+P1[[:space:]]*\([0-9]+\)' \
    | head -n1 | grep -oE '[0-9]+' | head -n1 || true)"
  CLAUDE_P1_N="${CLAUDE_P1_N:-0}"
  if [[ "$CLAUDE_P1_N" -gt 0 ]]; then
    abort "Claude review lists $CLAUDE_P1_N P1 finding(s)" \
      "Read the sticky, fix each P1, push; sticky updates in place."
  fi
  ok "no Claude P1 findings"
fi

# ---------- step 8: merge (or dry-run) ----------

SUMMARY="reviews current at $HEAD_SHORT, no P1s"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "OK: $SUMMARY. (dry-run — skipping merge)"
  exit 0
fi

echo "OK: $SUMMARY. Merging with $MERGE_STYLE."
gh pr merge "$PR" --repo "$REPO" "$MERGE_STYLE" --delete-branch
