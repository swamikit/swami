# Drag

@Metadata {
    @PageKind(article)
}

Drag a layer with momentum and rubber-band bounds — Origami's `origami.Drag` patch, as a
one-line SwiftUI modifier.

## Overview

`.drag(…)` gives any layer the Drag patch's behavior. Attach it and pass only what you need:

- term `momentum`: carries the throw after you let go, then eases to a stop.
- term `bounds`: a `min`/`max` extent the layer rubber-bands back inside.
- term `position` / `translation` / `velocity`: write the live Drag outputs back to your own state.
- term `enable` / `reset`: turn the gesture off, or snap the layer back to its start.

```swift
@State private var position: CGSize = .zero

RoundedRectangle(cornerRadius: 20)
    .drag(momentum: true, bounds: bounds, position: $position)
```

Each parameter mirrors a Drag output/input port from the Origami patch. For the full
declaration, see ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)``.

## Topics

### Used in

- <doc:Interaction_Drag>
