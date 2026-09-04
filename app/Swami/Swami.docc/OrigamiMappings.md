# Origami → SwiftUI mappings

How Swami translates the four kinds of Origami patch into SwiftUI's state graph.

@Metadata {
    @PageKind(article)
}

## Overview

Origami's patch graph and SwiftUI are both reactive dataflow, so the translator
targets SwiftUI's *state graph* — computed properties, `@State`, `withAnimation` —
not imperative functions. Each row below is a rule the codegen applies; the helper
library (``Interaction``, ``Drag``, …) fills the gaps where a patch has no direct
SwiftUI equivalent.

## The four rules

| Origami | SwiftUI |
|---|---|
| Pure value patch (Add, Transition/interpolate, logic) | computed property / expression |
| Interaction (Tap, Down/press, Double Tap, Long Press) | gesture + `@State` / `@GestureState` |
| State/memory (Switch, Sample and Hold) | `@State` + update logic |
| Animation (Classic Animation, Pop/Spring) | `withAnimation` / `.animation(.spring)` |

The Origami layer tree becomes the SwiftUI `View` body. Origami `Transition` means
interpolation (not SwiftUI's `.transition()` modifier — that's a different concept).

### Pure value patch → computed property

`Add`, `Transition/interpolate`, and other pure-function patches carry no state.
They fan an input through math and emit an output. In SwiftUI that's a computed
property (or an inline expression) — no `@State`, no side effect.

### Interaction → gesture + `@State`

Origami's Interaction patch exposes discrete output ports: `down`, `position`,
`onTap`, `onDoubleTap`, `onLongPress`. Each maps to a SwiftUI gesture recognizer
whose output lands in `@State` or fires a callback. The ``Interaction`` helper
attaches only the recognizer for each output the caller requests, which keeps
gesture arbitration clean.

### State/memory → `@State` + update logic

`Switch` and `Sample and Hold` remember a value across evaluations. That's what
`@State` is for. Codegen emits the state variable plus the update path (a gesture
callback, a `.onChange`, or an assignment inside a `withAnimation` block).

### Animation → `withAnimation` / `.animation`

`Classic Animation`, `Pop Animation`, and other animation patches drive a value
toward a target over time. In SwiftUI, that's a state change wrapped in
`withAnimation` or an `.animation(_:value:)` modifier on the animated property.
Continuous-time springs that don't have a stock SwiftUI equivalent get flagged
by the parser — Swami won't fake them.

## Flag, don't fake

Some Origami semantics don't have a SwiftUI equivalent. When the parser hits one,
it emits a marker in the IR and codegen surfaces the gap rather than papering over
it. The current list: continuous-time springs, custom JavaScript patches,
absolute-position layout.
