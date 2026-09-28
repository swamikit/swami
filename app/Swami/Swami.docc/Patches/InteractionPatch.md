# Interaction

@Metadata {
    @PageKind(article)
}

Touch outputs — down, position, tap, double-tap, long-press — wired straight into your
view's state. Origami's `origami.Interaction` patch, as a SwiftUI modifier.

## Overview

`.interaction(…)` attaches only the gesture for each output you pass, so a tap-only layer
carries just a tap recognizer, with no stray drag to fight it:

- term `down`: `true` while a finger is on the layer.
- term `position`: the touch point, in the layer's own coordinate space.
- term `onTap` / `onDoubleTap` / `onLongPress`: fire once, on that gesture.

```swift
Circle()
    .interaction(down: $isPressed, position: $touch, onTap: { pop() })
```

Each parameter mirrors an Interaction output port from the Origami patch. For the full
declaration, see ``View/interaction(down:position:onTap:onDoubleTap:onLongPress:)``.
