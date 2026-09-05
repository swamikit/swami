#!/usr/bin/env bash
#
# merge-gate.sh — computes and posts the consolidated `merge-gate` commit
# status for one PR. Reads the reviewer registry from `.github/reviewers.yml`
# so identities/markers are config, not hardcoded. Consumes formal PR Reviews
# posted via the Reviews API (refactor B / PR #75) — sticky-issue comments
# are NOT the source of truth here.
#
# Priority-ordered rules; the FIRST failing rule wins the status:
#   1. Mergeability      — MERGEABLE (no conflicts)
#   2. Required checks   — all statusCheckRollup entries SUCCESS/SKIPPED/NEUTRAL
#   3. Reviewer freshness — deep reviewer must have posted a Review at HEAD_SHA
#   4. P1 count          — deep reviewer's `### P1 (N)` header must be zero
#   5. P2/P3 orphans     — each P2/P3 finding must be addressed or linked to
#                          an OPEN/CLOSED-COMPLETED issue whose body references
#                          this PR or the finding's path:line
#
# Outputs:
#   - POST /repos/{owner}/{repo}/statuses/{sha} with context=merge-gate,
#     state in {success, failure, pending}, description <=140 chars.
#   - Post/update a marker-tagged issue comment (`<!-- merge-gate -->`) with
#     the longer human-readable breakdown.
#
# Usage:
#   scripts/merge-gate.sh --pr <N> [--repo OWNER/REPO] [--head-sha SHA]
#   scripts/merge-gate.sh --self-test
#
# Env:
#   GH_TOKEN         — required (workflow-provided or manual).
#   GITHUB_TOKEN     — accepted alias for GH_TOKEN.
#   REVIEWERS_CONFIG — override path to reviewers.yml (default:
#                      $repo_root/.github/reviewers.yml).
#
# Dependencies: bash 3.2+, gh, jq. Optional: yq (nicer YAML parsing; falls
# back to a small grep-based parser so a runner without yq still works).
#
# Not implemented here (deliberate):
#   - Modifying branch protection. Making `merge-gate` a required check is a
#     one-time repo settings change (Settings → Branches → main → require
#     `merge-gate`) — the workflow only POSTS the status.
#   - Auto-merging. This script is the GATE, not the merger.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
PR=""
REPO=""
HEAD_SHA=""
SELF_TEST=0

usage() {
  sed -n '2,40p' "$0"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr)         PR="${2:-}"; shift 2 ;;
    --repo)       REPO="${2:-}"; shift 2 ;;
    --head-sha)   HEAD_SHA="${2:-}"; shift 2 ;;
    --self-test)  SELF_TEST=1; shift ;;
    -h|--help)    usage ;;
    *)            echo "merge-gate: unknown arg: $1" >&2; usage ;;
  esac
done

# GH_TOKEN alias — GitHub Actions injects GITHUB_TOKEN by default.
if [[ -z "${GH_TOKEN:-}" && -n "${GITHUB_TOKEN:-}" ]]; then
  export GH_TOKEN="$GITHUB_TOKEN"
fi

# Self-test path takes no other input.
if [[ "$SELF_TEST" -eq 0 ]]; then
  if [[ -z "$PR" ]]; then
    echo "merge-gate: --pr is required (or --self-test)" >&2
    usage
  fi
fi

for tool in jq; do
  command -v "$tool" >/dev/null 2>&1 || { echo "merge-gate: missing $tool" >&2; exit 2; }
done
if [[ "$SELF_TEST" -eq 0 ]]; then
  command -v gh >/dev/null 2>&1 || { echo "merge-gate: missing gh" >&2; exit 2; }
fi

# ---------------------------------------------------------------------------
# Working state
# ---------------------------------------------------------------------------
WORK="$(mktemp -d -t merge-gate.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# Repo root discovery (for locating .github/reviewers.yml)
# ---------------------------------------------------------------------------
_script_dir() {
  cd "$(dirname "$0")" && pwd
}
SCRIPT_DIR="$(_script_dir)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REVIEWERS_CONFIG="${REVIEWERS_CONFIG:-$REPO_ROOT/.github/reviewers.yml}"

# ---------------------------------------------------------------------------
# Reviewer registry parser
# ---------------------------------------------------------------------------
# Reads .github/reviewers.yml and emits TSV rows (one per reviewer):
#   id\tidentities_csv\tmarker\tfailure_marker\tstyle\tgates_merge
# with `null` for missing values.
#
# Prefers `yq` when available (correct YAML). Falls back to a small grep
# parser that handles the shape this repo's file uses — flat list, one-level
# nesting, dash-prefixed identities. If someone rewrites the file into a
# fancy YAML shape yq can handle and the parser can't, that's a signal to
# install yq in the runner rather than expand this bash.
parse_reviewers() {
  local cfg="$1"
  if [[ ! -f "$cfg" ]]; then
    echo "merge-gate: reviewers config not found: $cfg" >&2
    return 2
  fi
  if command -v yq >/dev/null 2>&1; then
    yq -r '
      .reviewers[]
      | [
          .id,
          (.identities // [] | join(",")),
          (.marker // "null"),
          (.failure_marker // "null"),
          (.style // "reviews-api"),
          (.gates_merge // false | tostring)
        ]
      | @tsv
    ' "$cfg"
    return 0
  fi
  # No yq — pure-bash parser. State machine that recognizes the exact shape
  # used by .github/reviewers.yml. Deliberately narrow: it doesn't try to be
  # a general YAML parser (that way lies pain). macOS ships BSD awk which
  # lacks gawk's `match(str, re, arr)` third-arg form, so we avoid awk
  # entirely and stay in bash.
  local id="" ids="" marker="null" fmarker="null" style="reviews-api" gates="false" in_ids=0
  local line stripped key val
  _flush() {
    if [[ -n "$id" ]]; then
      printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$id" "$ids" "$marker" "$fmarker" "$style" "$gates"
    fi
    id=""; ids=""; marker="null"; fmarker="null"; style="reviews-api"; gates="false"; in_ids=0
  }
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Strip trailing whitespace.
    stripped="${line%"${line##*[![:space:]]}"}"
    # Skip blanks and comments.
    if [[ -z "$stripped" || "$stripped" =~ ^[[:space:]]*# ]]; then
      continue
    fi
    # Top-level `reviewers:` header.
    if [[ "$stripped" =~ ^reviewers:[[:space:]]*$ ]]; then
      continue
    fi
    # New reviewer: `- id: <value>`
    if [[ "$stripped" =~ ^[[:space:]]*-[[:space:]]+id:[[:space:]]*(.*)$ ]]; then
      _flush
      id="${BASH_REMATCH[1]}"
      id="${id%\"}"; id="${id#\"}"
      continue
    fi
    # `identities:` opener.
    if [[ "$stripped" =~ ^[[:space:]]+identities:[[:space:]]*$ ]]; then
      in_ids=1
      continue
    fi
    # `- foo` list items belong to identities: while in_ids=1.
    if [[ $in_ids -eq 1 && "$stripped" =~ ^[[:space:]]+-[[:space:]]+(.*)$ ]]; then
      val="${BASH_REMATCH[1]}"
      val="${val%\"}"; val="${val#\"}"
      if [[ -z "$ids" ]]; then
        ids="$val"
      else
        ids="$ids,$val"
      fi
      continue
    fi
    # `key: value` scalar.
    if [[ "$stripped" =~ ^[[:space:]]+([a-z_]+):[[:space:]]*(.*)$ ]]; then
      in_ids=0
      key="${BASH_REMATCH[1]}"
      val="${BASH_REMATCH[2]}"
      val="${val%\"}"; val="${val#\"}"
      case "$key" in
        marker)
          if [[ -z "$val" || "$val" == "null" ]]; then marker="null"; else marker="$val"; fi
          ;;
        failure_marker)
          if [[ -z "$val" || "$val" == "null" ]]; then fmarker="null"; else fmarker="$val"; fi
          ;;
        style)
          style="$val"
          ;;
        gates_merge)
          gates="$val"
          ;;
      esac
      continue
    fi
  done < "$cfg"
  _flush
  unset -f _flush
}

# Return the identities CSV for reviewer id, or "" if not found.
reviewer_identities() {
  local want="$1" cfg="$2"
  parse_reviewers "$cfg" | while IFS=$'\t' read -r id ids marker fmarker style gates; do
    if [[ "$id" == "$want" ]]; then
      printf '%s' "$ids"
      return 0
    fi
  done
}

# Return the marker for reviewer id (or `null`).
reviewer_marker() {
  local want="$1" cfg="$2"
  parse_reviewers "$cfg" | while IFS=$'\t' read -r id ids marker fmarker style gates; do
    if [[ "$id" == "$want" ]]; then
      printf '%s' "$marker"
      return 0
    fi
  done
}

# Return the failure marker for reviewer id (or `null`).
reviewer_failure_marker() {
  local want="$1" cfg="$2"
  parse_reviewers "$cfg" | while IFS=$'\t' read -r id ids marker fmarker style gates; do
    if [[ "$id" == "$want" ]]; then
      printf '%s' "$fmarker"
      return 0
    fi
  done
}

# ---------------------------------------------------------------------------
# Gate computation — pure functions that take fixture JSON and emit
# {status_state, description}. Called by both the real path (--pr) and the
# self-test path so both trust the same code.
# ---------------------------------------------------------------------------
#
# Each rule function reads from files in $WORK and emits:
#   $WORK/verdict.tsv:  status_state<TAB>short_description<TAB>long_reason
# on the FIRST rule that fires (any state other than "success"). If none
# fire, the caller writes a success verdict at the end.

RESULT_STATE=""
RESULT_DESC=""
RESULT_LONG=""

set_result() {
  RESULT_STATE="$1"
  RESULT_DESC="$2"
  RESULT_LONG="${3:-}"
  # Cap short description at 140 chars — GitHub's status API limit.
  if (( ${#RESULT_DESC} > 140 )); then
    RESULT_DESC="${RESULT_DESC:0:137}..."
  fi
}

# --- Rule 1: mergeability ---
# Input: $WORK/pr.json with { mergeable, mergeStateStatus }.
# Fires unless mergeable == "MERGEABLE".
rule_mergeability() {
  local mergeable
  mergeable="$(jq -r '.mergeable // ""' "$WORK/pr.json")"
  case "$mergeable" in
    MERGEABLE|"")
      # Empty is "not computed yet" — treat as pending upstream will retry.
      if [[ -z "$mergeable" ]]; then
        set_result "pending" "mergeability not yet computed" \
          "GitHub hasn't finished computing mergeability. Re-run once the check settles."
        return 0
      fi
      return 1
      ;;
    CONFLICTING)
      set_result "failure" "merge-conflict" \
        "PR has merge conflicts against the base branch."
      return 0
      ;;
    *)
      set_result "failure" "merge-conflict" \
        "PR mergeability is $mergeable — resolve conflicts / retry."
      return 0
      ;;
  esac
}

# --- Rule 2: required checks ---
# Input: $WORK/pr.json with .statusCheckRollup[].
# Fails on the FIRST rollup entry outside {SUCCESS, SKIPPED, NEUTRAL}.
# `merge-gate` context itself is skipped from evaluation — a status can't
# gate on its own prior value or it never turns green.
rule_checks() {
  local failing
  failing="$(jq -r '
    (.statusCheckRollup // [])
    | map(select(
        (.name // .context // "") != "merge-gate"
        and (
          # Status conclusion vs check-run conclusion — .conclusion for
          # check-runs, .state for statuses. Normalize.
          (.conclusion // .state // "") as $s
          | ($s | ascii_upcase) as $u
          | ($u != "SUCCESS" and $u != "SKIPPED" and $u != "NEUTRAL"
             and $u != "" and $u != "PENDING" and $u != "IN_PROGRESS"
             and $u != "QUEUED" and $u != "WAITING")
        )
      ))
    | .[0]
    | if . == null then "" else
        "\(.name // .context // "unknown-check") is \((.conclusion // .state // "unknown") | ascii_downcase)"
      end
  ' "$WORK/pr.json")"
  local pending
  pending="$(jq -r '
    (.statusCheckRollup // [])
    | map(select(
        (.name // .context // "") != "merge-gate"
        and (
          (.conclusion // .state // "") as $s
          | ($s | ascii_upcase) as $u
          | ($u == "PENDING" or $u == "IN_PROGRESS" or $u == "QUEUED" or $u == "WAITING" or $u == "")
        )
      ))
    | .[0]
    | if . == null then "" else (.name // .context // "unknown-check") end
  ' "$WORK/pr.json")"
  if [[ -n "$failing" ]]; then
    set_result "failure" "check $failing" \
      "One or more required status checks are failing: $failing"
    return 0
  fi
  if [[ -n "$pending" ]]; then
    set_result "pending" "check $pending pending" \
      "Waiting for required status check to complete: $pending"
    return 0
  fi
  return 1
}

# --- Rule 3: reviewer freshness ---
# Input:
#   $WORK/reviews.json — /repos/{repo}/pulls/{N}/reviews response
#   $WORK/pr.json      — includes .headSha
#   $WORK/failures.json — /repos/{repo}/issues/{N}/comments response
#   $DEEP_MARKER, $DEEP_FAILURE_MARKER, $DEEP_IDENTITIES_JSON
#
# If a failure-marker comment for the deep reviewer exists at HEAD_SHA →
# pending "waiting for reviewer to succeed".
# Otherwise pick the most recent non-dismissed Review by a deep-reviewer
# identity whose body contains DEEP_MARKER:
#   - none                       → pending "waiting for deep reviewer"
#   - state == CHANGES_REQUESTED → fail "deep reviewer requested changes"
#   - state == APPROVED          → continue
#   - state == COMMENTED         → treat as no verdict → pending
rule_reviewer_freshness() {
  local head_sha
  head_sha="$(jq -r '.headSha // ""' "$WORK/pr.json")"

  # Failure-marker fast path.
  if [[ -n "$head_sha" && -f "$WORK/failures.json" ]]; then
    local has_failure
    has_failure="$(
      jq -r --arg m "$DEEP_FAILURE_MARKER" --arg sha "$head_sha" '
        [ .[]
          | select((.body // "") | contains($m))
          | select((.body // "") | contains($sha))
        ] | length
      ' "$WORK/failures.json"
    )"
    if [[ "${has_failure:-0}" -gt 0 ]]; then
      set_result "pending" "waiting for reviewer to succeed" \
        "Deep reviewer errored on this HEAD (failure-marker comment present). Retry the review workflow."
      return 0
    fi
  fi

  # Pick the newest Review from deep identities with the deep marker,
  # ignoring DISMISSED entries. The Reviews list is server-ordered oldest
  # → newest so `last` gives us the freshest.
  local review_line rev_state rev_sha rev_id
  review_line="$(
    jq -r --argjson ids "$DEEP_IDENTITIES_JSON" --arg m "$DEEP_MARKER" '
      [ .[]
        | . as $r
        | select(($r.user.login // "") as $l | $ids | index($l))
        | select((.body // "") | contains($m))
        | select((.state // "") != "DISMISSED")
      ]
      | last
      | if . == null then "" else
          [(.state // ""), (.commit_id // ""), (.id | tostring)] | @tsv
        end
    ' "$WORK/reviews.json"
  )"

  if [[ -z "$review_line" ]]; then
    set_result "pending" "waiting for deep reviewer" \
      "No deep reviewer Review found on this PR. The review workflow may still be running."
    return 0
  fi

  IFS=$'\t' read -r rev_state rev_sha rev_id <<<"$review_line" || true

  if [[ -n "$head_sha" && -n "$rev_sha" && "$rev_sha" != "$head_sha" ]]; then
    set_result "pending" "deep reviewer stale — waiting for review of HEAD" \
      "Deep reviewer's latest Review is against $rev_sha but HEAD is $head_sha. Push settled? Retry after."
    return 0
  fi

  case "$rev_state" in
    CHANGES_REQUESTED)
      set_result "failure" "deep reviewer requested changes" \
        "Deep reviewer's latest verdict at HEAD is CHANGES_REQUESTED — address the P1(s) or the review body."
      return 0
      ;;
    APPROVED)
      # Falls through to next rule.
      return 1
      ;;
    COMMENTED|COMMENT)
      set_result "pending" "deep reviewer took no stance (COMMENT)" \
        "Deep reviewer posted a COMMENT verdict — treat as no verdict; awaiting APPROVED / CHANGES_REQUESTED."
      return 0
      ;;
    *)
      set_result "pending" "deep reviewer state=$rev_state — waiting" \
        "Deep reviewer verdict state is $rev_state; awaiting a APPROVED / CHANGES_REQUESTED."
      return 0
      ;;
  esac
}

# --- Rule 4: P1 count ---
# Read the deep review body captured by rule 3 (re-select from reviews.json
# using the same criteria for a clean data-flow).
# The reviewer's body carries `### P1 (N)` — parse N. If N > 0 → fail.
rule_p1_count() {
  local body_b64
  body_b64="$(
    jq -r --argjson ids "$DEEP_IDENTITIES_JSON" --arg m "$DEEP_MARKER" '
      [ .[]
        | . as $r
        | select(($r.user.login // "") as $l | $ids | index($l))
        | select((.body // "") | contains($m))
        | select((.state // "") != "DISMISSED")
      ]
      | last
      | if . == null then "" else (.body | @base64) end
    ' "$WORK/reviews.json"
  )"
  [[ -z "$body_b64" ]] && return 1  # rule 3 already caught this
  local body
  body="$(printf '%s' "$body_b64" | base64 -d)"

  # Match `### P1 (N)` — N is a nonneg integer. Regex tolerates optional
  # whitespace between the sev and the paren. Note: chaining `grep -Eo '[0-9]+'`
  # on the raw match would return `1` (from "P1") before `N` (from "(N)"), so
  # extract from inside the parens directly with sed.
  local n
  n="$(printf '%s\n' "$body" \
        | grep -Eo '###[[:space:]]+P1[[:space:]]*\([0-9]+\)' \
        | head -1 \
        | sed -E 's/.*\(([0-9]+)\).*/\1/')"
  n="${n:-0}"
  if [[ "$n" -gt 0 ]]; then
    set_result "failure" "$n unresolved P1$([[ $n -gt 1 ]] && echo 's')" \
      "Deep reviewer reports $n P1 finding(s) at HEAD. Fix or rebut before merge."
    return 0
  fi
  return 1
}

# --- Rule 5: P2/P3 orphans ---
# Every P2/P3 finding must be either:
#   (a) addressed — no longer present in the reviewer's HEAD read (reviewers
#       re-post fresh per push; a finding that disappeared is fixed), OR
#   (b) linked — a follow-up issue in the same repo is referenced in the PR
#       body, a PR comment, or an inline reply on the finding's own thread.
#       The issue must be OPEN or CLOSED-COMPLETED (not "not_planned") and
#       its body must reference the PR number or the finding's `path:line`
#       so we know the link is genuine.
#
# Inputs:
#   $WORK/findings.jsonl — one JSON per finding (deep + codex)
#   $WORK/pr_body.txt    — the PR body
#   $WORK/pr_comments.json — /issues/{N}/comments (excluding reviewer bots)
#   $WORK/review_thread_replies.json — inline replies on finding threads
#   $WORK/linked_issues/<N>.json     — issue detail cache (state, stateReason, body)
rule_p2p3_orphans() {
  if [[ ! -s "$WORK/findings.jsonl" ]]; then
    return 1
  fi

  # Collect all `#N` and OWNER/REPO issue URL refs from PR body + non-reviewer
  # comments. The result is a set of candidate issue numbers.
  local body="" comments=""
  [[ -f "$WORK/pr_body.txt" ]] && body="$(cat "$WORK/pr_body.txt")"
  if [[ -f "$WORK/pr_comments.json" ]]; then
    comments="$(jq -r '[.[].body // ""] | join("\n\n---\n\n")' "$WORK/pr_comments.json")"
  fi
  local scan="$body"$'\n'"$comments"

  # Extract candidate issue numbers.  Sources:
  #   - `resolves|fixes|closes|tracks|see|per|→|-> #123`
  #   - `https://github.com/OWNER/REPO/issues/123`
  # (issues/N is what we care about — PR URLs use /pull/, so we don't
  # collapse PRs into "linked".)
  local repo_re
  if [[ -n "${REPO:-}" ]]; then
    # Escape any regex-metachars in owner/name (unlikely but cheap).
    repo_re="$(printf '%s' "$REPO" | sed 's/[.[\*^$/]/\\&/g')"
  else
    repo_re="[^/]+/[^/]+"
  fi

  local body_refs url_refs
  body_refs="$(
    printf '%s\n' "$scan" \
      | grep -Eio '(resolves|fixes|closes|tracks|see|per|→|->)[[:space:]]*#[0-9]+' \
      | grep -Eo '#[0-9]+' \
      | grep -Eo '[0-9]+' \
      | sort -u
  )" || true
  url_refs="$(
    printf '%s\n' "$scan" \
      | grep -Eio "https://github\\.com/${repo_re}/issues/[0-9]+" \
      | grep -Eo '/issues/[0-9]+' \
      | grep -Eo '[0-9]+' \
      | sort -u
  )" || true

  local candidates
  candidates="$(printf '%s\n%s\n' "$body_refs" "$url_refs" | sort -u | grep -E '^[0-9]+$' || true)"

  # For each finding, decide handled vs orphan.
  local orphans_file="$WORK/orphans.txt"
  : > "$orphans_file"
  local orphan_count=0

  # Reduce findings to the set that is STILL present at HEAD — the input
  # jsonl already holds only HEAD findings (see collect_findings_from_*).
  local total_findings
  total_findings="$(wc -l < "$WORK/findings.jsonl" | tr -d ' ')"
  if [[ "$total_findings" -eq 0 ]]; then
    return 1
  fi

  # Loop over findings.
  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local path lineno sev title
    path="$(jq -r '.path // ""' <<<"$line")"
    lineno="$(jq -r '.line // ""' <<<"$line")"
    sev="$(jq -r '.severity // ""' <<<"$line")"
    title="$(jq -r '.title // ""' <<<"$line")"
    # Only P2/P3 count — P1 is handled by rule 4, P0 is treated as P1.
    if [[ "$sev" != "P2" && "$sev" != "P3" ]]; then
      continue
    fi

    local handled=0

    # Try each candidate issue.
    if [[ -n "$candidates" ]]; then
      while IFS= read -r n; do
        [[ -z "$n" ]] && continue
        local issue_file="$WORK/linked_issues/$n.json"
        [[ -f "$issue_file" ]] || continue
        local state state_reason ibody
        state="$(jq -r '.state // ""' "$issue_file" | tr '[:lower:]' '[:upper:]')"
        state_reason="$(jq -r '.stateReason // .state_reason // ""' "$issue_file" | tr '[:upper:]' '[:lower:]')"
        # Reject closed-not-planned.
        if [[ "$state" == "CLOSED" && "$state_reason" == "not_planned" ]]; then
          continue
        fi
        ibody="$(jq -r '.body // ""' "$issue_file")"
        # Body must reference this PR (#PR or PR permalink) OR the specific
        # path:line for the finding.
        local refs_pr=0 refs_pl=0
        if [[ -n "$PR" ]]; then
          if grep -Eq "(^|[^0-9a-zA-Z])#$PR([^0-9]|\$)|/pull/$PR([^0-9]|\$)" <<<"$ibody"; then
            refs_pr=1
          fi
        fi
        if [[ -n "$path" && -n "$lineno" && "$lineno" != "0" ]]; then
          # Match path:line with a non-digit / EOL boundary so 12 doesn't
          # match 120.
          local pl_re
          pl_re="$(printf '%s:%s' "$path" "$lineno" | sed 's/[.[\*^$/]/\\&/g')"
          if grep -Eq "${pl_re}([^0-9]|\$)" <<<"$ibody"; then
            refs_pl=1
          fi
        fi
        if [[ "$refs_pr" -eq 1 || "$refs_pl" -eq 1 ]]; then
          handled=1
          break
        fi
      done <<<"$candidates"
    fi

    if [[ "$handled" -eq 0 ]]; then
      orphan_count=$((orphan_count + 1))
      printf '%s:%s\n' "$path" "$lineno" >> "$orphans_file"
    fi
  done < "$WORK/findings.jsonl"

  if [[ "$orphan_count" -gt 0 ]]; then
    local first_three
    first_three="$(head -3 "$orphans_file" | tr '\n' ',' | sed 's/,$//; s/,/, /g')"
    set_result "failure" \
      "$orphan_count orphan P2/P3s: $first_three" \
      "$orphan_count P2/P3 finding(s) are neither addressed at HEAD nor linked to a follow-up issue. Address, or file & link an issue whose body references PR #$PR or the finding's path:line."
    return 0
  fi

  return 1
}

# ---------------------------------------------------------------------------
# Dispatcher: run rules in priority order until one fires, or succeed.
# ---------------------------------------------------------------------------
compute_gate() {
  rule_mergeability && return 0
  rule_checks && return 0
  rule_reviewer_freshness && return 0
  rule_p1_count && return 0
  rule_p2p3_orphans && return 0
  set_result "success" "all clear" \
    "Mergeable, checks green, deep reviewer approved at HEAD, no P1s, no orphan P2/P3s."
  return 0
}

# ---------------------------------------------------------------------------
# Real-run data gathering (skipped under --self-test).
# ---------------------------------------------------------------------------

# Collect deep reviewer's findings (P2/P3 only — P1 is rule 4's job) from the
# body's `### P2/P3 (N)` sections OR the review's inline comments. For the
# consolidated gate we walk the inline comments — refactor B moved per-finding
# detail there. The unanchored findings appended to the review body are
# captured too.
collect_deep_findings() {
  local pr="$1"
  local reviews_json="$WORK/reviews.json"
  local out="$WORK/deep-findings.jsonl"
  : > "$out"
  local review_id
  review_id="$(
    jq -r --argjson ids "$DEEP_IDENTITIES_JSON" --arg m "$DEEP_MARKER" '
      [ .[]
        | . as $r
        | select(($r.user.login // "") as $l | $ids | index($l))
        | select((.body // "") | contains($m))
        | select((.state // "") != "DISMISSED")
      ]
      | last
      | if . == null then "" else (.id | tostring) end
    ' "$reviews_json"
  )"
  [[ -z "$review_id" ]] && return 0
  local comments_json="$WORK/deep-review-comments.json"
  if ! gh api "/repos/$REPO/pulls/$pr/reviews/$review_id/comments" --paginate \
       > "$comments_json" 2>"$WORK/deep-review-comments.err"; then
    return 0
  fi
  jq -c '
    .[]
    | . as $c
    | ($c.body | capture("\\[P(?<n>[123])\\][[:space:]]+(?<title>[^\\n]+)")) as $m
    | select($m != null and $m.n != "1")
    | {
        pr: "'"$pr"'",
        reviewer: "claude",
        severity: ("P" + $m.n),
        path: ($c.path // ""),
        line: (($c.line // $c.original_line // 0) | tostring),
        title: ($m.title | gsub("^[[:space:]]+|[[:space:]]+$"; "")),
        comment_id: ($c.id | tostring),
        comment_url: ($c.html_url // "")
      }
  ' "$comments_json" >> "$out"
}

# Collect Codex line-badge findings visible at HEAD_SHA. We use GraphQL
# reviewThreads filtered by isResolved == false and commit.oid == HEAD_SHA
# so we don't count P2/P3s already resolved via the Files-changed UI or
# left behind on stale SHAs.
collect_codex_findings() {
  local pr="$1"
  local out="$WORK/codex-findings.jsonl"
  : > "$out"

  local codex_ids
  codex_ids="$(reviewer_identities codex "$REVIEWERS_CONFIG")"
  [[ -z "$codex_ids" ]] && return 0

  local head_sha
  head_sha="$(jq -r '.headSha // ""' "$WORK/pr.json")"

  # GraphQL — cursor-paginated reviewThreads with per-comment body/path/line.
  local owner name
  owner="${REPO%/*}"
  name="${REPO#*/}"
  local gql='
    query($owner:String!, $name:String!, $number:Int!, $cursor:String) {
      repository(owner:$owner, name:$name) {
        pullRequest(number:$number) {
          reviewThreads(first:100, after:$cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              isResolved
              comments(first:10) {
                nodes {
                  path
                  line
                  originalLine
                  body
                  url
                  databaseId
                  author { login }
                  commit { oid }
                }
              }
            }
          }
        }
      }
    }
  '
  local cursor="null"
  local page="$WORK/codex-page.json"
  local all="$WORK/codex-threads.json"
  echo '[]' > "$all"
  while : ; do
    local cursor_arg=""
    if [[ "$cursor" != "null" ]]; then
      cursor_arg="-F cursor=$cursor"
    fi
    # shellcheck disable=SC2086
    if ! gh api graphql -f query="$gql" -F owner="$owner" -F name="$name" \
         -F "number=$pr" $cursor_arg > "$page" 2>"$WORK/codex-page.err"; then
      # Codex is external — a fetch failure means we can't check its orphans
      # this run; don't hard-fail the gate, but log.
      echo "::warning::merge-gate: codex reviewThreads fetch failed" >&2
      return 0
    fi
    # Append threads to $all.
    jq -s '.[0] + [.[1].data.repository.pullRequest.reviewThreads.nodes[]?]' \
      "$all" "$page" > "$all.tmp" && mv "$all.tmp" "$all"
    local more end
    more="$(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage // false' "$page")"
    end="$(jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor // ""' "$page")"
    if [[ "$more" != "true" || -z "$end" ]]; then
      break
    fi
    cursor="\"$end\""
  done

  # Emit one finding per unresolved thread whose first codex comment carries
  # a P2/P3 badge and lives at HEAD.
  local identities_json
  identities_json="$(printf '%s' "$codex_ids" | jq -Rc 'split(",")')"

  jq -c --argjson ids "$identities_json" --arg head "$head_sha" '
    .[]
    | select(.isResolved == false)
    | .comments.nodes[0] as $c
    | select($c != null)
    | select(($c.author.login // "") as $l | $ids | index($l))
    | select($head == "" or $c.commit.oid == $head)
    | ($c.body | capture("P(?<n>[23])[[:space:]]*Badge")) as $m
    | select($m != null)
    | ($c.body | split("\n")[0]
        | gsub("\\*\\*"; "")
        | gsub("<[^>]+>"; "")
        | gsub("!\\[P[0-9] Badge\\]\\([^)]*\\)"; "")
        | gsub("^[[:space:]]+|[[:space:]]+$"; "")) as $title
    | {
        pr: "'"$pr"'",
        reviewer: "codex",
        severity: ("P" + $m.n),
        path: ($c.path // ""),
        line: (($c.line // $c.originalLine // 0) | tostring),
        title: $title,
        comment_id: ($c.databaseId | tostring),
        comment_url: ($c.url // "")
      }
  ' "$all" >> "$out"
}

# Cache linked-issue detail (state, stateReason, body) for the numbers we
# saw referenced in the PR context.
cache_linked_issues() {
  local pr="$1"
  local dir="$WORK/linked_issues"
  mkdir -p "$dir"
  # Collect refs from body + comments.
  local body="" comments=""
  [[ -f "$WORK/pr_body.txt" ]] && body="$(cat "$WORK/pr_body.txt")"
  if [[ -f "$WORK/pr_comments.json" ]]; then
    comments="$(jq -r '[.[].body // ""] | join("\n\n---\n\n")' "$WORK/pr_comments.json")"
  fi
  local scan="$body"$'\n'"$comments"
  local repo_re
  if [[ -n "$REPO" ]]; then
    repo_re="$(printf '%s' "$REPO" | sed 's/[.[\*^$/]/\\&/g')"
  else
    repo_re="[^/]+/[^/]+"
  fi
  local nums
  nums="$(
    {
      printf '%s\n' "$scan" \
        | grep -Eio '(resolves|fixes|closes|tracks|see|per|→|->)[[:space:]]*#[0-9]+' \
        | grep -Eo '#[0-9]+' | grep -Eo '[0-9]+'
      printf '%s\n' "$scan" \
        | grep -Eio "https://github\\.com/${repo_re}/issues/[0-9]+" \
        | grep -Eo '/issues/[0-9]+' | grep -Eo '[0-9]+'
    } 2>/dev/null | sort -u
  )"
  local n
  for n in $nums; do
    [[ "$n" == "$pr" ]] && continue  # skip self-ref
    local f="$dir/$n.json"
    [[ -f "$f" ]] && continue
    if ! gh issue view "$n" --repo "$REPO" \
         --json state,stateReason,body,number \
         > "$f" 2>"$WORK/issue-$n.err"; then
      # Not an issue (might be a PR or nonexistent). Skip silently.
      rm -f "$f"
    fi
  done
}

# ---------------------------------------------------------------------------
# Status + comment posting
# ---------------------------------------------------------------------------

post_status() {
  local sha="$1" state="$2" desc="$3"
  local payload
  payload="$(jq -cn --arg s "$state" --arg d "$desc" --arg c "merge-gate" \
               '{state:$s, description:$d, context:$c}')"
  gh api "/repos/$REPO/statuses/$sha" -X POST --input - <<<"$payload" >/dev/null
}

format_gate_comment() {
  local state="$1" desc="$2" long="$3" sha="$4"
  {
    echo "<!-- merge-gate -->"
    echo
    echo "## merge-gate — $state"
    echo
    echo "**short:** $desc"
    echo
    [[ -n "$long" ]] && { echo "**detail:** $long"; echo; }
    if [[ -n "$sha" ]]; then
      echo "**HEAD:** \`$sha\`"
      echo
    fi
    if [[ -f "$WORK/orphans.txt" && -s "$WORK/orphans.txt" ]]; then
      echo "### unresolved P2/P3 orphans"
      echo
      while IFS= read -r pl; do echo "- \`$pl\`"; done < "$WORK/orphans.txt"
      echo
    fi
    echo "_priority: mergeability > checks > freshness > P1 > P2/P3 orphans_"
    echo
    echo "_config: \`.github/reviewers.yml\` (edit that file to add/rename reviewers)_"
  }
}

upsert_gate_comment() {
  local pr="$1" state="$2" desc="$3" long="$4" sha="$5"
  local comment_file="$WORK/gate-comment.md"
  format_gate_comment "$state" "$desc" "$long" "$sha" > "$comment_file"

  # Find prior gate comment (any author — GitHub Actions bots may post).
  local existing_id
  existing_id="$(
    gh api "/repos/$REPO/issues/$pr/comments" --paginate \
      --jq '[.[] | select((.body // "") | contains("<!-- merge-gate -->"))] | last | .id // empty'
  )" || true

  if [[ -n "$existing_id" ]]; then
    gh api "/repos/$REPO/issues/comments/$existing_id" -X PATCH \
      -F body=@"$comment_file" >/dev/null
  else
    gh api "/repos/$REPO/issues/$pr/comments" -X POST \
      -F body=@"$comment_file" >/dev/null
  fi
}

# ---------------------------------------------------------------------------
# --self-test: fixture-based coverage of every priority rule.
# ---------------------------------------------------------------------------
run_self_test() {
  local failures=0

  # Fixture-mode reviewer config.
  DEEP_MARKER="<!-- reviewer:claude -->"
  DEEP_FAILURE_MARKER="<!-- reviewer:claude-failure -->"
  DEEP_IDENTITIES_JSON='["quibble-review[bot]","github-actions[bot]"]'
  REPO="swamikit/swami"
  PR="999"

  assert_state() {
    local label="$1" want_state="$2" want_desc_substr="$3"
    if [[ "$RESULT_STATE" != "$want_state" ]]; then
      printf '  FAIL  %s  (want state=%s, got %s; desc=%q)\n' \
        "$label" "$want_state" "$RESULT_STATE" "$RESULT_DESC"
      failures=$((failures + 1))
      return
    fi
    if [[ -n "$want_desc_substr" && "$RESULT_DESC" != *"$want_desc_substr"* ]]; then
      printf '  FAIL  %s  (state=%s ok; desc %q missing substring %q)\n' \
        "$label" "$want_state" "$RESULT_DESC" "$want_desc_substr"
      failures=$((failures + 1))
      return
    fi
    printf '  PASS  %s  (state=%s, desc=%q)\n' "$label" "$RESULT_STATE" "$RESULT_DESC"
  }

  reset_work() {
    rm -rf "$WORK"
    mkdir -p "$WORK/linked_issues"
    : > "$WORK/findings.jsonl"
    : > "$WORK/pr_body.txt"
    echo '[]' > "$WORK/pr_comments.json"
    echo '[]' > "$WORK/reviews.json"
    echo '[]' > "$WORK/failures.json"
    RESULT_STATE=""; RESULT_DESC=""; RESULT_LONG=""
  }

  echo "merge-gate --self-test: priority rules + address-vs-link semantics"
  echo

  # ---- Case 1: merge conflict ---------------------------------------------
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "CONFLICTING", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  compute_gate
  assert_state "1  merge conflict → failure" failure "merge-conflict"

  # ---- Case 2: failing required check --------------------------------------
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [
    {"name":"verify","conclusion":"SUCCESS"},
    {"name":"lint","conclusion":"FAILURE"}
  ] }
JSON
  compute_gate
  assert_state "2  failing check → failure" failure "check lint"

  # ---- Case 3: missing deep review → pending -------------------------------
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  # reviews.json is empty [] from reset_work.
  compute_gate
  assert_state "3  no deep review → pending" pending "waiting for deep reviewer"

  # ---- Case 3b: failure marker at HEAD → pending "waiting for reviewer" ---
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  cat > "$WORK/failures.json" <<'JSON'
[{
  "user": {"login": "quibble-review[bot]"},
  "body": "<!-- reviewer:claude-failure -->\n\nHEAD: `abc123`\n\n_reviewer failed — no findings this run._"
}]
JSON
  compute_gate
  assert_state "3b failure marker at HEAD → pending" pending "waiting for reviewer to succeed"

  # ---- Case 4: P1 count > 0 → failure -------------------------------------
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  cat > "$WORK/reviews.json" <<'JSON'
[{
  "id": 1,
  "state": "CHANGES_REQUESTED",
  "commit_id": "abc123",
  "user": {"login": "quibble-review[bot]"},
  "body": "<!-- reviewer:claude -->\n\n## Claude review\n\nverdict: **request changes**\n\n### P1 (2)\n### P2 (0)\n### P3 (0)\n"
}]
JSON
  compute_gate
  # Rule 3 fires first on CHANGES_REQUESTED (freshness rule), so verify that.
  assert_state "4  deep CHANGES_REQUESTED → failure" failure "deep reviewer requested changes"

  # ---- Case 4b: APPROVED but P1 count>0 (shouldn't happen but must fail) --
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  cat > "$WORK/reviews.json" <<'JSON'
[{
  "id": 1,
  "state": "APPROVED",
  "commit_id": "abc123",
  "user": {"login": "quibble-review[bot]"},
  "body": "<!-- reviewer:claude -->\n\n## Claude review\n\nverdict: **approve**\n\n### P1 (1)\n### P2 (0)\n### P3 (0)\n"
}]
JSON
  compute_gate
  assert_state "4b P1 count > 0 despite APPROVE → failure" failure "1 unresolved P1"

  # ---- Case 5a: orphan P2 finding, no link → failure ----------------------
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  cat > "$WORK/reviews.json" <<'JSON'
[{
  "id": 1,
  "state": "APPROVED",
  "commit_id": "abc123",
  "user": {"login": "quibble-review[bot]"},
  "body": "<!-- reviewer:claude -->\n\n## Claude review\n\nverdict: **approve**\n\n### P1 (0)\n### P2 (1)\n### P3 (0)\n"
}]
JSON
  cat > "$WORK/findings.jsonl" <<'JSONL'
{"pr":"999","reviewer":"claude","severity":"P2","path":"scripts/foo.sh","line":"42","title":"unclear naming","comment_id":"c1","comment_url":""}
JSONL
  compute_gate
  assert_state "5a orphan P2 → failure" failure "orphan P2/P3s"

  # ---- Case 5b: addressed-by-disappearance (finding not in findings.jsonl) -
  #      Simulate: reviewer's HEAD read has zero P2s → findings.jsonl empty
  #      → rule passes through, gate succeeds.
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  cat > "$WORK/reviews.json" <<'JSON'
[{
  "id": 1,
  "state": "APPROVED",
  "commit_id": "abc123",
  "user": {"login": "quibble-review[bot]"},
  "body": "<!-- reviewer:claude -->\n\n## Claude review\n\nverdict: **approve**\n\n### P1 (0)\n### P2 (0)\n### P3 (0)\n"
}]
JSON
  # findings.jsonl empty on purpose — the previous-push finding disappeared.
  compute_gate
  assert_state "5b addressed by disappearance → success" success "all clear"

  # ---- Case 5c: linked with verified body reference → success --------------
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  cat > "$WORK/reviews.json" <<'JSON'
[{
  "id": 1,
  "state": "APPROVED",
  "commit_id": "abc123",
  "user": {"login": "quibble-review[bot]"},
  "body": "<!-- reviewer:claude -->\n\n## Claude review\n\nverdict: **approve**\n\n### P1 (0)\n### P2 (1)\n### P3 (0)\n"
}]
JSON
  cat > "$WORK/findings.jsonl" <<'JSONL'
{"pr":"999","reviewer":"claude","severity":"P2","path":"scripts/foo.sh","line":"42","title":"unclear naming","comment_id":"c1","comment_url":""}
JSONL
  # PR body links tracks #123.
  printf 'Some PR body. Tracks #123 for the P2 follow-up.\n' > "$WORK/pr_body.txt"
  # Issue #123 open, body references this PR and the path:line.
  cat > "$WORK/linked_issues/123.json" <<JSON
{"number":123,"state":"OPEN","stateReason":null,"body":"Follow-up from PR #$PR — scripts/foo.sh:42 unclear naming."}
JSON
  compute_gate
  assert_state "5c linked with verified body ref → success" success "all clear"

  # ---- Case 5d: linked, issue is not-planned → still orphan ---------------
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  cat > "$WORK/reviews.json" <<'JSON'
[{
  "id": 1,
  "state": "APPROVED",
  "commit_id": "abc123",
  "user": {"login": "quibble-review[bot]"},
  "body": "<!-- reviewer:claude -->\n\n## Claude review\n\nverdict: **approve**\n\n### P1 (0)\n### P2 (1)\n### P3 (0)\n"
}]
JSON
  cat > "$WORK/findings.jsonl" <<'JSONL'
{"pr":"999","reviewer":"claude","severity":"P2","path":"scripts/foo.sh","line":"42","title":"unclear naming","comment_id":"c1","comment_url":""}
JSONL
  printf 'PR body: Tracks #123.\n' > "$WORK/pr_body.txt"
  cat > "$WORK/linked_issues/123.json" <<JSON
{"number":123,"state":"CLOSED","stateReason":"not_planned","body":"Won't do — PR #$PR — scripts/foo.sh:42."}
JSON
  compute_gate
  assert_state "5d linked but not-planned → still orphan" failure "orphan P2/P3s"

  # ---- Case 5e: linked but issue body doesn't reference PR/path:line ------
  reset_work
  cat > "$WORK/pr.json" <<'JSON'
{ "mergeable": "MERGEABLE", "headSha": "abc123",
  "statusCheckRollup": [{"name":"verify","conclusion":"SUCCESS"}] }
JSON
  cat > "$WORK/reviews.json" <<'JSON'
[{
  "id": 1,
  "state": "APPROVED",
  "commit_id": "abc123",
  "user": {"login": "quibble-review[bot]"},
  "body": "<!-- reviewer:claude -->\n\n## Claude review\n\nverdict: **approve**\n\n### P1 (0)\n### P2 (1)\n### P3 (0)\n"
}]
JSON
  cat > "$WORK/findings.jsonl" <<'JSONL'
{"pr":"999","reviewer":"claude","severity":"P2","path":"scripts/foo.sh","line":"42","title":"unclear naming","comment_id":"c1","comment_url":""}
JSONL
  printf 'PR body: Tracks #124.\n' > "$WORK/pr_body.txt"
  cat > "$WORK/linked_issues/124.json" <<'JSON'
{"number":124,"state":"OPEN","stateReason":null,"body":"Some unrelated tracking issue. No back-ref."}
JSON
  compute_gate
  assert_state "5e linked but unverifiable → orphan" failure "orphan P2/P3s"

  # ---- Case 6: config parser round-trip ------------------------------------
  local cfg="$WORK/reviewers.yml"
  cat > "$cfg" <<'YAML'
reviewers:
  - id: claude
    identities:
      - quibble-review[bot]
      - github-actions[bot]
    marker: "<!-- reviewer:claude -->"
    failure_marker: "<!-- reviewer:claude-failure -->"
    style: reviews-api
    gates_merge: true
  - id: fast
    identities:
      - quibble-review[bot]
      - github-actions[bot]
    marker: "<!-- reviewer:fast -->"
    failure_marker: "<!-- reviewer:fast-failure -->"
    style: reviews-api
    gates_merge: false
  - id: codex
    identities:
      - chatgpt-codex-connector[bot]
    marker: null
    failure_marker: null
    style: reviews-api-line-badges
    gates_merge: false
YAML
  local rows
  rows="$(parse_reviewers "$cfg")"
  if [[ "$(printf '%s\n' "$rows" | wc -l | tr -d ' ')" == "3" ]]; then
    printf '  PASS  6a config parser emits 3 rows\n'
  else
    printf '  FAIL  6a config parser row count: got %d rows\n' \
      "$(printf '%s\n' "$rows" | wc -l | tr -d ' ')"
    failures=$((failures + 1))
  fi
  local claude_ids
  claude_ids="$(printf '%s\n' "$rows" | awk -F'\t' '$1=="claude"{print $2}')"
  if [[ "$claude_ids" == "quibble-review[bot],github-actions[bot]" ]]; then
    printf '  PASS  6b claude identities parsed\n'
  else
    printf '  FAIL  6b claude identities: %q\n' "$claude_ids"
    failures=$((failures + 1))
  fi
  local codex_marker
  codex_marker="$(printf '%s\n' "$rows" | awk -F'\t' '$1=="codex"{print $3}')"
  if [[ "$codex_marker" == "null" ]]; then
    printf '  PASS  6c codex marker is null\n'
  else
    printf '  FAIL  6c codex marker: %q\n' "$codex_marker"
    failures=$((failures + 1))
  fi

  echo
  if [[ $failures -eq 0 ]]; then
    echo "merge-gate --self-test: OK (all cases passed)"
    return 0
  else
    echo "merge-gate --self-test: FAILED ($failures case(s))"
    return 1
  fi
}

if [[ "$SELF_TEST" -eq 1 ]]; then
  # Ensure default deep-reviewer vars exist for the fixture path.
  DEEP_MARKER="${DEEP_MARKER:-<!-- reviewer:claude -->}"
  DEEP_FAILURE_MARKER="${DEEP_FAILURE_MARKER:-<!-- reviewer:claude-failure -->}"
  DEEP_IDENTITIES_JSON="${DEEP_IDENTITIES_JSON:-[\"quibble-review[bot]\",\"github-actions[bot]\"]}"
  run_self_test
  exit $?
fi

# ---------------------------------------------------------------------------
# Real path
# ---------------------------------------------------------------------------
if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json owner,name -q '.owner.login + "/" + .name')"
fi

# Load deep reviewer config.
DEEP_MARKER="$(reviewer_marker claude "$REVIEWERS_CONFIG")"
DEEP_FAILURE_MARKER="$(reviewer_failure_marker claude "$REVIEWERS_CONFIG")"
DEEP_IDS_CSV="$(reviewer_identities claude "$REVIEWERS_CONFIG")"
if [[ -z "$DEEP_MARKER" || -z "$DEEP_IDS_CSV" ]]; then
  echo "::error::merge-gate: reviewers.yml missing 'claude' reviewer or its fields" >&2
  # Fail-closed on parse errors so a broken config never silently greens the gate.
  exit 3
fi
DEEP_IDENTITIES_JSON="$(printf '%s' "$DEEP_IDS_CSV" | jq -Rc 'split(",")')"

# Fetch PR context we need for every rule.
mkdir -p "$WORK/linked_issues"
if ! gh pr view "$PR" --repo "$REPO" \
     --json number,headRefOid,mergeable,mergeStateStatus,statusCheckRollup,body \
     > "$WORK/pr_raw.json" 2>"$WORK/pr.err"; then
  echo "::error::merge-gate: gh pr view failed — $(head -1 "$WORK/pr.err")" >&2
  # Fail-closed.
  exit 4
fi
jq '{mergeable, mergeStateStatus, statusCheckRollup, headSha: .headRefOid, number}' \
  "$WORK/pr_raw.json" > "$WORK/pr.json"
jq -r '.body // ""' "$WORK/pr_raw.json" > "$WORK/pr_body.txt"

# Prefer explicit --head-sha over the fetched one.
if [[ -z "$HEAD_SHA" ]]; then
  HEAD_SHA="$(jq -r '.headSha // ""' "$WORK/pr.json")"
fi

# Reviews API.
if ! gh api "/repos/$REPO/pulls/$PR/reviews" --paginate \
     > "$WORK/reviews.json" 2>"$WORK/reviews.err"; then
  echo "::warning::merge-gate: /pulls/$PR/reviews fetch failed — treating as no reviews" >&2
  echo '[]' > "$WORK/reviews.json"
fi

# Issue comments (for failure marker + linked-issue candidates + reviewer replies).
if ! gh api "/repos/$REPO/issues/$PR/comments" --paginate \
     > "$WORK/failures.json" 2>"$WORK/failures.err"; then
  echo '[]' > "$WORK/failures.json"
fi
# Filter comments EXCLUDING reviewer bot identities (avoid a reviewer bot
# "linking" to its own sibling issue counting as a followup).
all_ids_csv="$(parse_reviewers "$REVIEWERS_CONFIG" | awk -F'\t' '{print $2}' | tr ',' '\n' | sort -u | tr '\n' ',')"
all_ids_json="$(printf '%s' "${all_ids_csv%,}" | jq -Rc 'split(",")')"
jq --argjson ids "$all_ids_json" \
  '[.[] | . as $c | select(($c.user.login // "") as $l | ($ids | index($l)) | not)]' \
  "$WORK/failures.json" > "$WORK/pr_comments.json"

# Collect findings (deep + codex).
collect_deep_findings "$PR"
collect_codex_findings "$PR"
cat "$WORK/deep-findings.jsonl" "$WORK/codex-findings.jsonl" 2>/dev/null \
  > "$WORK/findings.jsonl" || true

# Cache linked issues for rule 5.
cache_linked_issues "$PR"

# Compute + post.
compute_gate

echo "merge-gate: PR #$PR HEAD=$HEAD_SHA state=$RESULT_STATE desc=\"$RESULT_DESC\""

if [[ -n "$HEAD_SHA" ]]; then
  post_status "$HEAD_SHA" "$RESULT_STATE" "$RESULT_DESC"
else
  echo "::warning::merge-gate: no HEAD_SHA — cannot POST commit status" >&2
fi
upsert_gate_comment "$PR" "$RESULT_STATE" "$RESULT_DESC" "$RESULT_LONG" "$HEAD_SHA"

# Exit 0 always on the real path — CI decision is the posted status, not the
# script's exit code. Fail-closed exits above (missing config, unfetchable PR)
# already returned non-zero before reaching here.
exit 0
