# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
}

`Interaction_DragView` translates the Interaction Drag pattern into a full-screen
SwiftUI composition. The dimensions and colors are measured from the runner-produced
750×1334 RGBA reference. Its corresponding 375×667-point composition has a
`#DD70DF` canvas, a 315×607-point `#E5A6E6` interaction area, and a centered
120×120-point white card. The current-head
PR screenshot triplet verifies the rendered result rather than this page assuming a match.

## Interaction

Touching the card engages a zero-distance drag. While the card is moving, the
`drag` modifier:

- publishes position, translation, and velocity;
- applies the Drag patch's documented 0.15 rubber-band friction beyond the fixed bounds;
- projects release momentum and settles within those boundaries; and
- accepts every placed-graph reset pulse through the monotonic `resetCount` adapter.

The pattern composes the reset decision outside the helper, matching the placed
`Snap to origin` branch: two approximately-equal comparisons feed an And when
interaction turns off. The helper's release callback reports the touch-up position
without installing a competing gesture. A touch-up within 100 points of center on
both axes increments `resetCount`; each increment clears position, translation, and
velocity and returns the card to its origin.

## Verification media

The pull-request delivery generated from the same commit supplies the native
Swami, Origami, and difference screenshots plus the H.264 Maestro recording.
The page image is populated by the documentation publication pipeline from the
verified Swami render; it is not a hand-authored substitute.

## See Also

- ``Interaction_DragView``
- ``Drag``
