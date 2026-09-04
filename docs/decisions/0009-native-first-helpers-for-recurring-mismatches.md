# ADR-0009: Native-first mapping; helpers only for recurring mismatches; inline-preferred

- Status: Accepted
- Date: 2026-09-03

## Context

Each Origami patch must become SwiftUI. Two temptations to avoid: (a) wrapping native APIs
in our own, and (b) building a helper for every patch (over-engineering).

## Decision

1. **Native-first.** Map each patch to the most idiomatic *native* SwiftUI/Swift construct
   that faithfully expresses it. Math → operators, logic → `&&`/`||`, `Transition` →
   interpolation expression, tap-with-position → `SpatialTapGesture`, animation →
   `.animation`/`.spring`, scroll → `ScrollView`/`LazyVStack`, loops → `ForEach`. Most of the
   ~55 patch types need **no helper**.
2. **Never wrap an API that already fits.** If SwiftUI has it (e.g. `SpatialTapGesture`), use
   it directly; the win is *knowing* to reach for it (record it in the mapping reference).
3. **Build a helper only when both:** (a) no single native API expresses the semantics, and
   (b) the idiom recurs. Expected set is small (~5–8): `Interaction`, `Drag` (momentum),
   `SampleAndHold`, maybe `Switch`. Validated in practice: `.interaction()` renders correctly
   in Xcode canvas (Touch example, 2026-09-03).
4. **Delivery — inline preferred.** Prefer emitting a helper *inline* into the generated file
   (self-contained, drop-in, zero dependency — serves ADR-0007's project-aware goal) over a
   shipped runtime library. Keep the shared `OrigamiPatterns` module for the corpus/harness;
   the codegen should also support an **inline mode** for exporting a pattern into a real app.

## Momentum note (the recurring hard case)

Without a helper, drag momentum = `DragGesture` + `value.predictedEndTranslation` (system
velocity projection) + `.interpolatingSpring` + clamp to bounds; scroll momentum = native
`ScrollView`. Faithful frame-by-frame velocity physics is deferred (TODOs in `drag()`).

## Consequences

- The helper library stays small; the mapping reference (in the skill) carries the
  patch→construct decisions. Corpus growth populates it.
