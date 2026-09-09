# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
}

`Interaction_DragView` translates the Interaction Drag pattern into a full-screen
SwiftUI composition. At the runner's 2× render scale, its 375×667-point canvas
matches Origami's 750×1334 image: a purple canvas, a 30-point inset interaction
area, and a centered 120×120-point white card.

## Interaction

Touching the card engages a zero-distance drag. While the card is moving,
``View/drag(enable:momentum:bounds:start:position:translation:velocity:reset:)``:

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
