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
- [ ] Local (dev-side, if applicable): `tree-sitter-swift` parses generated Swift without ERROR/MISSING nodes
- [ ] Local (dev-side, if applicable): XcodeBuildMCP `build_sim` still succeeds against `SwamiHost`
- [ ] CI: `verify.yml` `xcodebuild build` still succeeds on the macos-15 runner
- [ ] CI: pixel gate still passes (SSIM ≥ `SSIM_THRESHOLD`) for every pattern in `PATTERNS`
- [ ] Sticky-comment format unchanged, or docs updated to match
- [ ] Rollback plan noted if the runner regresses
