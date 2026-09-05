---
name: review
description: The Reviewer GA's skill. Codifies how any agent playing the Reviewer role checks a PR. Reviewers check visual state match, structural port match, methodology (ADR alignment), and evidence completeness. Reviews are evidence-required claims per verified-delivery; findings must be testable against current HEAD, not authoritative pronouncements. Load into any GA whose trigger is a PR event (opened, synchronize, ready_for_review) or an @claude review comment.
metadata:
  type: procedural
---

# Review

The Reviewer's job is to check what Builder posted, not to re-run it. Trust the
evidence in the PR, read the code against it, and file findings that Builder can
reproduce or rebut against HEAD.

## Context reads (do first, before commenting)

Load these before writing a single comment. A Reviewer without context is a person
guessing at style.

- **`AGENTS.md`.** Beats, definition of done, architecture. If the PR skips a
  beat, it's the AGENTS.md contract it's skipping.
- **`docs/decisions/*.md`.** Especially 0009 (native-first helpers), 0010
  (helper naming, faithful patch mapping), 0013 (runner installs Origami, verify
  substrate). A finding that contradicts an ADR needs to cite the ADR.
- **`skill/workflow/SKILL.md` if it exists at HEAD.** House rules, evidence
  expectations, the Build/Review cycle. This is the rulebook you're enforcing.
  If it isn't in the tree yet (pre-review-GA ship), treat AGENTS.md as the
  fallback source of the same rules and don't block on the missing file.
- **`app/Swami/*.swift`** (or whatever the helper surface is at HEAD). Helper
  API awareness. Do not propose an API that already exists under a different name.
- **The PR's Builder-posted sticky comment.** This is the evidence to review. If
  it's missing or stale, that's your first finding.

Skip any of these and the review devolves into taste.

## Check types by PR type

Different PRs earn different scrutiny. Pattern PRs need pixels; parser PRs need
determinism; docs PRs need cross-references that actually resolve.

### Pattern PR
- **Visual.** State match (rest, interacting, animating), alignment against
  the Origami render, chrome (status bar, safe area, background). SSIM alone is
  not enough (see below).
- **Structural.** The placed graph's ports match the helper's ports; the helper
  used matches the Origami patch it claims to map (ADR-0010).
- **Methodology.** Native-first path justified per ADR-0009; pattern PR
  template used (`.github/PULL_REQUEST_TEMPLATE/pattern.md`); evidence complete
  (states, timings, hit areas, not just one hero shot).

### Helper PR
- Code quality and idiom.
- **ADR-0009 native-first check.** Is the helper actually needed, or does the
  Origami patch have a native SwiftUI equivalent?
- Port table completeness against the Origami patch (Inputs, Outputs, defaults,
  units).
- Docstring convention. What patch it maps, what it does *not* map (the
  flag-don't-fake seams).

### Parser PR
- Deterministic behavior. Same input, byte-identical output.
- No runtime deps beyond stdlib (CLAUDE.md convention: "parser deterministic
  and dependency-light").
- Tests over the corpus, not just hand-crafted fixtures.
- Boundary handling: root field 14 is library, tail region is placed graph. A
  parser change had better not confuse them again.

### Docs / methodology PR
- Clarity, factual accuracy.
- Cross-references land where they say they land (`docs/decisions/0009-...`
  actually exists; anchors resolve).
- Nothing contradicts an existing ADR without superseding it.

### Infra / harness PR
- Reproducible from a clean clone.
- No runner minutes wasted on non-code PRs (docs-only changes shouldn't spin the
  sim).
- Codex P1 patterns caught. The failures we've seen before, we shouldn't see
  again.

## Rebuttal handling (verified-delivery)

Every finding is a claim. Claims need evidence, and claims can be rebutted.

- **Every finding requires evidence.** A line reference, a screenshot, a
  behavior claim tied to a specific state. "This feels off" is not a finding.
- **Builder can rebut by demonstrating the claim doesn't reproduce against
  current HEAD.** New commit, new screenshot, new test output, whichever is
  the evidence type for the finding.
- **If the claim reproduces, Builder addresses it.** If it doesn't, Builder
  posts counter-evidence and Reviewer re-verifies against the same HEAD.
- **Never repeat a rebutted finding on the same commit without new evidence.**
  A finding that's been rebutted is closed for that SHA. Reopen it only if a
  later commit reintroduces the condition.

Findings are testable claims, not authoritative pronouncements. Reviewer is
wrong sometimes; the mechanism has to allow for that.

## PR-comment shape

Write like a message to Builder, not a report to a manager.

- **Approve.** Single approving comment, `Approved` review action. Say what
  you checked, not just "LGTM".
- **Request changes.** Inline comments per finding (each with its evidence),
  plus one summary comment on the review that names the blocking findings.
- **Discussion.** Thread on the specific finding. Don't pile discussion into
  the review summary; it gets lost.

Findings that block merge and findings that are nice-to-have go in different
buckets. Say which is which.

## What NOT to do

- **Don't propose architectural changes without citing an ADR that supports
  them.** If the ADR doesn't exist, write it first; don't smuggle architecture
  through a code review.
- **Don't leave findings without evidence.** No evidence, no finding.
- **Don't treat SSIM at threshold alone as sufficient.** Two frames can score
  high and still be semantically wrong. Think of a Purple oval at scale 5 vs a
  Purple card at scale 1: same average pixels, different mechanism. Check the
  mechanism.
- **Don't re-run the same tests Builder already reported.** Trust the evidence.
  Review the code against it. If the evidence looks fabricated, that's the
  finding, not "I re-ran it and it passes".

## When the diff exceeds the reviewer cap

`scripts/run-claude-review.py` caps the diff it sends to Claude at
`MAX_DIFF_BYTES` (200,000 bytes). Anything larger is truncated and the
reviewer synthesizes a P1 finding that blocks the automated merge gate
(ADR-0014 — the Reviewer read *is* the gate; approving on a partial diff
is a false green). When you hit that cap, work through this ladder in
order before overriding:

1. **Split the PR.** Break it into smaller topic-scoped PRs that each fit
   under the cap. This is the default and by far the safest option — a
   review that reads the whole change is the whole point of the gate.
2. **Manual full-diff review with an explicit rebuttal.** For a
   one-pattern-one-PR where the size is unavoidable, a human reviewer
   reads the whole diff (generated Swift + IR included — those files are
   the shipped pattern; SSIM can conceal structural mistakes in them, so
   they are not vendored noise you can safely skip) and posts a rebuttal
   comment on the PR that (a) acknowledges the truncation, (b) explains
   why splitting isn't viable here, and (c) records the structural
   findings from the manual read (or explicitly states none). Only then
   merge manually. This is the escape hatch, not the default — use it
   sparingly and never as a way to keep generated code from being read.

Do not filter generated `.swift` or IR out of the diff to slip under the
cap. Those files are what the pattern actually is; approving HEAD
without them read is exactly the false green the gate exists to catch.

## Message-exchange context

- 30-minute poll deadline for both sides. Event-driven fallback on timeout: if
  Builder pushes and the review event doesn't wake you, the next poll picks it up.
- Ephemeral GA runs, so no session memory is needed. State lives in the PR:
  sticky comment, review threads, commit SHAs. Every run reloads from there.
- The cycle is Build, Review, Build, Review, not Review-approves-once. A
  Reviewer who approves on first pass without evidence is skipping the loop.
- Full Build/Review message-exchange model TBD in ADR-0015 (follow-up); the
  above is the working contract until then.
