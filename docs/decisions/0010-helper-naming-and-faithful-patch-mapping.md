# ADR-0010: Bare, patch-matched helper names; faithful 1:1 patch↔helper

- Status: Accepted
- Date: 2026-09-03

## Decision — naming

- Helpers are named after the Origami **patch**, **bare** (no `swami`/`origami` prefix):
  `interaction`, `sampleAndHold`, `transition`, `classicAnimation`, `drag`, …
- Disambiguate via the **module** (`OrigamiPatterns.Transition`) if a name is ever ambiguous.
- Handle the rare genuine collisions **by shape**, not a blanket prefix: value patches become
  free functions/types (so `transition(progress:start:end:)` doesn't clash with SwiftUI's
  `.transition()` *view modifier*); `switch` (a keyword) becomes a type `Switch`. Prefix only
  if a specific case truly can't be resolved otherwise.

## Decision — faithful 1:1 mapping (one helper per patch, exact ports)

- **One helper = one Origami patch, exposing exactly that patch's ports.** Patch **inputs →**
  helper parameters; patch **outputs →** bindings/callbacks.
- **Do not bundle multiple patches into one helper.** This keeps codegen a trivial
  `node → helper` lookup (the parser extracts nodes *by patch type*); bundling forces codegen
  to recognize combinations, which is lossy and complex.

### Correction that motivated this

The first `Interaction` helper wrongly bundled `onDoubleTap`/`onLongPress`. Per the Origami
docs, the **Interaction** patch outputs only **Down, Tap, Position, Force**. `Double Tap` and
`Long Press` are **separate patches** (`origami.DoubleTap`, `origami.LongPress`) and get their
own helpers. Faithful split:
- `Interaction` → `down`, `tap`, `position`, `force` (Force often inert on modern devices — expose but flag).
- `DoubleTap` → own helper.
- `LongPress` → own helper.

## Consequences

- Codegen maps each parsed node directly to its same-named helper (or native construct per ADR-0009).
- The mapping reference lists, per patch: native construct vs helper, and the helper's exact ports.
