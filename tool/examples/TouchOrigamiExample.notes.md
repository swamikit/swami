# Touch Origami Example — translation notes

Companion to `TouchOrigamiExample.swift`. What was recovered, how it mapped, and what
didn't map cleanly. This is the first stress-test of the `CLAUDE.md` mapping table
against a real file.

## Fidelity (read this first)

`TouchOrigamiExample.swift` is a **pattern-level reconstruction**, not a faithful
edge-level transpile. It was produced from:

- the **recoverable** graph content — patch types, layer/port names, values
  (see `docs/format/origami-graph-format.md`), and
- the **mapping table** in `CLAUDE.md`.

The **port-to-port wiring was not parsed** (it lives in the FlatBuffers tables; that's
the `src/parser` job, ADR 0001). So the dataflow in the Swift file is *inferred from
labels*, not read from the file. Treat it as a strong hypothesis of intent, to be
validated once the parser can read edges.

## What the prototype does

An interactive iOS **modal / card presentation**: a card pushes up over a dimming
gradient background and is dismissed by dragging down or an edge swipe, with
velocity-based physics and a bouncy pop. Recovered designer labels that tell the story:
`Modal Transition`, `Push Background`, `Push Gradient`, `Push Positioning`,
`Push Progress`, `Screen Progress`, `Edge Swipe Dismiss`, `Pop Animation`,
`Sticky Boundaries`, `Smooth Value On Drag Release`, `Touch Velocity`, `Content Stack`,
`Gradient Fill` (`Start/End Color`, `Start/End Position`).

## Mapping applied

| Origami patch(es) | SwiftUI | Confidence |
|---|---|---|
| `ios.Screen`, `builtin.switch` | `@State isPresented` + present/dismiss | inferred |
| `builtin.deviceInfo` (Screen Height/Width, Safe Area) | `GeometryReader` proxy size | confirmed present |
| `builtin.layer.layer` / `.text` / `.ellipse` | `ZStack` / `Text` / `Capsule` | confirmed present |
| `builtin.layer.gradient`, "Gradient Fill" | `LinearGradient` (start/end color+position) | confirmed present |
| "Content Stack" (Layout Kit) | `VStack` | inferred |
| `builtin.progress`, "Push/Screen Progress", `builtin.range` | computed `progress()` 0…1 | inferred |
| "Push Positioning" | `.offset(y:)` from computed `cardOffset()` | inferred |
| `ios.StickyBoundaries` | `max(...)` clamp on offset | inferred |
| interaction patches (Tap, Drag) | `DragGesture` + `.onTapGesture` | inferred wiring |
| `origami.Velocity`, `ios.Smoothvalueondragrelease` | `predictedEndTranslation` + `@GestureState` auto-reset | approximation |
| `builtin.bouncy` ("Pop Animation") | `.bouncy` spring | confirmed present |
| `builtin.classicAnimation` (easing enum) | `.easeIn/.easeOut/.easeInOut` / custom `Animation` | not used here (bouncy chosen) |
| `builtin.transition` ("Modal Transition") | `.offset`/opacity drive; could be `.transition`/`matchedGeometryEffect` | inferred |

## Hard cases surfaced (flag, don't fake)

1. **Continuous-time velocity spring.** `origami.Velocity` → `ios.Smoothvalueondragrelease`
   → `builtin.bouncy` is a real-time physics chain. SwiftUI has no closed-form
   equivalent; `value.predictedEndTranslation` + `.bouncy` is the standard
   approximation. Behaviour will diverge for fast flicks. **Approximated + flagged.**
2. **Edge-swipe gating.** `ios.EdgeSwipeDetection` + "Edge Threshold" fire only when the
   touch starts within N pt of the screen edge. The seed uses a plain drag for
   reviewability and notes the omission rather than faking the edge geometry.
3. **Wireless broadcaster/receiver links.** The graph uses `builtin.wirelessBroadcaster`/
   `wirelessReceiver` (connect by name, not by a drawn wire). Until the parser resolves
   these by name, some dataflow is invisible to a wire-following parser. **Parser TODO.**
4. **Groups / components.** `builtin.group.input`/`output` mean the graph is
   hierarchical (sub-graphs). The IR must represent nesting; the seed flattens it.

## What the parser must extract next to make this faithful

- Port-to-port edges from the FlatBuffers tables (the wiring).
- Resolution of wireless broadcaster/receiver names into edges.
- Group boundaries + component sub-graphs.
- Per-port literal values bound to specific inputs (colors, thresholds, durations).

With those, this seed can be regenerated as a validated translation instead of an
inferred one.
