---
name: review
description: The Reviewer GA's skill. Codifies how any agent playing the Reviewer role checks a PR — visual state match, structural port match, methodology (ADR alignment), evidence completeness. Reviews are evidence-required claims per verified-delivery — findings must be testable against current HEAD, not authoritative pronouncements. Load into any GA whose trigger is a PR event (opened/synchronize/ready_for_review) or an @claude review comment.
metadata:
  type: procedural
---

# Review

The Reviewer's job is to check what Builder posted — not to re-run it. Trust the
evidence in the PR, read the code against it, and file findings that Builder can
reproduce or rebut against HEAD.

## Context reads (do first, before commenting)

Load these before writing a single comment. Reviewer without context is a person
guessing at style.

- **`AGENTS.md`** — Beats, definition of done, architecture. If the PR skips a
  beat, it's the AGENTS.md contract it's skipping.
- **`docs/decisions/*.md`** — especially 0009 (native-first helpers), 0010
  (helper naming, faithful patch mapping), 0013 (runner installs Origami / verify
  substrate). A finding that contradicts an ADR needs to cite the ADR.
- **`skill/workflow/SKILL.md`** — house rules, evidence expectations, Build↔Review
  cycle. This is the rulebook you're enforcing.
- **`app/Swami/*.swift`** (or whatever the helper surface is at HEAD) — helper
  API awareness. Do not propose an API that already exists under a different name.
- **The PR's Builder-posted sticky comment** — the evidence to review. If it's
  missing or stale, that's your first finding.

Skip any of these and the review devolves into taste.

## Check types by PR type

Different PRs earn different scrutiny. Pattern PRs need pixels; parser PRs need
determinism; docs PRs need cross-references that actually resolve.

### Pattern PR
- **Visual** — state match (rest / interacting / animating), alignment against
  the Origami render, chrome (status bar, safe area, background). SSIM alone is
  not enough (see below).
- **Structural** — the placed graph's ports match the helper's ports; the helper
  used matches the Origami patch it claims to map (ADR-0010).
- **Methodology** — native-first path justified per ADR-0009; PR template used;
  evidence complete (states, timings, hit areas, not just one hero shot).

### Helper PR
- Code quality and idiom.
- **ADR-0009 native-first check** — is the helper actually needed, or does the
  Origami patch have a native SwiftUI equivalent?
- Port table completeness against the Origami patch (Inputs/Outputs, defaults,
  units).
- Docstring convention — what patch it maps, what it does *not* map (the flag-
  don't-fake seams).

### Parser PR
- Deterministic behavior — same input, byte-identical output.
- No runtime deps beyond stdlib (ADR-0004).
- Tests over the corpus, not just hand-crafted fixtures.
- Boundary handling: root field 14 is library, tail region is placed graph — a
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
- Codex P1 patterns caught — the failures we've seen before, we shouldn't see
  again.

## Rebuttal handling (verified-delivery)

Every finding is a claim. Claims need evidence, and claims can be rebutted.

- **Every finding requires evidence.** A line reference, a screenshot, a
  behavior claim tied to a specific state. "This feels off" is not a finding.
- **Builder can rebut by demonstrating the claim doesn't reproduce against
  current HEAD.** New commit, new screenshot, new test output — whichever is
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

- **Approve** — single approving comment, `Approved` review action. Say what
  you checked, not just "LGTM".
- **Request changes** — inline comments per finding (each with its evidence),
  plus one summary comment on the review that names the blocking findings.
- **Discussion** — thread on the specific finding. Don't pile discussion into
  the review summary; it gets lost.

Findings that block merge and findings that are "nice-to-have" go in different
buckets. Say which is which.

## What NOT to do

- **Don't propose architectural changes without citing an ADR that supports
  them.** If the ADR doesn't exist, write it first; don't smuggle architecture
  through a code review.
- **Don't leave findings without evidence.** No evidence, no finding.
- **Don't treat SSIM ≥ threshold alone as sufficient.** Two frames can score
  high and still be semantically wrong — think a Purple oval at scale 5 vs a
  Purple card at scale 1, same average pixels. Check the mechanism.
- **Don't re-run the same tests Builder already reported.** Trust the evidence.
  Review the code against it. If the evidence looks fabricated, that's the
  finding — not "I re-ran it and it passes".

## Message-exchange context

- 30-minute poll deadline for both sides. Event-driven fallback on timeout — if
  Builder pushes and the review event doesn't wake you, the next poll picks it up.
- Ephemeral GA runs — no session memory needed. State lives in the PR: sticky
  comment, review threads, commit SHAs. Every run reloads from there.
- The cycle is Build → Review → Build → Review, not Review-approves-once. A
  Reviewer who approves on first pass without evidence is skipping the loop.
