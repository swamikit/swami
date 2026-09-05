#!/usr/bin/env bash
#
# audit-p2s.sh — for every PR merged since --since (default: today), collect
# every P2/P3 finding left on it by BOTH reviewers (Codex line comments +
# Claude review sticky), decide whether each finding is already tracked by a
# repo issue, and print the orphans. With --file-issues, open one issue per
# orphan.
#
# The earlier audit missed all of PR #58's Claude P2/P3 findings because it
# only walked Codex line comments. This script walks BOTH reviewers off the
# same code so the next run cannot repeat that gap.
#
# Usage:
#   scripts/audit-p2s.sh [--since YYYY-MM-DD] [--file-issues] [--repo OWNER/REPO]
#
# Dependencies: bash 4+, gh, jq. No Python.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
SINCE="$(date -u +%Y-%m-%d)"
FILE_ISSUES=0
REPO=""

usage() {
  sed -n '2,20p' "$0"
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --since)        SINCE="${2:-}"; shift 2 ;;
    --file-issues)  FILE_ISSUES=1; shift ;;
    --repo)         REPO="${2:-}"; shift 2 ;;
    -h|--help)      usage ;;
    *)              echo "unknown arg: $1" >&2; usage ;;
  esac
done

if ! [[ "$SINCE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "audit-p2s: --since must be YYYY-MM-DD (got: $SINCE)" >&2
  exit 2
fi

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json owner,name -q '.owner.login + "/" + .name')"
fi

for tool in gh jq; do
  command -v "$tool" >/dev/null 2>&1 || { echo "audit-p2s: missing $tool" >&2; exit 2; }
done

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
# on any realistic backlog.
ISSUES_JSON="$WORK/issues.json"
gh issue list --repo "$REPO" --state all --limit 500 \
  --json number,title,body,url,createdAt \
  > "$ISSUES_JSON"

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
# Discover PRs merged since SINCE
# ---------------------------------------------------------------------------
PRS_JSON="$WORK/prs.json"
gh pr list --repo "$REPO" --state merged --limit 100 \
  --json number,mergedAt,title,url,headRefOid \
  > "$PRS_JSON"

# macOS ships bash 3.2 which lacks `mapfile` — read the numbers into an
# array the portable way.
PR_NUMBERS=()
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

# Claude review sticky: one <!-- claude-review --> comment per PR. Findings
# live under `### P2 (N)` and `### P3 (N)` headers as
# `- **`path:line` — [P2] title**` bullets, with reasoning/suggestion on
# indented sublines.
collect_claude() {
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
      | select(.body | contains("<!-- claude-review -->"))
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
# Addressed-ness check
# ---------------------------------------------------------------------------
#
# A finding is "addressed" if ANY of:
#   * an issue mentions the exact `path:line` (title or body)
#   * an issue links to the exact comment URL (title or body) — but ONLY
#     when the URL uniquely identifies THIS finding
#
# The earlier "issue mentions PR #N AND the file path" heuristic was too
# loose: a single follow-up issue on PR #58 that named the file made every
# other finding in the same file on the same PR look addressed too — that is
# how the previous audit hid all of PR #58's Claude P2/P3s. Match by exact
# anchor only.
#
# Reviewer matters for the URL check. Codex line comments each have their
# own `html_url` (unique per finding), so URL match is honest. The Claude
# sticky is ONE comment carrying N findings — all N share the same URL, so
# once any one is filed (and the filed issue references the sticky URL),
# the URL match would mark every remaining Claude finding on that PR as
# addressed. For Claude findings the URL is deliberately NOT used.
#
# We also do NOT treat "a later commit on the PR touched this file" as
# addressed: on merged PRs every commit is later than every review comment,
# so that heuristic evaluates to "always addressed". Issue-linkage is the
# honest signal.
#
# is_addressed <path> <line> <comment_url> <reviewer>
is_addressed() {
  local path="$1" line="$2" curl="$3" reviewer="$4"
  local needle_pathline="${path}:${line}"
  local url_arg="$curl"
  # Claude sticky URL is shared across all findings on the PR — do not use it.
  if [[ "$reviewer" == "claude" ]]; then
    url_arg=""
  fi
  jq -e --arg pl "$needle_pathline" \
        --arg url "$url_arg" '
    any(.[]?;
      (.body // "") as $b
      | (.title // "") as $t
      | (
          ($b | contains($pl)) or
          ($t | contains($pl)) or
          ($url != "" and (($b | contains($url)) or ($t | contains($url))))
        )
    )
  ' "$ISSUES_JSON" >/dev/null
}

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
  path="$(jq -r .path  <<<"$finding")"
  line="$(jq -r .line  <<<"$finding")"
  curl="$(jq -r .comment_url <<<"$finding")"
  rev="$(jq -r .reviewer <<<"$finding")"
  if is_addressed "$path" "$line" "$curl" "$rev"; then
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
    title="$(jq -r .title <<<"$f")"
    curl="$(jq -r .comment_url <<<"$f")"
    body="$(jq -r .body <<<"$f")"

    # Idempotency belt: re-check right before filing, in case an earlier
    # iteration of THIS run just filed a near-duplicate issue.
    if is_addressed "$path" "$line" "$curl" "$rev"; then
      continue
    fi

    issue_title="[${sev}] ${path}:${line} — ${title} (from PR #${pr})"
    # gh caps titles at 256 chars; trim before the parenthetical if oversize.
    if (( ${#issue_title} > 240 )); then
      issue_title="${issue_title:0:230}... (PR #${pr})"
    fi

    issue_body=$(cat <<EOF
**Source**: ${rev} ${sev} on PR #${pr} (merged) — \`${path}:${line}\`.

**Comment**: ${curl}

---

${body}

---

_Filed by \`scripts/audit-p2s.sh\` — a P2/P3 finding from a merged PR that
no existing issue tracks by \`file:line\` or PR reference._
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
