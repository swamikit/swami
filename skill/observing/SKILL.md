---
name: observing
description: How to watch for recurring patterns across many PRs and propose system-level improvements. When called from the Review GA or a scheduled meta-scan, reads recent PR history, identifies repeated shapes (same class of Codex finding, same misalignment kind, same helper missing), and files a type:meta issue with evidence proposing a fix. This is how the self-improving loop generates its own tasks.
metadata:
  type: procedural
---

# Observing

Any single PR is a data point. The pattern across PRs is the signal. The observer's
job is to watch that signal — recurring findings, repeated misalignments, missing
helpers that keep coming up — and turn it into a meta-issue Builder can act on,
so the same lesson stops getting re-learned one PR at a time.

This skill is the loop that lets the system improve itself.

## Trigger patterns for meta-observation

Any of these is a valid entry point:

- **Post-review reflex.** After reviewing a PR, when at least two other agents have
  already reviewed prior PRs in the last 30 days, scan those reviews for shared
  findings before signing off. If three PRs carry the same shape of finding, this
  is the moment to file.
- **Scheduled meta-scan.** A weekly cron on the Triage GA reads every closed PR
  from the last N days and runs the detection heuristics below across the whole
  set. This catches slow-burn patterns a single reviewer wouldn't see.
- **Manual invocation.** `@claude observe` in an issue or PR thread runs the
  same scan on demand, scoped to whatever the caller specifies (last 30 days,
  a label, a directory).

## Detection heuristics

A finding earns "meta" status only when the same shape shows up N=3+ times. The
threshold is what separates a real pattern from noise.

- **Same Codex finding title on 3+ different PRs in the last 30 days** → likely
  systemic. Propose a skill rule, a linter, or an ADR that closes the class.
- **Same helper missing across 2+ pattern translations** → propose adding the
  helper to `app/Swami/` (ADR-0009 native-first, ADR-0010 faithful patch
  mapping). Two occurrences is the threshold here because helpers are additive
  and cheap to justify.
- **Same test/verify failure signature across N runs** → propose an infra fix
  (runner setup, simulator selection, timeout, artifact upload). If the failure
  keeps eating Builder time, the fix belongs in `.github/workflows/` or the
  Verify GA, not in yet another PR-local patch.
- **Same style issue across M skill files** → propose a linter rule or an
  unslop update. Prose drift across skill/ADR/PR bodies is exactly the shape
  `unslop/` was written to catch.

Look for the shape, not the words. Three PRs whose Codex finding was worded
differently but flagged the same underlying issue (e.g. "helper not found",
"missing patch", "no such symbol") count as three occurrences.

## Output format — a filed meta-issue

Findings go into GitHub as issues, not comments. A meta-issue is a Builder
target, not a review note.

- **Title.** Brief description of the pattern. "Codex keeps flagging missing
  drag momentum helper — file it once" beats "meta finding #4".
- **Body.**
  - **Evidence.** Direct links to the specific PRs and comments where the
    pattern appeared. One line per occurrence — PR number, date, one-sentence
    excerpt of the finding, permalink. No occurrence, no evidence.
  - **Proposed fix.** Concrete action. New skill rule at
    `skill/<name>/SKILL.md`, new helper at `app/Swami/<Name>.swift`, new PR
    template section, new ADR under `docs/decisions/`. If the fix needs a
    human decision (naming, taste, an ADR pivot), flag it `needs-decision`
    and stop — do not force a call the observer isn't scoped to make.
  - **Threshold.** How many more occurrences before we should act, if the
    proposed fix is deferred. Default: three more without fix, then escalate
    to blocking on the next PR that hits the same shape.
- **Labels.** `type:meta` always. Priority label based on the impact — how
  much Builder time or reviewer time each occurrence costs.

## What NOT to do

The observer is one of the cheapest sources of noise if it's undisciplined.

- **Don't file meta-issues from single occurrences.** N=1 is a finding on that
  PR. N=3+ is a pattern. If you file at N=1 you're just re-doing the review
  under a different label.
- **Don't file speculative meta-issues without linked PR evidence.** Every
  claim in the body needs a URL. "This feels like it happens a lot" is not
  evidence.
- **Don't propose fixes agents can't autonomously execute.** If the fix needs
  a human decision — an ADR pivot, a rename, a scope call — flag it
  `needs-decision` and describe the trade-off. Don't guess.
- **Don't spam.** Max one meta-issue per review pass per agent. If more than
  one pattern is real, list the others as "also observed" in a follow-up
  comment on the first issue, and file the second in the next pass. The rate
  limit is the discipline that makes the meta-loop trustworthy.

## Steps

1. **Read the trigger's scope.** Post-review reflex → the current PR plus the
   last N closed PRs by the same GA or on the same area. Scheduled scan → last
   N days across all closed PRs. Manual → whatever the caller specified.
2. **Pull the finding surface.** For each PR in scope: Codex review comments,
   reviewer sticky comments, Verify GA output, merge status. Normalize each
   finding to a short shape label (helper-missing, drift-in-skill, verify-flake,
   style-slop, alignment-off).
3. **Cluster.** Group by shape. Drop any shape with fewer than the threshold
   (helpers 2+, everything else 3+).
4. **Draft the meta-issue** per the format above. Evidence first, fix second,
   threshold third. Run `unslop` on the body before filing.
5. **File once.** Search open issues with `type:meta` first — if the same
   pattern is already filed, add an occurrence to the existing issue's evidence
   list instead of opening a duplicate.
6. **Link back.** On the PR that triggered the reflex, drop a one-liner
   pointing at the meta-issue so the next reviewer sees the trail.
