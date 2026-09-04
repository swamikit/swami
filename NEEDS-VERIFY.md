# NEEDS-VERIFY — drive-gate backlog (verified-delivery)

Nothing here is "done." Each item is DRAFT/UNVERIFIED until an agent drives the real running
product (XcodeBuildMCP `build_run_sim` → `screenshot`, read against intent, compared to the
Origami artboard) AND Samuel spot-checks. A clean compile is necessary, never sufficient.

Gate is blocked until the `SwamiHost` app target is wired into Swami.xcodeproj (framework has
nothing to launch). Compile-gating also requires code synced into the framework by Samuel's local
agent — the cloud loop does not write there.

## Queue
- **Touch (TouchOrigamiExample)** — LAYOUT-VERIFIED via SwamiHost screenshot (2026-09-03, Trove
  ProMax iOS 26.2): magenta bg #DD70DF ✓, white Tap card ✓, radius ~20 ✓, spacing ~30 ✓, 4 rows in
  order ✓, ovals correctly invisible at rest ✓. NOT done — two open items:
  (a) Down/DoubleTap/LongPress card tints (progressive pink) are UNCONFIRMED vs the real Origami
      artboard — the oracle only pinned "Tap frame white"; compare side-by-side or Samuel's eye.
  (b) INTERACTION undriven — static shot can't verify the 100×100 oval growing from the touch point
      on press/tap. Needs a driven gesture in the sim (touch-injection tool) or Samuel driving live.
- **drag() helper (origami.Drag)** — drafted, syntax-clean, NOT compiled in-framework, NOT driven.
  Momentum/rubber-band CONSTANTS are placeholders (iOS-standard), not Origami's real defaults
  (see parser TODO). Drive: fling → momentum decay matches Origami feel; over-drag past bounds →
  rubber-band resists then settles; release at rest → clamps; velocity reset on fresh touch.
- **Interaction_Drag (examples/Interaction_Drag.draft.swift)** — STRUCTURAL DRAFT only. Geometry,
  colors, bounds, layer count NOT read from the graph (parser tail heuristic over-includes the
  embedded Drag component on this 534 KB file). Must: (a) generalize the parser to isolate the real
  placed graph, (b) re-generate from true values, (c) drive-verify.

## Parser TODOs blocking faithful output
- **Placed-vs-library generalization** (core challenge): fixed tail offset (360000) is tuned to the
  Touch example; on Interaction_Drag (534 KB) it captures Drag's component internals as false
  "placed" nodes. Need a structural way to find the document's placed graph (root reference), not a
  byte offset. Blocks trustworthy translation of any pattern embedding composite patches.
- **Input-port default-value decoding**: DragSettings port defaults (Momentum/Rubber Band Friction,
  Clip) are NOT reachable by naive vtable field-offset walking (returns zeros / canvas coords).
  Values are a typed value-union stored indirectly — needs real union tag→payload decoding. Blocks
  faithful momentum constants in drag().
