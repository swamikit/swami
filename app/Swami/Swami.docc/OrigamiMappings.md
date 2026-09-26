# Origami → SwiftUI reference

What each Origami patch becomes in SwiftUI, so you know which construct — or which
``Swami`` helper — to reach for.

@Metadata {
    @PageKind(article)
}

## Overview

Origami's patch graph and SwiftUI both describe how values flow and change over
time, so the translations map onto SwiftUI's own tools: computed properties for
pure math, gestures and `@State` for interaction, `withAnimation` for motion. Most
patches land on a native SwiftUI construct. A few need a helper from the ``Swami``
library, named after the patch it stands in for.

## Patch → SwiftUI

| Origami patch | SwiftUI |
|---|---|
| Pure value patch (Add, interpolate, logic) | computed property / expression (native) |
| Interaction (Tap, Press, Double Tap, Long Press) | gesture + `@State` via ``Interaction`` (helper) |
| `origami.Drag` — Drag | ``drag(enable:momentum:bounds:position:translation:velocity:reset:)`` (helper) |
| Magnification / Pinch | `MagnifyGesture` (native) |
| `origami.PopSwitch` — Pop Switch | `@State` flipped on a threshold, `.spring` pop (native) |
| `builtin.layer.shape` — Shape (triangle) | ``RoundedTriangle`` (helper) |
| State / memory (Switch, Sample and Hold) | `@State` + update logic (native) |
| Animation (Classic Animation, Pop / Spring) | `withAnimation` / `.animation(.spring)` (native) |

The Origami layer tree becomes the SwiftUI `View` body.

## How the categories map

**Pure value patches** — `Add`, interpolation, logic — carry no state. They run an
input through math and emit a result, which is exactly a computed property or an
inline expression.

**Interaction** exposes discrete outputs: `down`, `position`, `onTap`,
`onDoubleTap`, `onLongPress`. Each becomes a SwiftUI gesture whose result lands in
`@State` or fires a callback. The ``Interaction`` helper attaches only the
recognizers you ask for, so gesture arbitration stays clean.

**State and memory** — `Switch`, `Sample and Hold`, `Pop Switch` — remember a value
between evaluations. That is what `@State` is for; the update path is a gesture
callback, an `.onChange`, or an assignment.

**Animation** — `Classic Animation`, `Pop Animation` — drives a value toward a
target over time, which is a state change wrapped in `withAnimation` or an
`.animation(_:value:)` modifier.

One naming note: Origami's `Transition` means *interpolation* (mapping one range
onto another), not SwiftUI's `.transition()` modifier for view insertion and
removal.

## When a mapping isn't exact

Some Origami semantics have no direct SwiftUI equivalent — continuous-time springs,
custom JavaScript patches, absolute-position layout. Rather than approximate them
silently, each translated view marks the gap with an inline `TODO` in its source,
so the caveat travels with the code. The individual pattern pages link to the
source where those notes live.
