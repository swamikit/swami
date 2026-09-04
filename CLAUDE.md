# CLAUDE.md — project memory for swami

Load before working here. Durable project context, not a task list.

## What this is

An Origami→SwiftUI translator: a deterministic **parser** (`.origami` → semantic IR) plus
a **codegen** (IR → SwiftUI). Parser for facts, codegen for the mapping. Read `docs/decisions/`.

## Deliverables (what's shipped at the end)

Earlier drafts listed seven; there are really four. Overlap collapsed for real:

1. **The Swift package (`Swami`)** — the patch-matched helper library (native-first,
   sized by Origami's patch surface per ADR-0009), the DocC in `Swami.docc/` (which is
   how the mapping reference reaches a human reader — there is no separate mapping
   doc), and a gallery/showcase surface for the translated corpus.
2. **The tool (`tool/`)** — parser + codegen. The "skill / MCP" packaging is the same
   code with an agent-facing entry point, not a separate artifact.
3. **The verified corpus** — every Origami Pattern translated + auto-compare-verified,
   living as DocC-embedded examples inside the Swift package (start there — keeps
   docs and examples in sync; split to a sibling repo only if it grows heavy).
4. **The methodology** — ADRs, verified-delivery, the beats. Not a shipped artifact;
   it's how 1–3 stay honest.

The harness (macOS-runner verify gate) sits under all four as the fidelity oracle —
means, not a deliverable.

## Format facts (`.origami`)

- `.origami` is a **zip**; the graph doc is `<name>.diamond/graph`, **FlatBuffers**, file_identifier **`ORGM`**, root table at offset 0x30. No `.fbs` schema ships (it's compiled in) → schema-less walk.
- The file embeds Origami's whole component **library**; the *placed* graph is a small subset. **Separating placed patches from library definitions is THE core parsing challenge.** Root field 14 (EdgeSwipe, Velocity, StickyBoundaries, …) is the LIBRARY, not the placed graph — do not mistake it for the document (a prior session did, and generated the wrong app).
- Placed nodes cluster in the file **tail region (~373k–401k)** for the Touch example. ~25 placed nodes / ~44 edges is the real graph (vs 356/395 library-inclusive).
- Design tokens follow Origami's ColorKit/TypeKit model: a color is `{name, hex, alpha}` plus `colorUsages` (semantic roles); type styles likewise. Preserve these names in the IR (ADR-0007).
- **Patch docs are compiled into the app** (2026-09-03). Structural metadata is FlatBuffers fields: `category`, `enumOptions`, `libraryInfo`, `availableInComponentsOnly`, and a per-patch `useNewDocumentation` bool (newer patches defer to origami.design docs; older carry inline prose). Human-readable descriptions ship as compiled strings (e.g. Velocity: "Measure the speed that a value is changing… ex: Drag, Scroll").
- **Complete catalog = the app itself, not the web.** `Origami Studio.app/Contents/Resources/Patches/*.origami-system/` holds **66 composite/system patches** as readable `.diamond/graph` FlatBuffers (our format): **origami core 24, iOS 16, Android 24 (material.*), Desktop 1**, each with `info.json`, icons, and `.m4a` SoundKit assets. Primitive patches (Interaction, Transition, Add, Switch, Pop Animation…) live in the binary, not as `.diamond` files. Web docs = secondary human cross-check only.
- **Composite graphs give faithful physics.** `origami.Drag` contains the full momentum impl as named nodes: Add Momentum, Rubber Band Friction, Rubber Band Tension, Stick To Boundaries, "Reset remaining velocity on touch up", Round to Screen Pixels, Clip/Set Position + Momentum. Port these 1:1 instead of approximating (retires the `drag()` TODOs from ADR-0009). Same for origami.Velocity, DoubleTap, LongPress, LegacyScroll, PopSwitch, ProgressRing, Shimmer, HitArea, GridLayout.

## The mapping model

Origami's patch graph and SwiftUI are both reactive dataflow. Target SwiftUI's state graph, not imperative functions:

| Origami | SwiftUI |
|---|---|
| Pure value patch (Add, Transition/interpolate, logic) | computed property / expression |
| Interaction (Tap, Down/press, Double Tap, Long Press) | gesture + `@State`/`@GestureState` |
| State/memory (Switch, Sample and Hold) | `@State` + update logic |
| Animation (Classic Animation, Pop/Spring) | `withAnimation` / `.animation(.spring)` |
| Layer tree | the `View` body |

Origami `Transition` = interpolation (not SwiftUI's `.transition()` modifier). Flag, don't fake: continuous-time springs, custom JS patches, absolute layout.

## Verified oracle — Touch Origami Example

The document is the tap/down/double-tap/long-press demo. Values read from the Inspector (parser must reproduce):
- Frame (card): cornerRadius **20** all corners, Size **Grow**, stroke width 0; Tap-frame background **white**.
- Oval: **100×100**, fill Origami Core **"Purple" = `#DD70DF`** (RGB 221,112,223), Transform Scale **0 at rest → 5** on Down (Classic Animation, quadratic, 0.5s).
- Group: vertical, spacing **30**. Artboard background = the same Purple.
- Mechanism: pressing grows the hidden 100×100 Oval inside the card — NOT scaling the card.

## Conventions

- Record non-trivial decisions as ADRs in `docs/decisions/`.
- Parser deterministic and dependency-light. IR **semantic-rich** (names, not just values).
- Verification is visual against the Origami render; corpus = Origami Patterns gallery.
- **Verify gate = XcodeBuildMCP** (local MCP on the Mac, proxied `mcp__remote-devices__XcodeBuildMCP__*`). Build/test/screenshot over MCP — no Terminal typing (Terminals/IDEs are click-only by macOS policy) and no Linux VM. Project: `/Volumes/SatechiSSD/Developer/Apps/Swift/swami/Origami_Patterns/Origami_Patterns.xcodeproj`, scheme `Origami_Patterns`, sims are iOS 26.2 (Trove ProMax `580207F9-…`). `build_sim` confirmed working 2026-09-03 (6.7s, clean). GAP: it's a framework target (no app to launch), so pixel render/screenshot needs a small preview-host app target or a snapshot test target (ImageRenderer). Compile gate is live now; visual gate pending that host. Cloud-side **syntax pre-gate**: `tree-sitter-swift` (pip) parses generated/helper Swift for ERROR/MISSING nodes — catches syntax errors without the Mac (not type errors). Use it before build_sim to fail fast.
- Parser TODO (unblocks faithful constants): decode a node's **input-port default values** (schema-less FlatBuffers union), not just node types/names. Needed to read exact patch defaults — e.g. origami.DragSettings' Momentum Friction / Rubber Band Friction — instead of iOS-standard stand-ins. `drag()` (Sources/Swami/Drag.swift) has faithful ports (Position/Translation/Velocity out; Enable/Momentum/bounds/Reset in) but TODO constants until this lands.
