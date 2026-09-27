# Interaction

@Metadata {
    @PageKind(article)
}

Touch outputs — down, position, tap, double-tap, long-press — wired straight into your
view's state. Origami's `origami.Interaction` patch, as a SwiftUI modifier.

## Overview

`.interaction(…)` attaches only the gesture for each output you pass, so a tap-only layer
carries just a tap recognizer, with no stray drag to fight it. `down` is `true` while a
finger is on the layer, `position` is the touch point in the layer's own coordinate space,
and `onTap` / `onDoubleTap` / `onLongPress` fire once on that gesture.

```swift
Circle()
    .interaction(down: $isPressed, position: $touch, onTap: { pop() })
```

The full signature and every parameter live on the modifier itself:
``View/interaction(down:position:onTap:onDoubleTap:onLongPress:)``.
