---
name: triage
description: How to take feedback/observations and produce/update issues without spam. G-doc-style lifecycle. Read before writing, update-first heuristic, consolidate related, split accumulated, close on evidence. Loaded by the Triage GA (on `issues` events) but any agent processing feedback can invoke it directly. Load whenever a chat log, meeting notes, review batch, or raw user complaint has to become issues that a human wants to be able to track a week later without a duplicate-hunting cleanup pass.
metadata:
  type: procedural
---

# Triage

The failure mode this skill exists to prevent: an agent reads one chunk of
feedback, produces eight new issues that overlap two open issues and each other,
labels none of them, closes none of them when they get fixed. A week later the
tracker is unreadable, the human declares issue bankruptcy, and the tracking
system is worse than nothing. That's what happened before this skill existed.
Read before writing, update before creating, consolidate the drift, split the
pile-ups, and close on evidence.

## Read before writing

Before creating any issue, run `gh issue list` (with the right filters) and skim
for open matches. Cheap similarity check: title tokens, labels, most recent body
edit or comment. If the new feedback fits an open issue, that issue is your
target. **Never create an issue without checking for duplicates.**

Practical form:

```
gh issue list --state open --limit 100 --json number,title,labels,updatedAt
gh issue view <n>   # for anything that looks close
```

Do this once per triage session, cache the list in your head or a scratch note,
then decide on each new item.

## Update-first heuristic

If new feedback matches an open issue, **append it**. Add a comment with the new
observation, or edit the body to fold it in. Only create a new issue when the
feedback is genuinely orthogonal (a different failure mode, a different surface,
a different subsystem).

The default is "add to what exists". The exception is orthogonality, and
orthogonality needs a one-line justification in the new issue's body ("split
from #N because …").

## Consolidate related

If two or more open issues describe the same thing, propose merging. Same
symptom, same subsystem, same fix would close both. Leave the newer one open
(usually has fresher context), close the older with:

> Closing as duplicate of #M. Same failure mode, consolidating discussion there.

Evidence for "same thing" can come from GA runs that repro both, from clustering
on titles/labels, or from a human eyeballing the list. Always link the survivor
so history follows the reader.

## Split accumulated

If an open issue's comment thread has accumulated three or more orthogonal
concerns, split them. Different bugs, different features, different asks.
Original issue stays open for its original subject; the drift gets extracted
into new issues, each linking back with "split from #N (comment <permalink>)".

The signal is comment count plus topical drift, not comment count alone. A long
thread on one bug is fine; three separate bugs sharing a thread is not.

## Batch mode

For a feedback dump like a chat log, meeting notes, a Codex-finding batch, or a
review comment sweep, do not create issues one by one as you read. Three passes:

1. **Extract.** Read the whole dump. Produce a working list of N candidate
   items with a one-line summary each. No writes yet.
2. **Dedupe.** For each candidate, check the open-issue list (from *Read before
   writing*). Mark each candidate as `update:#N`, `duplicate:#M`, or `new`.
3. **Write.** Do the updates first (cheapest, lowest chance of accidental
   duplication), then the new-issue creates. Every new issue gets labels, a
   type, and a priority in the same call. No bare titles.

The three-pass shape is the whole point. One-pass triage is how the tracker
gets flooded.

## Lifecycle

- **Open on creation.** Every issue starts open, labeled, and typed.
- **Close on evidence.** Close when a linked PR merges and its verify job is
  green, not when the PR merges alone. Include the PR number and the verify
  run link in the closing comment.
- **Reopen on regression.** New failure with the same signature (same repro,
  same surface) reopens the original issue rather than creating a new one.
  Different signature → new issue that links back.
- **Merge duplicates.** "Closing #N as duplicate of #M" as the closing comment.
  Never close a duplicate silently.

## Type taxonomy

(From verified-delivery plus swami-specific additions. Every issue gets exactly
one type.)

- `type:bug`. Reproducible defect with evidence (steps, expected, actual).
- `type:feature`. New capability request.
- `type:meta`. Observations about the system: cross-PR patterns, process
  gaps, methodology drift. Not a code change on its own.
- `type:infra-blocker`. Runner-level failures: Origami install, sim boot,
  network, cache. Blocks work but isn't a product defect.
- `type:feedback`. Raw user input still to be triaged into one of the above.
  Temporary; a `type:feedback` issue that stays feedback for more than a
  triage cycle is a smell.
- `type:duplicate`. Closed as duplicate of another. Applied at close, not open.
- `type:no-longer-reproducible`. Version-specific bug that later versions
  don't hit. Close, note the version window, keep the label for future
  regression matching.

## Priority triage

- **p1.** Blocks something real: a merge, a demo, a customer. If nothing is
  blocked, it isn't p1.
- **p2.** Worth doing next; not blocking. Default for actionable work.
- **p3.** Nice-to-have; may sit forever. Honest signalling, not a graveyard.

Priority is renegotiable. If a p3 starts blocking something, bump it. Note the
bump in a comment.

## What NOT to do

- Do not create an issue without checking for duplicates.
- Do not leave an issue without labels, at minimum a type and a priority.
- Do not close an issue without linking why: a PR number, a duplicate target,
  or an explanation.
- Do not spam-create issues from a single feedback dump. Three-pass batch, or
  don't touch the tracker.
- Do not treat `type:feedback` as a permanent state. Triage it or close it.
