#!/usr/bin/env bash
#
# audit-p2s.sh — for every PR merged since --since (default: today), collect
# every P2/P3 finding left on it by BOTH reviewers (Codex line comments +
# Quibble review), decide whether each finding is already tracked by a
# repo issue, and print the orphans. With --file-issues, open one issue per
# orphan.
#
# The earlier audit missed all of PR #58's Claude P2/P3 findings because it
# only walked Codex line comments. This script walks BOTH reviewers off the
# same code so the next run cannot repeat that gap.
#
# Usage:
#   scripts/audit-p2s.sh [--since YYYY-MM-DD] [--file-issues] [--repo OWNER/REPO]
#   scripts/audit-p2s.sh --self-test
#
# Dependencies: bash 4+, gh, jq. No Python.  --self-test needs only jq.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
SINCE="$(date -u +%Y-%m-%d)"
FILE_ISSUES=0
REPO=""
SELF_TEST=0

usage() {
  sed -n '2,22p' "$0"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --since)        SINCE="${2:-}"; shift 2 ;;
    --file-issues)  FILE_ISSUES=1; shift ;;
    --repo)         REPO="${2:-}"; shift 2 ;;
    --self-test)    SELF_TEST=1; shift ;;
    -h|--help)      usage ;;
    *)              echo "unknown arg: $1" >&2; usage ;;
  esac
done

if [[ "$SELF_TEST" -eq 0 ]]; then
  if ! [[ "$SINCE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "audit-p2s: --since must be YYYY-MM-DD (got: $SINCE)" >&2
    exit 2
  fi

  if [[ -z "$REPO" ]]; then
    REPO="$(gh repo view --json owner,name -q '.owner.login + "/" + .name')"
  fi
fi

for tool in jq; do
  command -v "$tool" >/dev/null 2>&1 || { echo "audit-p2s: missing $tool" >&2; exit 2; }
done
if [[ "$SELF_TEST" -eq 0 ]]; then
  command -v gh >/dev/null 2>&1 || { echo "audit-p2s: missing gh" >&2; exit 2; }
fi

# ---------------------------------------------------------------------------
# Working state
# ---------------------------------------------------------------------------
WORK="$(mktemp -d -t audit-p2s.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

FINDINGS="$WORK/findings.jsonl"          # one JSON object per finding
ORPHANS="$WORK/orphans.jsonl"            # subset that are un-tracked
: > "$FINDINGS"
: > "$ORPHANS"

# PRs whose reviewer-comment fetches errored out (auth, rate, 404, network).
# Reported in the SUMMARY so a partial audit can never look byte-identical
# to a clean one — that silent-zero was the whole failure class this script
# exists to prevent (see header comment).
FAILED_FETCHES=()

# Preload every open+closed issue title/body/URL once — searching per finding
# is O(findings × issues). One dump + jq greps stays under gh's rate limits
# on any realistic backlog. Skipped under --self-test (fixtures written later).
ISSUES_JSON="$WORK/issues.json"
if [[ "$SELF_TEST" -eq 0 ]]; then
  gh issue list --repo "$REPO" --state all --limit 500 \
    --json number,title,body,url,createdAt \
    > "$ISSUES_JSON"
fi

# False-positive patterns (see scripts/known-false-positives.txt).
FP_FILE="$(cd "$(dirname "$0")" && pwd)/known-false-positives.txt"
FP_PATTERNS=()
if [[ -f "$FP_FILE" ]]; then
  # shellcheck disable=SC2016
  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    FP_PATTERNS+=("$line")
  done < "$FP_FILE"
fi

is_false_positive() {
  local body="$1"
  local pat
  for pat in "${FP_PATTERNS[@]}"; do
    if printf '%s' "$body" | grep -qE -- "$pat"; then
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# Round-4 helpers: unique-per-finding markers + regex-boundary path:line
# match. See the block comment above is_addressed() below for the rationale.
# ---------------------------------------------------------------------------

# Escape a literal string so it is safe to embed as-is inside a jq/Oniguruma
# regex. Escapes: \ . ^ $ * + ? ( ) [ ] { } | — every char the regex engine
# treats specially. `{` and `}` cannot be written as literals inside the
# `pattern` half of `${var//pattern/repl}` (bash's parser bites), so route
# them through single-char variables.
regex_escape() {
  local s="$1"
  local lbrace='{' rbrace='}'
  s="${s//\\/\\\\}"
  s="${s//./\\.}"
  s="${s//\[/\\[}"
  s="${s//\]/\\]}"
  s="${s//(/\\(}"
  s="${s//)/\\)}"
  s="${s//^/\\^}"
  s="${s//\$/\\\$}"
  s="${s//\*/\\*}"
  s="${s//+/\\+}"
  s="${s//\?/\\?}"
  s="${s//$lbrace/\\$lbrace}"
  s="${s//$rbrace/\\$rbrace}"
  s="${s//|/\\|}"
  printf '%s' "$s"
}

# Slug a Claude finding title so it participates in a unique marker. Lower,
# non-alphanumeric to `-`, collapse, trim, cap at 40 chars so the marker line
# stays readable.
slugify_title() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | LC_ALL=C sed -e 's/[^a-z0-9]/-/g' -e 's/--*/-/g' -e 's/^-//' -e 's/-$//' \
    | cut -c1-40
}

# Compose the unique per-finding marker embedded in a filed issue's body.
#   Codex — comment_id is unique per line comment; use it.
#   Claude — one sticky carries N findings, so per-finding uniqueness has to
#            be synthesised: pr:sev:path:line:slug(title).
# Args: reviewer pr cid sev path line title
finding_marker() {
  local reviewer="$1" pr="$2" cid="$3" sev="$4" path="$5" line="$6" title="$7"
  case "$reviewer" in
    codex)
      printf '<!-- audit-p2s-marker: codex:%s -->' "$cid"
      ;;
    claude)
      local slug; slug="$(slugify_title "$title")"
      printf '<!-- audit-p2s-marker: claude:%s:%s:%s:%s:%s -->' \
        "$pr" "$sev" "$path" "$line" "$slug"
      ;;
    *)
      return 1
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Discover PRs merged since SINCE
# ---------------------------------------------------------------------------
PRS_JSON="$WORK/prs.json"
PR_NUMBERS=()
if [[ "$SELF_TEST" -eq 0 ]]; then
  gh pr list --repo "$REPO" --state merged --limit 100 \
    --json number,mergedAt,title,url,headRefOid \
    > "$PRS_JSON"

  # macOS ships bash 3.2 which lacks `mapfile` — read the numbers into an
  # array the portable way.
  while IFS= read -r _n; do
    [[ -n "$_n" ]] && PR_NUMBERS+=("$_n")
  done < <(
    jq -r --arg since "${SINCE}T00:00:00Z" \
      '.[] | select(.mergedAt >= $since) | .number' \
      "$PRS_JSON"
  )

  if [[ ${#PR_NUMBERS[@]} -eq 0 ]]; then
    echo "audit-p2s: no PRs merged since $SINCE — nothing to audit." >&2
    echo "SUMMARY total=0 addressed=0 orphans=0 filed=0 errors=0"
    exit 0
  fi

  echo "audit-p2s: auditing ${#PR_NUMBERS[@]} PR(s) merged since $SINCE in $REPO" >&2
fi

# ---------------------------------------------------------------------------
# Per-PR helpers
# ---------------------------------------------------------------------------

# Record a finding as JSONL. Args:
#   $1 pr   $2 reviewer   $3 severity   $4 path   $5 line
#   $6 comment_id   $7 comment_url   $8 title   $9 full body
record_finding() {
  local body="$9"
  if is_false_positive "$body"; then
    return 0
  fi
  jq -cn \
    --arg pr "$1" --arg reviewer "$2" --arg sev "$3" \
    --arg path "$4" --arg line "$5" \
    --arg cid "$6" --arg curl "$7" \
    --arg title "$8" --arg body "$body" \
    '{pr:$pr, reviewer:$reviewer, severity:$sev, path:$path, line:$line,
      comment_id:$cid, comment_url:$curl, title:$title, body:$body}' \
    >> "$FINDINGS"
}

# Codex line comments: each comment IS one finding; severity is encoded in
# the ![P2 Badge] / ![P3 Badge] shield near the top of the body.
collect_codex() {
  local pr="$1"
  local raw="$WORK/codex-$pr.json"
  local err="$WORK/codex-$pr.err"
  # Do NOT swallow gh errors: auth failure, rate limit, 404, or a network
  # blip must never look like "PR had no findings". Record the PR in
  # FAILED_FETCHES and let SUMMARY report errors=N.
  if ! gh api "/repos/$REPO/pulls/$pr/comments" --paginate > "$raw" 2>"$err"; then
    FAILED_FETCHES+=("codex:$pr")
    echo "audit-p2s: gh api pulls/$pr/comments FAILED — $(head -1 "$err" 2>/dev/null || echo 'no stderr')" >&2
    return 0
  fi

  # Filter to codex/chatgpt authors and P2|P3 badges, extract the fields we
  # need. Emits tab-separated: sev, path, line, id, url, title, body_b64.
  jq -r '
    .[]
    | select(.user.login | test("codex|chatgpt"; "i"))
    | . as $c
    | ($c.body | capture("P(?<n>[23]) Badge") ) as $m
    | ($c.body | split("\n")[0]
        | gsub("\\*\\*"; "")
        | gsub("<[^>]+>"; "")
        | gsub("!\\[P[0-9] Badge\\]\\([^)]*\\)"; "")
        | gsub("^[[:space:]]+|[[:space:]]+$"; "")) as $title
    | [ "P" + $m.n,
        ($c.path // ""),
        (($c.line // $c.original_line // 0) | tostring),
        ($c.id | tostring),
        $c.html_url,
        $title,
        ($c.body | @base64)
      ]
    | @tsv
  ' "$raw" | while IFS=$'\t' read -r sev path line cid curl title body_b64; do
    [[ -z "$sev" ]] && continue
    local body; body="$(printf '%s' "$body_b64" | base64 -d)"
    record_finding "$pr" "codex" "$sev" "$path" "$line" "$cid" "$curl" "$title" "$body"
  done
}

# Claude findings on a PR live in one of two places depending on when the PR
# was reviewed:
#
#   (A) NEW SHAPE (refactor B onward): a formal PR Review authored by
#       `quibble-review[bot]`. Its `body` still carries `### P1/P2/P3 (N)`
#       count headers so a merge-gate grep still works, but the per-finding
#       DETAIL lives in the review's inline `comments[]` collection —
#       `/pulls/{N}/reviews/{review_id}/comments`. Each inline comment
#       carries the `<!-- reviewer:claude:finding -->` marker.
#
#   (B) LEGACY SHAPE: a sticky ISSUE comment tagged `<!-- reviewer:claude -->`
#       (or the earlier `<!-- claude-review -->`) with `- **`path:line` —
#       [P2] title**` bullets under severity headers. Kept recognized for one
#       release so PRs merged before refactor B still audit.
#
# We try (A) first — if a bot-authored review with the marker exists on this
# PR, use it. Otherwise fall back to the sticky-issue path (B). This keeps
# backward compat across the transition; the sticky path can be removed a
# release after refactor B ships.
collect_claude() {
  local pr="$1"
  if collect_claude_review "$pr"; then
    return 0
  fi
  collect_claude_sticky "$pr"
}

latest_quibble_review_line() {
  local reviews_raw="$1"
  jq -r --arg login "quibble-review[bot]" '
    [ .[]
      | select(.user.login == $login)
      | select(.body // "" | contains("<!-- reviewer:claude -->"))
    ]
    | last
    | if . == null then empty else [(.id|tostring), (.body|@base64)] | @tsv end
  ' "$reviews_raw" 2>/dev/null | { head -1 || true; }
}

# NEW SHAPE — walk the latest bot-authored PR Review on the PR. Returns 0 if
# a review was found + walked (regardless of finding count), non-zero if no
# such review exists (so the caller falls through to the sticky path).
collect_claude_review() {
  local pr="$1"
  local reviews_raw="$WORK/claude-reviews-$pr.json"
  local err="$WORK/claude-reviews-$pr.err"

  if ! gh api "/repos/$REPO/pulls/$pr/reviews" --paginate > "$reviews_raw" 2>"$err"; then
    FAILED_FETCHES+=("claude:$pr")
    echo "audit-p2s: gh api pulls/$pr/reviews FAILED — $(head -1 "$err" 2>/dev/null || echo 'no stderr')" >&2
    # Signal "found path A but broken" so we do NOT fall through to sticky —
    # a partial audit lies about coverage if we do both paths on error.
    return 0
  fi

  # Pick the newest bot review whose body carries the reviewer:claude marker.
  # `.[]` iterates in server order (oldest→newest); take the last with |last.
  local review_line review_id review_body_b64
  review_line="$(latest_quibble_review_line "$reviews_raw")"
  [[ -z "$review_line" ]] && return 1

  IFS=$'\t' read -r review_id review_body_b64 <<<"$review_line" || true
  [[ -z "${review_id:-}" ]] && return 1

  local review_url="https://github.com/$REPO/pull/$pr#pullrequestreview-$review_id"

  # Pull the per-line comments attached to that review.
  local comments_raw="$WORK/claude-review-comments-$pr.json"
  local cerr="$WORK/claude-review-comments-$pr.err"
  if ! gh api "/repos/$REPO/pulls/$pr/reviews/$review_id/comments" --paginate > "$comments_raw" 2>"$cerr"; then
    FAILED_FETCHES+=("claude:$pr:review-comments")
    echo "audit-p2s: gh api pulls/$pr/reviews/$review_id/comments FAILED — $(head -1 "$cerr" 2>/dev/null || echo 'no stderr')" >&2
    return 0
  fi

  # Walk each inline comment. Each one is one finding. The first line of the
  # body has `[P<n>] <title>`; the remainder is reasoning + suggestion. Only
  # P2/P3 matter for orphan tracking (P1 blocks merge, so it never becomes a
  # merged-PR orphan — codex_collect drops them too).
  jq -r --arg finding_marker "<!-- reviewer:claude:finding -->" '
    .[]
    | select(.body // "" | contains($finding_marker))
    | . as $c
    | ($c.body | capture("\\[P(?<n>[23])\\][[:space:]]+(?<title>[^\\n]+)")) as $m
    | select($m != null)
    | [ "P" + $m.n,
        ($c.path // ""),
        (($c.line // $c.original_line // 0) | tostring),
        ($c.id | tostring),
        ($c.html_url // ""),
        ($m.title | gsub("^[[:space:]]+|[[:space:]]+$"; "")),
        ($c.body | @base64)
      ]
    | @tsv
  ' "$comments_raw" | while IFS=$'\t' read -r sev path line cid curl title body_b64; do
    [[ -z "$sev" ]] && continue
    local body; body="$(printf '%s' "$body_b64" | base64 -d)"
    # comment_id fed into finding_marker() is the review comment id — unique
    # per finding, so the audit-p2s marker never collides across findings.
    record_finding "$pr" "claude" "$sev" "$path" "$line" "$cid" "$curl" "$title" "$body"
  done
  return 0
}

# LEGACY SHAPE — sticky issue comment. Kept for backward compat with PRs
# merged before refactor B (issue #36) shipped. Findings live under
# `### P2 (N)` and `### P3 (N)` headers as `- **`path:line` — [P2] title**`
# bullets. Removed a release after refactor B stabilizes.
collect_claude_sticky() {
  local pr="$1"
  local raw="$WORK/claude-$pr.json"
  local err="$WORK/claude-$pr.err"
  # Same reasoning as collect_codex: never swallow the failure into a
  # silent zero. Record and continue so one bad PR does not blank the run.
  if ! gh api "/repos/$REPO/issues/$pr/comments" --paginate > "$raw" 2>"$err"; then
    FAILED_FETCHES+=("claude:$pr")
    echo "audit-p2s: gh api issues/$pr/comments FAILED — $(head -1 "$err" 2>/dev/null || echo 'no stderr')" >&2
    return 0
  fi

  # Find the sticky comment (there is at most one). `read` returning 1 (no
  # match) and `head` closing the pipe on jq (SIGPIPE) are both expected —
  # do not let `set -e` / `pipefail` treat them as script-fatal.
  local sticky_line sticky_id sticky_url sticky_body_b64
  sticky_line="$(
    jq -r '
      .[]
      | select(
          (.body | contains("<!-- reviewer:claude -->"))
          or (.body | contains("<!-- claude-review -->"))
        )
      | [(.id|tostring), .html_url, (.body|@base64)] | @tsv
    ' "$raw" 2>/dev/null | { head -1 || true; }
  )"
  [[ -z "$sticky_line" ]] && return 0
  IFS=$'\t' read -r sticky_id sticky_url sticky_body_b64 <<<"$sticky_line" || true
  [[ -z "${sticky_id:-}" ]] && return 0

  local sticky_body; sticky_body="$(printf '%s' "$sticky_body_b64" | base64 -d)"

  # Walk the sticky body line-by-line. State: current severity section, and
  # the currently-open finding (so we can append its reasoning/suggestion
  # sublines into the body we hand to record_finding).
  local sev="" cur_line="" cur_path="" cur_line_no="" cur_title="" cur_body=""

  flush_finding() {
    if [[ -n "$cur_line" && "$sev" =~ ^P[23]$ ]]; then
      record_finding "$pr" "claude" "$sev" "$cur_path" "$cur_line_no" \
        "$sticky_id" "$sticky_url" "$cur_title" "$cur_body"
    fi
    cur_line=""; cur_path=""; cur_line_no=""; cur_title=""; cur_body=""
  }

  while IFS= read -r ln; do
    if [[ "$ln" =~ ^\#\#\#[[:space:]]+(P[123])[[:space:]]*\( ]]; then
      flush_finding
      sev="${BASH_REMATCH[1]-}"
      continue
    fi
    if [[ "$ln" =~ ^\#\#[[:space:]] || "$ln" =~ ^_reviewer[[:space:]]skill ]]; then
      flush_finding
      sev=""
      continue
    fi
    # Finding bullet: - **`path:line` — [P2] title**
    if [[ "$ln" =~ ^-[[:space:]]+\*\*\`([^\`]+)\`[[:space:]]+.*\[(P[123])\][[:space:]]+(.+)\*\*[[:space:]]*$ ]]; then
      # Capture BASH_REMATCH BEFORE flush_finding — flush_finding's own
      # `[[ ... =~ ... ]]` clobbers the array, and the reset resurrected a
      # pre-lint-fix bug where every other finding lost its severity.
      local loc="${BASH_REMATCH[1]-}"
      local new_sev="${BASH_REMATCH[2]-}"
      local new_title="${BASH_REMATCH[3]-}"
      flush_finding
      cur_line="$ln"
      sev="$new_sev"
      cur_title="$new_title"
      if [[ "$loc" == *":"* ]]; then
        cur_path="${loc%:*}"
        cur_line_no="${loc##*:}"
      else
        cur_path="$loc"
        cur_line_no="0"
      fi
      cur_body="$ln"
      continue
    fi
    # Continuation sublines (indented `- ...`) belong to the open finding.
    if [[ -n "$cur_line" && "$ln" =~ ^[[:space:]]+- ]]; then
      cur_body+=$'\n'"$ln"
      continue
    fi
    # Blank line inside a section: close the finding but stay in-section.
    if [[ -z "${ln//[[:space:]]/}" ]]; then
      flush_finding
      continue
    fi
  done <<< "$sticky_body"
  flush_finding
}

# ---------------------------------------------------------------------------
# Addressed-ness check  (round-4 fix, PR #69)
# ---------------------------------------------------------------------------
#
# A finding is "addressed" if ANY of:
#   1. an issue's body carries THIS finding's unique audit-p2s marker
#      (see `finding_marker` above), OR
#   2. an issue that has NO audit-p2s marker mentions the exact `path:line`
#      as a regex-boundary match — i.e. legacy / hand-filed follow-ups.
#
# Two failure modes the previous `contains($pl)` matcher hit and this one
# closes (see round-4 review on PR #69):
#
#   (a) Substring collision. `"scripts/x.sh:120".contains("scripts/x.sh:12")`
#       is TRUE, so a finding at line 12 was reported addressed by an issue
#       about line 120. Fix: `test( <regex-escaped pl> + "(\\D|$)" )` — the
#       character after the line number must be non-digit or end-of-string.
#
#   (b) Same-anchor collapse. When Codex and Claude both flag the same
#       `path:line` (routine — PR #58 had multiple such), the first filed
#       issue's body carries that `path:line`, so every subsequent finding
#       at the same anchor looked addressed and got dropped. Fix: audit-
#       filed issues match ONLY on their per-finding marker; the fallback
#       `path:line` match runs only against issues that carry no marker at
#       all (legacy / hand-filed).
#
# We also do NOT treat "a later commit on the PR touched this file" as
# addressed: on merged PRs every commit is later than every review comment,
# so that heuristic evaluates to "always addressed". Issue-linkage is the
# honest signal.
#
# is_addressed <path> <line> <comment_url> <reviewer> <pr> <comment_id> <severity> <title>
is_addressed() {
  local path="$1" line="$2" curl="$3" reviewer="$4"
  local pr="${5:-}" cid="${6:-}" sev="${7:-}" title="${8:-}"
  local needle_pathline="${path}:${line}"
  local pl_re; pl_re="$(regex_escape "$needle_pathline")(\\D|\$)"
  local marker=""
  if [[ "$reviewer" == "codex" || "$reviewer" == "claude" ]]; then
    marker="$(finding_marker "$reviewer" "$pr" "$cid" "$sev" "$path" "$line" "$title")"
  fi
  jq -e --arg marker "$marker" --arg pl_re "$pl_re" '
    any(.[]?;
      (.body // "") as $b
      | (.title // "") as $t
      | ($b + "\n" + $t) as $bt
      | (
          # (1) exact per-finding marker match — always wins
          ($marker != "" and ($bt | contains($marker)))
          or
          # (2) legacy / hand-filed issue: no audit-p2s marker anywhere in
          #     the body, but it names the path:line with a regex boundary
          #     so 12 does not match 120.
          (
            (($bt | test("<!-- audit-p2s-marker:")) | not)
            and
            ($bt | test($pl_re))
          )
        )
    )
  ' "$ISSUES_JSON" >/dev/null
}

# ---------------------------------------------------------------------------
# --self-test: reproduce the round-4 false-positive cases and prove the fix
# ---------------------------------------------------------------------------
#
# Runs without gh — writes fixture issues into $ISSUES_JSON and asserts
# is_addressed's verdict on hand-crafted findings.
#
# Cases:
#   A) Substring collision (round-4 P1 case #1)
#      Existing issue mentions "scripts/x.sh:120".
#      New finding is at "scripts/x.sh:12".
#      OLD contains() → true (WRONG — different lines).
#      NEW test() with boundary → false.
#
#   B) Same-anchor collapse (round-4 P1 case #2)
#      Codex and Claude both flag "scripts/audit-p2s.sh:100" with different
#      titles. First (Claude, title A) is filed with its per-finding marker.
#      OLD contains() → the second one (Claude, title B) matches on the
#      first's path:line → dropped.
#      NEW → second finding's marker is different, so no marker match; the
#      first issue carries an audit-p2s marker so the legacy path:line
#      fallback ignores it → NOT addressed.
#
#   C) Legacy hand-filed issue (backward compat)
#      Issue with no audit-p2s marker mentions "scripts/x.sh:12" cleanly.
#      New finding at scripts/x.sh:12 → addressed via legacy fallback.
#
#   D) Exact codex marker match
#      Issue carries "<!-- audit-p2s-marker: codex:999 -->".
#      New codex finding with comment_id=999 → addressed.
#      Different codex finding with comment_id=1000 at same path:line
#      → NOT addressed (marker differs, legacy fallback skipped because
#      the issue has an audit marker).
run_self_test() {
  local failures=0

  # Fixture: four issues covering all four cases.
  #  * issue #1 = filed-by-audit Claude marker for scripts/audit-p2s.sh:100
  #               title "anchor first" (used for case B / B')
  #  * issue #2 = hand-filed legacy issue naming "scripts/collide.sh:120"
  #               (case A: must NOT match a finding at :12)
  #  * issue #3 = hand-filed legacy issue naming "scripts/legacy.sh:12"
  #               (case C: SHOULD match a finding at :12)
  #  * issue #4 = filed-by-audit Codex marker for comment_id 999
  #               (case D / D')
  cat > "$ISSUES_JSON" <<'JSON'
[
  {
    "number": 1,
    "title": "[P2] scripts/audit-p2s.sh:100 — anchor first (from PR #69)",
    "body": "<!-- audit-p2s-marker: claude:69:P2:scripts/audit-p2s.sh:100:anchor-first -->\n\n**Source**: claude P2 on PR #69 — `scripts/audit-p2s.sh:100`.\n",
    "url": "https://example/1",
    "createdAt": "2026-09-04T00:00:00Z"
  },
  {
    "number": 2,
    "title": "Follow-up on line 120",
    "body": "See scripts/collide.sh:120 for the failing line. No audit marker here on purpose.",
    "url": "https://example/2",
    "createdAt": "2026-09-04T00:00:00Z"
  },
  {
    "number": 3,
    "title": "Legacy hand-filed for scripts/legacy.sh:12",
    "body": "Please fix the check at scripts/legacy.sh:12 — legacy filing, no audit marker.",
    "url": "https://example/3",
    "createdAt": "2026-09-04T00:00:00Z"
  },
  {
    "number": 4,
    "title": "[P2] scripts/audit-p2s.sh:200 — codex marker (from PR #69)",
    "body": "<!-- audit-p2s-marker: codex:999 -->\n\ncodex comment 999 body\n",
    "url": "https://example/4",
    "createdAt": "2026-09-04T00:00:00Z"
  }
]
JSON

  # Test harness: expect is_addressed to succeed (0) or fail (1).
  # Args: label expect_addressed reviewer path line curl pr cid sev title
  assert_addressed() {
    local label="$1" expect="$2"
    local reviewer="$3" path="$4" line="$5" curl="$6"
    local pr="$7" cid="$8" sev="$9" title="${10}"
    local rc=0
    is_addressed "$path" "$line" "$curl" "$reviewer" \
                 "$pr" "$cid" "$sev" "$title" \
      >/dev/null 2>&1 || rc=$?
    local got="addressed"
    [[ $rc -ne 0 ]] && got="orphan"
    local want="orphan"
    [[ "$expect" == "1" ]] && want="addressed"
    if [[ "$got" == "$want" ]]; then
      printf '  PASS  %s  (got %s)\n' "$label" "$got"
    else
      printf '  FAIL  %s  (want %s, got %s)\n' "$label" "$want" "$got"
      failures=$((failures + 1))
    fi
  }

  echo "audit-p2s --self-test: is_addressed round-4 cases"
  echo

  # ---- Case A: substring collision (previously false positive) --------------
  # Old contains("scripts/collide.sh:12") would match issue #2's
  # "scripts/collide.sh:120". New regex-boundary must NOT match — finding
  # is an orphan.
  assert_addressed \
    "A  numeric-prefix collision (line 12 vs line 120): must be ORPHAN" \
    0  codex  "scripts/collide.sh"  "12"  "https://c/1"  70  555  P2  "boundary test"

  # ---- Case B: same-anchor collapse (previously false positive) -------------
  # Issue #1 was filed by audit for a Claude finding at :100 title 'anchor first'.
  # A DIFFERENT Claude finding at the same :100 must NOT be marked addressed.
  assert_addressed \
    "B  same-anchor Claude finding, different title: must be ORPHAN" \
    0  claude  "scripts/audit-p2s.sh"  "100"  ""  69  0  P2  "second finding same anchor"

  # And the ORIGINAL finding is still addressed by its own marker.
  assert_addressed \
    "B' original Claude finding, exact marker: must be ADDRESSED" \
    1  claude  "scripts/audit-p2s.sh"  "100"  ""  69  0  P2  "anchor first"

  # ---- Case C: legacy hand-filed issue matches its path:line ----------------
  assert_addressed \
    "C  legacy issue naming scripts/legacy.sh:12 (no marker): must be ADDRESSED" \
    1  claude  "scripts/legacy.sh"  "12"  ""  70  0  P2  "any legacy title"

  # ---- Case D: exact codex marker match, and marker isolation ---------------
  assert_addressed \
    "D  codex finding with cid 999 (marker match): must be ADDRESSED" \
    1  codex  "scripts/audit-p2s.sh"  "200"  "https://c/999"  69  999  P2  "codex 999"

  # Different cid at same path:line must NOT collapse onto issue #4's marker.
  # Issue #4 carries an audit-p2s marker so legacy fallback is skipped.
  assert_addressed \
    "D' codex finding with cid 1000 same path:line: must be ORPHAN" \
    0  codex  "scripts/audit-p2s.sh"  "200"  "https://c/1000"  69  1000  P2  "codex 1000"

  # ---- Case E: display prose is not a parser key --------------------------
  cat > "$WORK/review-contract.json" <<'JSON'
[
  {"id": 7, "user": {"login": "quibble-review[bot]"}, "body": "<!-- reviewer:claude -->\n\n## Quibble Review Summary\n\nstatus: **approve**\n\n### P1 (0)"},
  {"id": 8, "user": {"login": "someone-else"}, "body": "<!-- reviewer:claude -->\n\n## Anything"},
  {"id": 9, "user": {"login": "quibble-review[bot]"}, "body": "<!-- reviewer:claude -->\n\n## Legacy display heading\n\nlegacy-label: **approve**\n\n### P1 (0)"}
]
JSON
  local selected_review
  selected_review="$(latest_quibble_review_line "$WORK/review-contract.json" | cut -f1)"
  if [[ "$selected_review" == "9" ]]; then
    printf '  PASS  E  Quibble selection keys on identity and marker, not heading/status prose\n'
  else
    printf '  FAIL  E  Quibble selection returned review %q\n' "$selected_review"
    failures=$((failures + 1))
  fi

  echo
  if [[ $failures -eq 0 ]]; then
    echo "audit-p2s --self-test: OK (all cases passed)"
    return 0
  else
    echo "audit-p2s --self-test: FAILED ($failures case(s))"
    return 1
  fi
}

if [[ "$SELF_TEST" -eq 1 ]]; then
  run_self_test
  exit $?
fi

# ---------------------------------------------------------------------------
# Collect findings for every PR
# ---------------------------------------------------------------------------
for pr in "${PR_NUMBERS[@]}"; do
  collect_codex "$pr"
  collect_claude "$pr"
done

TOTAL="$(wc -l < "$FINDINGS" | tr -d ' ')"
ERRORS="${#FAILED_FETCHES[@]}"
if [[ "$TOTAL" -eq 0 ]]; then
  if [[ "$ERRORS" -gt 0 ]]; then
    echo "audit-p2s: $ERRORS PR fetch(es) failed — total=0 does NOT mean 'clean'." >&2
    printf '  failed: %s\n' "${FAILED_FETCHES[@]}" >&2
  fi
  echo "SUMMARY since=$SINCE prs=${#PR_NUMBERS[@]} total=0 addressed=0 orphans=0 filed=0 errors=$ERRORS"
  # A run with fetch failures and no findings is not a clean audit — exit
  # non-zero so callers (and CI) cannot mistake it for one.
  [[ "$ERRORS" -gt 0 ]] && exit 1
  exit 0
fi

# ---------------------------------------------------------------------------
# Split into addressed vs orphan
# ---------------------------------------------------------------------------
ADDRESSED=0
ORPHAN=0
while IFS= read -r finding; do
  path="$(jq -r .path         <<<"$finding")"
  line="$(jq -r .line         <<<"$finding")"
  curl="$(jq -r .comment_url  <<<"$finding")"
  rev="$(jq -r  .reviewer     <<<"$finding")"
  pr="$(jq -r   .pr           <<<"$finding")"
  cid="$(jq -r  .comment_id   <<<"$finding")"
  sev="$(jq -r  .severity     <<<"$finding")"
  title="$(jq -r .title       <<<"$finding")"
  if is_addressed "$path" "$line" "$curl" "$rev" "$pr" "$cid" "$sev" "$title"; then
    ADDRESSED=$((ADDRESSED + 1))
  else
    ORPHAN=$((ORPHAN + 1))
    printf '%s\n' "$finding" >> "$ORPHANS"
  fi
done < "$FINDINGS"

# ---------------------------------------------------------------------------
# Report / file
# ---------------------------------------------------------------------------
FILED=0

print_orphan_human() {
  local f="$1"
  local pr sev rev path line title curl
  pr="$(jq -r .pr <<<"$f")"
  sev="$(jq -r .severity <<<"$f")"
  rev="$(jq -r .reviewer <<<"$f")"
  path="$(jq -r .path <<<"$f")"
  line="$(jq -r .line <<<"$f")"
  title="$(jq -r .title <<<"$f")"
  curl="$(jq -r .comment_url <<<"$f")"
  printf '  [PR #%s] %s %s %s:%s — %s\n         %s\n' \
    "$pr" "$sev" "$rev" "$path" "$line" "$title" "$curl"
}

if [[ "$ORPHAN" -gt 0 ]]; then
  echo
  echo "ORPHANS ($ORPHAN) — P2/P3 findings on merged PRs with no matching issue:"
  while IFS= read -r f; do
    print_orphan_human "$f"
  done < "$ORPHANS"
fi

if [[ "$FILE_ISSUES" -eq 1 && "$ORPHAN" -gt 0 ]]; then
  echo
  echo "Filing $ORPHAN issue(s)..."
  while IFS= read -r f; do
    pr="$(jq -r .pr <<<"$f")"
    sev="$(jq -r .severity <<<"$f")"
    rev="$(jq -r .reviewer <<<"$f")"
    path="$(jq -r .path <<<"$f")"
    line="$(jq -r .line <<<"$f")"
    cid="$(jq -r .comment_id <<<"$f")"
    title="$(jq -r .title <<<"$f")"
    curl="$(jq -r .comment_url <<<"$f")"
    body="$(jq -r .body <<<"$f")"

    # Idempotency belt: re-check right before filing, in case an earlier
    # iteration of THIS run just filed a near-duplicate issue.
    if is_addressed "$path" "$line" "$curl" "$rev" "$pr" "$cid" "$sev" "$title"; then
      continue
    fi

    marker="$(finding_marker "$rev" "$pr" "$cid" "$sev" "$path" "$line" "$title")"

    issue_title="[${sev}] ${path}:${line} — ${title} (from PR #${pr})"
    # gh caps titles at 256 chars; trim before the parenthetical if oversize.
    if (( ${#issue_title} > 240 )); then
      issue_title="${issue_title:0:230}... (PR #${pr})"
    fi

    issue_body=$(cat <<EOF
${marker}

**Source**: ${rev} ${sev} on PR #${pr} (merged) — \`${path}:${line}\`.

**Comment**: ${curl}

---

${body}

---

_Filed by \`scripts/audit-p2s.sh\` — a P2/P3 finding from a merged PR that
no existing issue tracks by its per-finding audit marker (Codex: comment id;
Claude: pr:sev:path:line:title-slug) or by \`path:line\` fallback._
EOF
)

    url="$(gh issue create --repo "$REPO" --title "$issue_title" --body "$issue_body" 2>/dev/null || true)"
    if [[ -n "$url" ]]; then
      FILED=$((FILED + 1))
      echo "  filed: $url"
      # Append to in-memory issues so the next iteration's is_addressed sees it.
      new_num="${url##*/}"
      jq --arg n "$new_num" --arg t "$issue_title" --arg b "$issue_body" --arg u "$url" \
        '. += [{number:($n|tonumber), title:$t, body:$b, url:$u, createdAt:"now"}]' \
        "$ISSUES_JSON" > "$ISSUES_JSON.tmp" && mv "$ISSUES_JSON.tmp" "$ISSUES_JSON"
    else
      echo "  FAILED to file for PR #$pr $path:$line" >&2
    fi
  done < "$ORPHANS"
fi

if [[ "$ERRORS" -gt 0 ]]; then
  echo
  echo "WARNING: $ERRORS PR fetch(es) failed — reported totals are a lower bound." >&2
  printf '  failed: %s\n' "${FAILED_FETCHES[@]}" >&2
fi

echo
echo "SUMMARY since=$SINCE prs=${#PR_NUMBERS[@]} total=$TOTAL addressed=$ADDRESSED orphans=$ORPHAN filed=$FILED errors=$ERRORS"

# Any fetch failure means the audit is incomplete — signal that in exit
# code, so a partial audit cannot be mistaken for a clean one.
[[ "$ERRORS" -gt 0 ]] && exit 1
exit 0
