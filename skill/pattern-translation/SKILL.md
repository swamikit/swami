---
name: pattern-translation
description: How to translate one Origami pattern into idiomatic SwiftUI. Reads the .origami file's semantic IR, maps patches to SwiftUI constructs (native-first per ADR-0009), emits a compilable Swift file. Community-portable — doesn't know about swamikit/swami's specific PR flow. Load into any agent (or human dev) that has the parser (tool/src/parser/), the Swami helper library (app/Swami/), and an .origami file to translate.
metadata:
  type: procedural
---

# Pattern translation — Origami .origami to SwiftUI

Translate one Origami pattern into a compilable SwiftUI file. This skill is the
**judgment half** of the translator: the parser produces facts (nodes, edges,
ports, values); this skill decides how those facts land in SwiftUI.

Community-portable by design. It does not mention `swamikit/swami`'s branches,
PR templates, or review flow. Those live in `skill/workflow/`. Load `workflow`
on top when you're opening a PR in this repo; load `pattern-translation` alone
elsewhere.

## Inputs you must have on hand

- **One `.origami` file** (the source pattern; bytes on disk).
- **The parser** at `tool/src/parser/` (`origami_graph.py`), able to walk the
  FlatBuffers graph and return the semantic IR (nodes, edges, patch types,
  ports where decoded).
- **The Swami helper library** at `app/Swami/` — read the public surface of the
  `.swift` files before you emit anything that references a helper. Only what
  is public and shipping is fair game.
- **The DocC mapping tables** at `app/Swami/Swami.docc/` — the per-category
  collection pages (`Interaction.md`, `Layer.md`, …) carry the current patch →
  SwiftUI decision for every patch known to the corpus. This is the authoritative
  mapping reference; read it before deciding native vs helper.
- **The load-bearing ADRs**:
  - **ADR-0009** — native-first; helpers only for recurring mismatches;
    inline-preferred delivery.
  - **ADR-0010** — bare, patch-matched helper names; one helper = one patch;
    ports match exactly.

Missing any of these is a stop condition. Say what's missing and don't guess.

## Translation flow

### 1. Parse `.origami` to semantic IR

Run the parser (`tool/src/parser/origami_graph.py`) on the file. What you need
out of it, per node:

- `patch_id` (e.g. `origami.Interaction`, `origami.ClassicAnimation`, `layer.Oval`).
- `name` (the human name, when present).
- `ports` (inputs and outputs; values when the port-default decoder has landed —
  see the parser TODOs before trusting constants).
- `edges` (which output feeds which input).

The parser is deterministic; run it once, work from its output. Do not eyeball
FlatBuffers.

### 2. Walk the IR; pick the SwiftUI mapping per patch

For each patch node, decide in this order:

1. **Check the DocC mapping table** (the collection page for the patch's
   category). If a decision is already recorded, use it.
2. **Helper exists?** If `app/Swami/` ships a public helper with the same name
   as the patch (`interaction(...)`, `drag(...)`, `sampleAndHold(...)`, …) and
   its port list matches, use it.
3. **Native SwiftUI covers it?** Per ADR-0009, map to the most idiomatic native
   construct. Math to operators, logic to `&&`/`||`, tap-with-position to
   `SpatialTapGesture`, scroll to `ScrollView`, loops to `ForEach`, most `Layer.*`
   to `Shape`/`View` primitives. **Do not wrap an API that already fits.** Reach
   for `SpatialTapGesture` directly rather than a `spatialTap()` helper.
4. **Neither native nor helper covers it?** Flag it. Emit a `// unsupported:
   <patch_id> — <reason>` comment at the call site; do not fabricate an API.
   Record the miss so a follow-up can decide whether a helper is warranted (per
   ADR-0009 point 3 — a helper earns its place when a patch recurs without a
   faithful native equivalent).

### 3. Layout — patches under the artboard become the `View` body

The Origami artboard is the root view. Its child layer tree becomes the SwiftUI
`body`. Groups become `VStack`/`HStack`/`ZStack` by their stacking axis;
individual layers become the corresponding SwiftUI primitive from the mapping
table (`Frame` → a shape or `.background`; `Oval` → `Circle`; `Text` → `Text`;
etc.). Preserve semantic names (color name, type style name) per ADR-0007 — the
IR carries them; the emitted code should too.

### 4. State — Origami's Interaction and State patches to `@State` + gestures

The **ISAT mapping** is the frame for this. Sam's framing: an Origami graph
resolves through *Interaction → State → Animation → Transition*, and SwiftUI's
declarative stack lands each stage as `gesture → @State → withAnimation →
interpolation`.

- **Interaction patches** (`origami.Interaction`, `origami.DoubleTap`,
  `origami.LongPress`, `origami.Drag`, …) become SwiftUI gesture modifiers —
  `.onTapGesture`, `.interaction()`, `.gesture(DragGesture(…))`, etc. One patch
  per gesture modifier; do not fold `Double Tap` and `Long Press` into
  `Interaction` (ADR-0010: they are separate patches with separate helpers).
- **State patches** (`origami.Switch`, `origami.SampleAndHold`, memory-carrying
  logic) become `@State` (or `@GestureState` when the value only lives for the
  gesture's duration). One `@State` property per stored value; name it after
  the Origami node.

### 5. Animation — Classic and Spring become `withAnimation` / `.animation`

- `origami.ClassicAnimation` → `.animation(.easeInOut(duration: <t>), value: <v>)`
  or `withAnimation(.easeInOut(…)) { … }` when the transition is state-driven.
  Preserve the curve name from the IR (quadratic → `.easeInOut`, linear →
  `.linear`, etc.).
- `origami.PopAnimation` / spring patches → `.spring(response:, dampingFraction:)`
  or `.interpolatingSpring(…)`. Faithful continuous-time springs are a flagged
  hard case per CLAUDE.md — if the parser hasn't decoded exact constants, emit
  the closest system spring and comment the mismatch.

### 6. Transition — `origami.Transition` is interpolation, not `.transition()`

Origami's `Transition` patch **interpolates a value between two endpoints as a
progress fraction moves 0 to 1**. It is a value expression, not the SwiftUI
`.transition()` view modifier. Emit it as a computed expression in the body
(e.g. `startValue.interpolated(to: endValue, by: progress)` or a plain
`lerp(...)`), never as `.transition(...)`. This is the most common
misreading; do not repeat it.

### 7. Emit compilable Swift with a DocC sample-code header

One file per pattern, `public struct <PatternID>: View`. Filename, struct name,
and DocC page name all match (per `skill/docc-authoring`). Include the
sample-code doc comment so the file renders in DocC as a sample-code page:

```swift
/// # <Category> — <Name>
///
/// @Metadata {
///     @PageKind(sampleCode)
///     @PageImage(purpose: card, source: "<PatternID>")
/// }
///
/// <One or two sentences: what the pattern does, which patches drive it.>
public struct <PatternID>: View {
    // @State properties from step 4
    // body from steps 3–6
}
```

Filename and struct name follow the Origami sidebar category + pattern name:
`Interaction_Touch`, `Layer_Oval`, `Interaction_Drag`. See
`skill/docc-authoring/SKILL.md` for the full page shape and the collection
mapping-table convention.

## Structural self-verification (before opening a PR)

Compile-gate is table stakes and lives elsewhere (the harness). This skill
covers the *structural* checks you can run on the emitted file itself.

For each helper the file calls:

- **Port list matches** the Origami patch's ports, one-to-one, per ADR-0010.
  Inputs become helper parameters; outputs become bindings or callbacks. No
  helper call may pass a port that isn't on the patch, or drop a port that is.
- **Values are sensible.** Constants read from the IR match the Origami
  Inspector's values for that node (colors, sizes, durations, curves). If the
  parser hasn't decoded a value yet (see `NEEDS-VERIFY.md` and the parser
  TODOs), use the documented default and add a `// TODO: parser-decoded
  default when available` comment — do not guess.
- **All patch nodes accounted for.** Every node in the IR appears in the
  emitted file — as a helper call, a native construct, or an `// unsupported`
  comment. Silent drops mask parser gaps.

Port-list checking becomes automatable when the parser's port-extraction pass
lands (see `NEEDS-VERIFY.md`). Until then, cross-check by hand against the
patch's public port list in the DocC mapping table.

## Output shape

- **One file**: `<PatternID>.swift`.
- **One public struct**: `public struct <PatternID>: View`.
- **DocC sample-code header** per step 7.
- **Follows `skill/docc-authoring`** for the doc-comment shape and the
  collection-page mapping-table convention.

## What NOT to do

- **Do not wrap a native SwiftUI API in a helper.** If `SpatialTapGesture` or
  `ScrollView` fits, use it directly. Wrapping is prohibited by ADR-0009; the
  win is *knowing* to reach for the native construct, not renaming it.
- **Do not guess at helper APIs.** Only call helpers that are public in
  `app/Swami/` right now. If you find yourself needing a helper that isn't
  there, flag the pattern as blocked on that helper and stop — do not invent
  a signature.
- **Do not emit `.swift` that references helpers that don't exist yet.** A
  file that won't compile against `app/Swami/` HEAD is not a translation; it's
  a proposal for a helper. Ship the helper first (its own PR), then the
  pattern.
- **Do not translate `origami.Transition` as SwiftUI `.transition()`.** It is
  interpolation. Step 6.
- **Do not bundle multiple patches into one helper call.** One patch, one
  helper. ADR-0010.
- **Do not silently drop unsupported patches.** Emit an `// unsupported`
  comment at the call site so the miss is visible to the Reviewer and to the
  next translator.

## Where to read next

- **`skill/docc-authoring/SKILL.md`** — the DocC page shape the emitted file's
  header must match, and the collection-page mapping-table conventions.
- **`docs/decisions/0009-native-first-helpers-for-recurring-mismatches.md`** —
  the native-first rule that drives step 2.
- **`docs/decisions/0010-helper-naming-and-faithful-patch-mapping.md`** —
  helper naming and the one-patch-one-helper rule.
- **`app/Swami/Swami.docc/`** — the mapping tables that are the source of
  truth for "native or helper?" per patch.
- **`NEEDS-VERIFY.md`** — the parser gaps that constrain what "faithful"
  currently means (placed-vs-library isolation, port-default decoding).
