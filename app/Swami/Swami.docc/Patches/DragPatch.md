# Drag

@Metadata {
    @PageKind(article)
}

Drag a layer with momentum and rubber-band bounds — Origami's `origami.Drag` patch, as a
one-line SwiftUI modifier.

## Overview

`.drag(…)` gives any layer the Drag patch's behavior: `momentum` carries the throw after
you let go and eases it to a stop, `bounds` is a `min`/`max` the layer rubber-bands back
inside, and `position` / `translation` / `velocity` write the live Drag outputs back to
your own state. Pass only what you need.

```swift
@State private var position: CGSize = .zero

RoundedRectangle(cornerRadius: 20)
    .drag(momentum: true, bounds: bounds, position: $position)
```

The full signature and every parameter live on the modifier itself:
``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)``.

## Topics

### Used in

- <doc:Interaction_Drag>
