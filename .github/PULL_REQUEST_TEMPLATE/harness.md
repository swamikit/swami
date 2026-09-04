# Verify / CI change

The harness is the fidelity oracle for Beat 3 (Prove). Changes here move the gate, not the product.

## What changed
- Files (`.github/workflows/*`, `app/`, `scripts/`, `tool/harness/`):
- Summary:

## Why
- Problem it fixes / capability it adds:

## CI behavior
- **Before:**
- **After:**

## Expected impact
- Run time delta (approx):
- Runner cost / flakiness expectation:
- Gate strictness change (SSIM threshold, new checks):

## Checks
- [ ] Compile pre-gate still runs (tree-sitter-swift + `build_sim`)
- [ ] Sticky-comment format unchanged, or docs updated to match
- [ ] Rollback plan noted if the runner regresses
