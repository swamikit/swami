---
name: pattern-translation
description: How to translate one Origami pattern into idiomatic SwiftUI. Reads the .origami file's semantic IR, maps patches to SwiftUI constructs (native-first per ADR-0009), emits a compilable Swift file. Community-portable — doesn't know about swamikit/swami's specific PR flow. Load into any agent (or human dev) that has the parser (tool/src/parser/), the Swami helper library (app/Swami/), and an .origami file to translate.
metadata:
  type: procedural
---

# Pattern translation — Origami .origami to SwiftUI

Translate one Origami pattern into a compilable SwiftUI file. This skill is the
**judgment half** of the translator: the parser produces facts (placed nodes
today; edges, ports, and port defaults as the parser lands them); this skill
decides how those facts land in SwiftUI.

Community-portable by design. It does not mention `swamikit/swami`'s branches,
PR templates, or review flow. Those live in `skill/workflow/`. Load `workflow`
on top when you're opening a PR in this repo; load `pattern-translation` alone
elsewhere.

## Inputs you must have on hand

- **One `.origami` file** (the source pattern; bytes on disk).
- **The parser** at `tool/src/parser/` (`origami_graph.py`). Today it enumerates
  placed nodes only — see *Current parser limits* below for exactly what fields
  it produces. Treat anything else as not-yet-decoded.
- **The Swami helper library** at `app/Swami/` — read the public surface of the
  `.swift` files before you emit anything that references a helper. Only what
  is public and shipping is fair game.
- **The mapping model table** — the `## The mapping model` section in
  `AGENTS.md` / `CLAUDE.md` at the repo root. This is the current authoritative
  patch-category → SwiftUI-construct reference. (The per-category DocC
  collection pages under `app/Swami/Swami.docc/` are the eventual home for
  per-patch decisions but do not exist yet; do not block on them.)
- **The load-bearing ADRs**:
  - **ADR-0009** — native-first; helpers only for recurring mismatches;
    inline-preferred delivery.
  - **ADR-0010** — bare, patch-matched helper names; one helper = one patch;
    ports match exactly.

Missing the `.origami` file, the parser, `app/Swami/`, or the ADRs is a stop
condition. Say what's missing and don't guess.

### Current parser limits

`origami_graph.parse(path)` today returns a document dict with `placed_nodes`,
`placed_node_count`, and a `kinds` histogram. Each placed node has:

- `table` — its FlatBuffers table offset (opaque; disambiguates duplicates).
- `type` — the patch id string, e.g. `origami.Interaction`,
  `origami.ClassicAnimation`, `layer.Oval`. This is what the mapping model
  keys on.
- `name` — the human name from the graph, when present. May be `None`.

Not yet produced (tracked in the parser's `_todo` and in `NEEDS-VERIFY.md`):

- **edges** — connections between output and input ports.
- **ports** — the per-node input/output port list.
- **port default values** — the constants that live on unconnected inputs
  (colors, sizes, durations, curves).

Work from what's there. Where a step below asks for edges, ports, or exact
constants, cross-check by hand against the `.origami` in Origami Studio or the
patch's composite `.diamond/graph` in `Origami Studio.app/Contents/Resources/Patches/`,
and flag the missing-decoder gap so the follow-up can retire the workaround.

## Translation flow

### 1. Parse `.origami` to semantic IR

Run the parser (`tool/src/parser/origami_graph.py`) on the file. What you get
out of it, per placed node (see *Current parser limits* above):

- `type` — the patch id (e.g. `origami.Interaction`, `origami.ClassicAnimation`,
  `layer.Oval`). This is the key for the mapping model.
- `name` — the human name, when present.
- `table` — the FlatBuffers table offset (opaque; use only to distinguish
  duplicate nodes of the same `type`).

Ports, edges, and port default values are not yet decoded. Where later steps
need them (e.g. wiring interactions to state, reading exact durations or
colors), you'll either read them from the `.origami` in Origami Studio by hand
or fall back to documented defaults with a comment — do not fabricate.

The parser is deterministic; run it once, work from its output. Do not eyeball
FlatBuffers.

### 2. Walk the IR; pick the SwiftUI mapping per patch

For each patch node, decide in this order:

1. **Check the mapping model table** in `AGENTS.md` / `CLAUDE.md` (`## The
   mapping model`). If the node's category is covered there, use that as the
   SwiftUI target.
2. **Helper exists?** If `app/Swami/` HEAD ships a public helper with the same
   name as the patch (check the module for the current list), use it. Port-list
   matching is a per-helper check when the parser starts decoding ports; until
   then, follow the helper's documented signature. Only call helpers that are
   public in `app/Swami/` right now — do not invent one by name.
3. **Native SwiftUI covers it?** Per ADR-0009, map to the most idiomatic native
   construct. Math to operators, logic to `&&`/`||`, tap-with-position to
   `SpatialTapGesture`, scroll to `ScrollView`, loops to `ForEach`, most `Layer.*`
   to `Shape`/`View` primitives. **Do not wrap an API that already fits.** Reach
   for `SpatialTapGesture` directly rather than a `spatialTap()` helper.
4. **Neither native nor helper covers it?** Flag it. Emit a `// unsupported:
   <type> — <reason>` comment at the call site; do not fabricate an API.
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
`.transition()` view modifier — never emit it as `.transition(...)`. This is
the most common misreading; do not repeat it.

There is no `interpolated(to:by:)` method on Swift numerics, no stdlib `lerp`,
and no `app/Swami/` helper for this today. Emit the interpolation as a plain
arithmetic expression using the endpoints and progress the graph gives you:

```swift
// t in 0…1; A and B are the endpoints from the Transition patch's input ports.
let value = A + (B - A) * t
```

If the endpoints are compound values (points, sizes, colors), interpolate
each component with the same formula. The linear form above is authoritative
for the linear case only.

**Non-linear curves are unsupported at HEAD.** There is no easing helper
public in `app/Swami/` today and no stdlib primitive that emits a faithful
Origami curve inline (a plausible-looking `ease(t)` call is fake — the earlier
`interpolated(to:by:)` / `lerp(...)` guidance was the same defect one layer
up). Per AGENTS.md's "Flag, don't fake" rule (which lists continuous-time
springs, custom JS patches, and absolute layout — non-linear Transition
curves belong on the same list), the translator MUST flag any Transition
whose curve is not linear and stop generating code for it: emit an
`// unsupported: origami.Transition non-linear curve — no easing helper in
app/Swami/ (see #53)` comment at the site and leave the value unwired. Do
not invent a curve function; do not fall back to a stdlib approximation.

The resolution path is a separate `app/Swami/Transition.swift` PR (tracked
in #53) that ships a curve-aware helper with ports matching Origami's
Transition patch (ADR-0010). Once that helper is public, this section will
authorize its use for non-linear curves; until then, flag-and-stop is the
only correct output.

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

- **All placed nodes accounted for.** Every node in `placed_nodes` appears in
  the emitted file — as a helper call, a native construct, or an
  `// unsupported: <type>` comment. Silent drops mask parser gaps.
- **Values are sensible.** Constants used in the emitted code match the
  Origami Inspector's values for that node (colors, sizes, durations, curves)
  when you can cross-check them. Because the parser has not yet decoded port
  defaults (see *Current parser limits*), read the values from Origami Studio
  by hand or use the patch's documented default, and add a `// TODO:
  parser-decoded default when available` comment — do not guess.
- **Helper calls match documented signatures.** Every helper you invoke exists
  in `app/Swami/` HEAD and is called with its documented parameters (ADR-0010:
  one helper = one patch; ports match exactly). Full port-list-vs-patch
  checking becomes automatable when the parser's port-extraction pass lands;
  until then, this is a manual cross-check against the helper's Swift
  signature.

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

- **`AGENTS.md` / `CLAUDE.md`, `## The mapping model`** — the current
  patch-category → SwiftUI-construct table. Source of truth for step 2 until
  the per-category DocC collection pages land.
- **`skill/docc-authoring/SKILL.md`** — the DocC page shape the emitted file's
  header must match, and the collection-page mapping-table conventions.
- **`docs/decisions/0009-native-first-helpers-for-recurring-mismatches.md`** —
  the native-first rule that drives step 2.
- **`docs/decisions/0010-helper-naming-and-faithful-patch-mapping.md`** —
  helper naming and the one-patch-one-helper rule.
- **`NEEDS-VERIFY.md`** — the parser gaps that constrain what "faithful"
  currently means (placed-vs-library isolation, port-default decoding).
