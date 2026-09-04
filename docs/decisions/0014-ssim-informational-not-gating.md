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
5. **No threshold field in the YAML today.** SSIM is informational; there is nothing for a threshold to gate. A future interaction-gate ADR can reintroduce a per-region or per-pattern threshold if that metric proves it fits the subject matter.

### Interim gate (until Reviewer GA ships)

This decision captures the *target* model. Reviewer GA (PR #11, skill/review) hasn't
shipped yet, so today's visual gate is **Sam's spot-check on the posted evidence
triplet** — same swami/origami/diff comment, human read. Once Reviewer GA lands, the
same read becomes automated per this ADR, with Sam only spot-checking flagged cases.
No workflow change is required at the flip — the evidence comment is already the
Reviewer's input surface.

## Consequences

- verify.yml can drop the FAIL=1/any_fail export in a follow-up cleanup (or leave it; nothing consumes it now).
- skill/review takes on the visual-check responsibility explicitly (already in the skill draft).
- ADR-0013 stays valid for "how" (runner installs Origami, live render). Only "SSIM gates merge" reading is superseded.
- Future ADR opportunity: interaction gate could re-introduce a real threshold (video-based, per-region SSIM or similar) — that's a separate decision.
