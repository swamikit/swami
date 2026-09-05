---
name: pattern-translation
description: Translate one Origami pattern into idiomatic SwiftUI. Parse the .origami's semantic IR, categorize each patch, walk the layer and dataflow graphs, and decide the SwiftUI construct. Native-first. Flag what won't translate. Hand the file shape and DocC surface off to the docc-authoring skill.
metadata:
  type: procedural
---

# Pattern translation

Judgment for turning one Origami pattern into a SwiftUI file. The parser produces facts. This skill decides how those facts land in SwiftUI.

This is the judgment half. The file-shape half (filename, struct, DocC header, catalog surface) lives in the sibling `docc-authoring` skill. Do not restate it here.

## What you must have

- One `.origami` file to translate.
- A parser that reads it and returns a semantic IR (see below).
- The public surface of your reference helper module. Read what is public and shipping before emitting any helper call. Do not invent helpers.

Missing any of these is a stop condition. Say what is missing.

## Format facts

- `.origami` is a zip. The graph document is `<name>.diamond/graph`. It is FlatBuffers with file_identifier `ORGM`; the root table starts at offset `0x30`. No `.fbs` schema ships with the file, so the walk is schema-less.
- The file embeds Origami's whole component library. The placed graph is a small subset. **Separating placed patches from library definitions is the core parsing challenge.** Root field 14 (`EdgeSwipe`, `Velocity`, `StickyBoundaries`, and so on) is the library, not the placed graph. Do not read the library as the document.
- Design tokens follow Origami's ColorKit and TypeKit model. A color is `{name, hex, alpha}` plus semantic role usages; type styles the same. The IR must preserve names, not only resolved values. You can always resolve a name to a value; you cannot recover the name from a value.
- Origami Studio's Resources folder ships **composite/system patches** as readable `.diamond/graph` files (origami core, iOS, Android, Desktop). Read those to port physics faithfully. **Primitive patches (Interaction, Transition, Add, Switch, Pop Animation, and other core built-ins) do not appear there.** They live in the app binary. Do not conclude a patch is missing from Origami because it is absent from the composite folder.

## Semantic IR

Each placed node the parser returns should carry:

- `type`: the patch id, for example `origami.Interaction`, `origami.ClassicAnimation`, `layer.Oval`. This is the key for the mapping.
- `name`: the human name from the graph, when present.
- `ports`: per-node input and output port names.
- `edges`: connections between output and input ports.
- `port_defaults`: constants on unconnected inputs (colors, sizes, durations, curves), with semantic names preserved.
- `table`: an opaque identifier that distinguishes duplicate nodes of the same `type`.

Ports, edges, and port defaults may not all be decoded yet in your parser. Where a step below needs them and they are not present, cross-check by hand against the `.origami` in Origami Studio's Inspector, or against the patch's composite `.diamond/graph` when one exists. Comment the gap in the emitted code. Do not fabricate.

The parser is deterministic. Run it once. Do not eyeball FlatBuffers.

## Categorize each patch

Every placed node falls into one of six categories. The category picks the SwiftUI target.

| Origami category | SwiftUI target |
|---|---|
| **Layer** (`layer.Oval`, `layer.Text`, groups, artboard) | `View` primitives and stacks (`Circle`, `Text`, `VStack`/`HStack`/`ZStack`) |
| **Pure value** (math, logic, colour and geometry expressions) | computed properties, operators, expressions |
| **Interaction** (`origami.Interaction`, `origami.DoubleTap`, `origami.LongPress`, `origami.Drag`) | gestures (`.onTapGesture`, `SpatialTapGesture`, `DragGesture`) plus `@State`/`@GestureState` |
| **State/memory** (`origami.Switch`, `origami.SampleAndHold`) | `@State` (or `@GestureState` when only alive during a gesture) |
| **Animation** (`origami.ClassicAnimation`, `origami.PopAnimation`, springs) | `withAnimation { ... }` or `.animation(...)` |
| **Transition** (`origami.Transition`) | an interpolation expression on a driving value. **Never SwiftUI's `.transition()` view modifier.** |

`Transition` is the most common misreading. It interpolates a value between two endpoints as a progress fraction moves from 0 to 1. It is not a view transition. Emit the linear case as arithmetic on the endpoints:

```swift
// t in 0...1; A and B are the endpoints from the Transition patch's inputs.
let value = A + (B - A) * t
```

For compound values (points, sizes, colors) interpolate each component with the same formula.

## Walk order

### 1. Layer tree first (bottom up)

The artboard is the root view. Its child layer tree becomes the SwiftUI `body`. Groups become the stack matching their axis. Individual layers become the primitive from the mapping table. Preserve semantic names for colors and type styles. Emit the layout before wiring behaviour.

### 2. State and interaction second

For each Interaction patch, emit its gesture modifier and any `@State`/`@GestureState` the graph reads from it. One patch, one gesture. Do not fold `Double Tap` or `Long Press` into `Interaction`; the Origami patches are separate and have separate ports.

For each State/memory patch, emit one `@State` property named after the Origami node. Wire the gesture's output through the graph's edges into the state update.

### 3. Animation third

Where the graph runs a state change through `ClassicAnimation` or a spring, wrap the state update in `withAnimation(...)` or attach `.animation(..., value:)`. Preserve the curve name from the IR (quadratic to `.easeInOut`, linear to `.linear`, and so on) and the duration.

### 4. Value expressions last

Pure-value patches resolve into the expressions they feed. A `Transition` on the scale port becomes the arithmetic that computes `scale` from the state.

## Helper conventions

- **Native-first.** Map to the most idiomatic native SwiftUI or Swift construct that faithfully expresses the patch. Math to operators. Logic to `&&`/`||`. Tap-with-position to `SpatialTapGesture`. Scroll to `ScrollView`. Loops to `ForEach`. Most `Layer.*` to `Shape`/`View` primitives. If a native API already fits, use it directly. Do not wrap it.
- **A helper earns its place when no single native API faithfully expresses the patch's semantics.** No recurrence threshold. No line budget. Helper eligibility follows fidelity, not frequency.
- **One helper equals one patch.** The helper is named after the patch, exposes exactly that patch's ports (inputs to parameters, outputs to bindings or callbacks), and does not bundle sibling patches. `Interaction` outputs `Down`, `Tap`, `Position`, `Force`. `Double Tap` and `Long Press` are separate patches with separate helpers.
- **Only call helpers that exist in the reference module today.** If a patch needs a helper that is not there, do not invent a signature. Flag it (see next section) and let the helper ship first, in its own change, before the pattern that needs it.

## Flag, don't fake

Some patches have no faithful native mapping and no shipped helper. The translator marks them and stops emitting code for them. A human decides. Do not paper over with an approximation.

Currently unsupported:

- **Non-linear `Transition` curves.** The linear form is emittable inline. Non-linear curves need a curve-aware helper; no stdlib primitive reproduces Origami's curves faithfully.
- **Continuous-time springs.** Origami's spring model does not map directly to SwiftUI's `.spring(response:dampingFraction:)`. Emit the closest system spring only when the graph's exact constants are decoded and the mismatch is commented.
- **Custom JS patches.** Not translatable without inspecting the JS body.
- **Absolute layout** driven by numeric positions with no semantic parent frame.

For each unsupported node, emit a comment at the call site naming the patch type and the reason. Silent drops mask parser gaps and reviewer signal.

```swift
// unsupported: origami.Transition non-linear curve, no faithful native primitive
```

## Verify

Compile is table stakes and lives outside this skill. Structural checks belong here.

- **Every placed node is accounted for.** Every entry the parser returned appears in the emitted file as a native construct, a helper call, or an `// unsupported:` comment. Silent drops hide parser gaps.
- **Constants match the source.** Colors, sizes, durations, and curves in the emitted code match what the Origami Inspector shows for that node. Where the parser has not decoded a port default, read the value by hand and comment the gap.
- **Helper calls match documented signatures.** Every helper is public in the reference module and is called with its exact ports.

The visual check compares the translated SwiftUI, rendered in a host, against Origami's own render of the same `.origami`. **Render both. Compare with your eye or with your project's chosen review path.** A perceptual similarity score, if the project prints one, is evidence, not a verdict; flat-color artboards give false positives on those metrics. The gate is a human read or the project's verify workflow, not a threshold.

## Hand-off

Stop at the code content. The file's shape (filename, struct name, DocC symbol header, catalog page, patch-mapping table) is the `docc-authoring` skill's job. Load it when you write the file to disk.
