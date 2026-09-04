# Beats

The four-beat discipline that keeps the translator honest: one pattern per branch,
compile-clean before opening a PR, visual gate against Origami's own render, ship
only on Reviewer approval plus a human spot-check.

@Metadata {
    @PageKind(article)
}

## Overview

Reframe first: **each pattern that lands is a deliverable, not a test.** The corpus
is a public gallery for the Origami community *and* the training set that teaches
Swami the general rules. Every PR equals one more entry in the gallery and one more
mapping rule earned. That's the shape of the loop.

## The beats

### 1. Isolate

One pattern per branch (one per worktree when a Mac agent is running alongside).
The unit of change is *one `.origami` → one generated view → one PR*. This keeps
diffs reviewable and pins each rule the codegen earns to a single artifact.

### 2. Build

Parser and codegen edits in `tool/`. Run the `tree-sitter-swift` syntax pre-gate on
the generated `.swift` before opening a PR. Compile-clean is the ticket to enter
the queue, not proof of correctness — the visual gate is what closes it.

### 3. Prove

The GitHub Actions `macos-15` runner installs Origami itself (from its Sparkle
appcast) and runs both sides in the same job: opens each pattern's `.origami` in
Origami and screenshots via **View → Take Screenshot**; boots `SwamiHost` with
`SWAMI_PATTERN=<slug>` and screenshots the simulator; posts a swami / origami / diff
triplet on the PR as the visual gate's input surface.

SSIM is a data point, not a verdict. The metric over-rewards palette match on our
flat-color subject matter and has repeatedly green-lit obvious mismatches, so it
sits in the sticky PR comment as evidence — never as the gate. See ADR-0014.

### 4. Ship

Merge on Reviewer approval plus Samuel's spot-check on flagged cases. The Reviewer
skill (`skill/review`) reads the swami / origami / diff triplet and calls state
match, alignment, chrome, and semantic correctness — that's the visual gate. Human
sign-off remains for interactions (gesture-driven behavior). Resolve the matching
`NEEDS-VERIFY.md` item on merge.

Until the Reviewer GA lands (PR #11), the read is Samuel's by hand on the same
posted evidence — same surface, same criteria, just not yet automated.

## Cross-cutting

`unslop` (`skill/unslop/`) is a pass on anything a human will read — commit
messages, PR titles and bodies, ADRs, `NEEDS-VERIFY.md` entries. Run it before you
push, so the words on the page carry the same care as the code they describe.
