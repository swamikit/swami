# ADR-0014: SSIM is informational evidence, not a merge gate

- Status: Accepted
- Date: 2026-09-04
- Supersedes: implicit SSIM-as-gate in ADR-0013 (ADR-0013's "SSIM-diffs" step stays; only the interpretation changes)

## Context

ADR-0013 established the runner-installs-Origami + SSIM-diff pattern. In practice, SSIM as a threshold gate has repeatedly given false greens on our subject matter (flat magenta artboards + light-pink cards):
- PR #2 v2: SSIM 0.9686 ✅ despite Origami showing mid-interaction (ovals visible) while Swami showed rest state
- PR #2 v3: SSIM 0.9740 ✅ with Dynamic Island in Swami's shot but not Origami's, cards at different vertical positions
- Codex P1 on PR #5 (2026-09-04): even the "gate" doesn't fail the workflow — SSIM below threshold sets FAIL=1 but no step exits nonzero, so merges proceed

SSIM measures perceptual structure — for near-flat color fields it over-rewards palette match and under-penalizes semantic mismatch. The metric doesn't fit the subject.

## Decision

1. **SSIM stays** as a posted number in the sticky PR comment. Data point, not verdict.
2. **The visual gate becomes: Reviewer GA (skill/review) + Sam's spot-check on flagged cases.** Reviewer reads the swami/origami/diff triplet and calls state match, alignment, chrome, semantic correctness. That's what the human eye already does; the Reviewer skill codifies it.
3. **Structural gate** (port match) lands separately when parser port extraction ships — that's automated, deterministic, and complements the visual side.
4. **Verify workflow doesn't need to fail on SSIM.** Keep the number as evidence; merges gate on Reviewer approval + no unresolved findings.
5. **Threshold field stays in the YAML for future opt-in** — e.g. an interaction gate PR could set a per-pattern threshold if it makes sense — but the default gate is Reviewer-driven, not SSIM-driven.

## Consequences

- verify.yml can drop the FAIL=1/any_fail export in a follow-up cleanup (or leave it; nothing consumes it now).
- skill/review takes on the visual-check responsibility explicitly (already in the skill draft).
- ADR-0013 stays valid for "how" (runner installs Origami, live render). Only "SSIM gates merge" reading is superseded.
- Future ADR opportunity: interaction gate could re-introduce a real threshold (video-based, per-region SSIM or similar) — that's a separate decision.
