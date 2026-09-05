---
name: pattern-translation
description: Translate one Origami pattern (.origami file) into one idiomatic SwiftUI file. Self-contained, community-portable playbook. Covers the judgment procedure for mapping Origami's dataflow patch graph onto SwiftUI's declarative state graph. Load whenever you have a .origami file and a target SwiftUI reference project with a Swami-shaped helper module.
metadata:
  type: procedural
---

# Pattern translation: Origami .origami to SwiftUI

## This is a portable skill

This file is the whole skill. It carries every fact it needs: the mapping model,
the format facts, the helper conventions, the verification bar. Nothing links out
to a private repo layout, an ADR file, or an internal branching model.

Shape:

- **Input**: one `.origami` file plus a SwiftUI reference project that ships a
  Swami-shaped helper module (a Swift module whose public API is one function
  per Origami patch that recurs enough to earn a helper).
- **Output**: one Swift file per pattern that compiles against that module and
  renders faithfully.
- **Sibling skill**: `skill/docc-authoring/` in this same skills directory owns
  the file-name, struct-name, and DocC-page shape of that output file. Load it
  alongside this one when you emit the file.

Lift the file verbatim into any repo whose reference project matches that shape.

## The mapping model

Origami's patch graph and SwiftUI are both reactive dataflow. Target SwiftUI's
state graph, not imperative functions. Every placed patch maps to one row of
this table:

| Origami                                                | SwiftUI                                       |
|--------------------------------------------------------|-----------------------------------------------|
| Pure value patch (Add, Transition/interpolate, logic)  | computed property / expression                |
| Interaction (Tap, Down/press, Double Tap, Long Press)  | gesture + `@State` / `@GestureState`          |
| State / memory (Switch, Sample and Hold)               | `@State` + update logic                       |
| Animation (Classic Animation, Pop / Spring)            | `withAnimation` / `.animation(.spring)`       |
| Layer tree                                             | the `View` body                               |

### ISAT beats

Every Origami graph resolves through **Interaction → State → Animation →
Transition**. That is the order in which the user's touch becomes pixels on
screen, and it maps 1:1 onto SwiftUI's stack:

- **I**nteraction → `gesture`
- **S**tate → `@State`
- **A**nimation → `withAnimation`
- **T**ransition → interpolation (an expression, see below)

Walk the graph in ISAT order and the SwiftUI falls out.

### The Transition trap

Origami's `Transition` patch **interpolates a value between two endpoints as a
progress fraction moves 0 to 1**. It is a value expression.

It is **not** SwiftUI's `.transition(...)` view modifier. `.transition(...)` is
an animation category (opacity, slide, scale on insertion/removal), not a
data-flow pattern. Getting this wrong wastes hours. If you catch yourself
reaching for `.transition(...)`, stop.

Emit the linear case as plain arithmetic on the endpoints and progress the
graph gives you:

```swift
// t in 0...1; A and B are the endpoints from the Transition patch's ports.
let value = A + (B - A) * t
```

For compound endpoints (points, sizes, colors), interpolate each component
with the same formula.

### Flag, don't fake

When a patch does not have a faithful native or helper equivalent, **mark the
site and stop**. Do not invent a helper name; do not paste a plausible-looking
call that will compile but lie. The list of known-unsupported cases:

- **Continuous-time springs.** SwiftUI's springs are frame-timed;
  Origami's are continuous. Emit the closest system spring only when the
  reference project has no faithful helper, and comment the mismatch.
- **Custom JS patches.** User-authored patches with arbitrary JS bodies.
  No mechanical translation; flag as unsupported.
- **Absolute layout.** Pixel-anchored positioning that fights SwiftUI's
  layout system. Flag; do not force with `.offset(x:y:)` gymnastics.
- **Non-linear Transition curves.** No linear-only stdlib primitive emits
  a faithful Origami easing curve inline. A fake `ease(t)` call is worse
  than a `// unsupported` comment. Flag until the reference project ships
  a curve-aware helper.

Emit `// unsupported: <patch-type>, <one-line reason>` at the site. Leave
the value unwired.

## Format facts: the .origami file

A community user parsing `.origami` by hand needs these:

- `.origami` is a **zip**. The graph document inside is
  `<name>.diamond/graph`, a **FlatBuffers** binary with file_identifier
  `ORGM` and the root table at offset **`0x30`**. No `.fbs` schema ships;
  the walk is schema-less.
- The file embeds Origami's whole component **library** alongside the placed
  graph. The placed (in-use) graph is a small subset in the file tail.
  **Separating placed patches from library definitions is THE core parsing
  challenge.** Root field 14 is the library (EdgeSwipe, Velocity,
  StickyBoundaries, ...), NOT the document. A parser that treats field 14 as
  the document generates the wrong app.
- The complete patch catalog lives at
  `Origami Studio.app/Contents/Resources/Patches/*.origami-system/`. That
  folder holds 66 composite / system patches as readable `.diamond/graph`
  FlatBuffers.
  On a macOS host with Origami Studio installed, that path is directly
  readable. Use it to cross-check patch semantics against the compiled
  source rather than the web docs.

Ports and port default values inside the `.origami` file are inside the
schema-less union payload. Reading them robustly is a parser problem; if your
parser has not decoded them, either read the values from Origami Studio's
Inspector by hand or use the patch's documented defaults, and leave a
`// TODO: parser-decoded default when available` comment. Do not guess.

## The reference project

This skill assumes the target SwiftUI project has three surfaces. Rename to fit
local conventions; the shape is what matters.

- **A Swami-shaped helper module.** A Swift module whose public API is one
  function per recurring Origami patch. Read the module's public surface
  before you emit anything that references a helper; only public and shipping
  helpers are fair game.
- **A `Patterns/` folder.** One Swift file per translated Origami pattern.
- **A host app target.** Renders each pattern for the visual verify gate
  (a simulator screenshot or a live preview).

### Helper conventions

Two rules govern the helper module. Both belong in the module's own docs;
restated here so this skill stands alone.

- **Native-first.** Prefer stdlib and native SwiftUI over adding a helper.
  Reach for `SpatialTapGesture` directly instead of wrapping it in
  `spatialTap()`. A helper earns its place when no clean native construct
  faithfully expresses the patch's semantics, and it preserves the patch's
  port semantics 1:1. Fidelity to the patch is the bar — there is no
  recurrence threshold and no line budget; the library is sized by
  Origami's patch surface, not by an arbitrary cap.
- **One patch = one helper.** Helpers are named after the patch
  (`drag(...)`, `interaction(...)`, `doubleTap(...)`). No bundled convenience
  wrappers that fold Double Tap + Long Press + Tap into one call. The named
  ports on the Origami patch become the named parameters on the Swift
  helper, in the same order.

## Judgment procedure

This is the flow. Facts above; procedure here.

### a. Parse

Run the project's `.origami` parser. Get the placed graph: nodes (each with a
patch type id and a human name), connections between output and input ports,
and the layer tree. Fall back to Origami Studio's Inspector for anything the
parser has not yet decoded.

### b. Categorize every node

For each placed node, decide its row in the mapping model table above.

1. Category covered by the table? Use the corresponding SwiftUI construct.
2. A helper with the exact patch name exists in the reference project's helper
   module? Call it with the ports the parser gave you.
3. Native SwiftUI fits directly? Use it (`ScrollView`, `SpatialTapGesture`,
   `Circle`, `ForEach`, arithmetic operators for math). Do not wrap.
4. None of the above? Apply **Flag, don't fake**.

### c. Layer tree → View body

Walk the artboard's child layer tree bottom-up. Groups become
`VStack` / `HStack` / `ZStack` by stacking axis. Individual layers map to
their SwiftUI primitive: `Frame` becomes a shape or `.background`, `Oval`
becomes `Circle`, `Text` stays `Text`. Preserve semantic names from the IR
(color tokens, type-style names) in the emitted code.

### d. Interaction / State / Animation → gestures + @State + withAnimation

Walk the ISAT half of the graph:

- **Interaction patches** (`origami.Interaction`, `origami.DoubleTap`,
  `origami.LongPress`, `origami.Drag`, ...) become gesture modifiers.
  One patch, one modifier. Do not fold `Double Tap` and `Long Press` into
  `Interaction`.
- **State patches** (`origami.Switch`, `origami.SampleAndHold`,
  memory-carrying logic) become `@State`. Use `@GestureState` when the value
  only lives for the gesture's duration. One `@State` property per stored
  value; name it after the Origami node.
- **Animation patches** (`origami.ClassicAnimation`, `origami.PopAnimation`,
  spring patches) become `.animation(...)` or `withAnimation { ... }`.
  Preserve the curve name (quadratic → `.easeInOut`, linear → `.linear`).
  For springs where the parser has not decoded exact constants, emit the
  closest system spring and comment the mismatch.
- **Transition patches** become interpolation expressions per the arithmetic
  above. Never `.transition(...)`.

### e. Emit one Swift file

One Swift file per pattern, one `public struct <PatternID>: View`. File name,
struct name, and DocC page name follow **`skill/docc-authoring/`**. That
sibling skill owns the header, doc-comment, and file-layout conventions.
This skill stops at the code content; that one starts at the wrapper.

### f. Render and compare

The gate is visual, not compile.

- Render the pattern in a simulator or SwiftUI preview at the same viewport
  the Origami artboard uses.
- Compare side-by-side against Origami's live render (or its
  `View → Take Screenshot` export).
- **Pixel evidence**: SSIM ≥ 0.95 on the same viewport dimensions is
  evidence. A human eyeball on the render is the minimum.
- **Never claim a translation is done from a clean compile alone.** A file
  that compiles and renders wrong is not a translation.

Iterate steps b through f until the render matches. Every unmatched
difference is either a bug in the emitted code, a parser gap, or a
legitimate flagged case. Decide which, then act.

## Structural self-checks before you ship

Run these on the emitted file before handing it off.

- **Every placed node is accounted for.** Each node in the parser's
  placed-node list appears in the file as a helper call, a native construct,
  or an `// unsupported:` comment. Silent drops mask parser gaps.
- **Constants match the Origami Inspector.** Colors, sizes, durations,
  curves in the emitted code match what the Inspector shows for the source
  patch. Where the parser has not decoded a port default, the value is a
  documented patch default and carries a
  `// TODO: parser-decoded default when available` comment.
- **Every helper call matches a public signature.** Every helper you invoke
  exists in the reference project's helper module today and is called with
  its documented named parameters. No invented helper names, no invented
  parameter names.

## What NOT to do

- Do not wrap a native SwiftUI API in a helper. If `SpatialTapGesture` or
  `ScrollView` fits, call it directly.
- Do not invent helper signatures. Only call helpers that ship in the
  reference project's module right now. A file that references a
  non-existent helper is a proposal for that helper, not a translation.
- Do not translate `origami.Transition` as SwiftUI `.transition(...)`. It
  is interpolation. See the mapping model.
- Do not bundle multiple patches into one helper call. One patch, one
  helper.
- Do not silently drop unsupported patches. Emit the `// unsupported`
  comment at the call site so the miss is visible to the next reader.
- Do not claim a translation is done because it compiles. Compile is
  necessary, never sufficient. The gate is visual.
