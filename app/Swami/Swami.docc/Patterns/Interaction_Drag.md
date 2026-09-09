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

Touching the card engages a zero-distance drag. While the card is moving,
`drag(enable:momentum:bounds:start:position:translation:velocity:reset:)`:

- publishes position, translation, and velocity;
- applies rubber-band resistance beyond the inset area's boundaries;
- projects release momentum and settles within those boundaries; and
- accepts the placed graph's reset pulse through Drag's `reset` input.

The pattern composes that reset pulse outside the helper, matching the placed
`Snap to origin` branch: two approximately-equal comparisons feed an And when
interaction turns off. A touch-up within 100 points of center on both axes resets
the card; Drag itself does not expose an app-specific release predicate.

## Verification media

The pull-request delivery generated from the same commit supplies the native
Swami, Origami, and difference screenshots plus the H.264 Maestro recording.
The page image is populated by the documentation publication pipeline from the
verified Swami render; it is not a hand-authored substitute.

## See Also

- ``Interaction_DragView``
- ``Drag``
