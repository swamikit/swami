# ADR-0012: Auto-compare against cached Origami references is the V1 verify gate

- Status: Accepted
- Date: 2026-09-04

## Context

ADR-0004 established visual verification as the fidelity gate — render the SwiftUI,
diff it against the Origami render. In practice we've been running that gate with a
human's eyes: an agent posts the SwamiHost screenshot on a PR, Samuel opens the
Origami artboard side-by-side, decides. That doesn't scale to the ~60+ pattern
corpus, and it re-couples the loop to Samuel's desk — the exact thing the cloud-
first architecture (macOS runner + Codex environment) is meant to dissolve.

## Decision

1. **V1 verify = auto-compare, not human eyes.** For each pattern the CI runs
   SwamiHost's render and diffs it against a **cached Origami reference PNG** using
   a perceptual metric (SSIM or equivalent), not raw pixel diff — SwiftUI subpixel-
   antialiases differently than Origami and raw diffs will always be noisy. A
   score below the threshold merges; above it flags for human review.

2. **Reference set is cached, versioned, private.** Rendered once per pattern per
   Origami version by driving Origami's export on a Mac, then committed to
   `swami-private/references/<origami-version>/<pattern>.png`. Meta-adjacent
   content stays out of the public repo (per the `.gitignore` policy already
   established for `patterns/`).

3. **Origami version is pinned in the reference set.** When Origami updates, we
   re-render the references before running the compare — otherwise a legitimate
   Origami-side rendering change reads as a swami regression. `NEEDS-VERIFY.md`
   tracks the installed version so a drift is caught before it corrupts a run.

4. **Human eyes remain the final sign-off, on a shrinking surface.** Interaction
   verification (gestures driving the render) and anything the auto-compare flags
   still go to Samuel. But the default path — layout, colors, geometry — is
   automated.

5. **CI needs read access to `swami-private`.** Add a deploy key or fine-grained
   PAT to `swamikit/swami`'s Actions secrets; the compare step in `verify.yml`
   fetches references before diffing.

## Consequences

- The loop is cloud-only for pattern iteration. Mac only runs at reference-set
  refresh time (Origami upgrade or a pattern's semantics changed upstream).
- ADR-0004 is not superseded — it stands as the *why* (fidelity is visual). This
  ADR is the *how* (auto-compare against cached references).
- `verify.yml` grows two steps: fetch references from `swami-private`, then
  `pixelmatch`/`ssim` compare. The sticky PR comment shifts from "look at this
  and decide" to "auto-compare score X.YZ vs threshold, here's the diff image."
- A helper (Mac-side) is needed to drive Origami's export headlessly. First
  implementation can be AppleScript / UI-scripting; investigate whether Origami
  has a scriptable export interface before writing the automation.
