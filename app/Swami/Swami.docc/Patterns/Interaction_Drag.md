# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
}

`Interaction_DragView` translates the Interaction Drag pattern into a full-screen
SwiftUI composition. The current-head Origami reference contains two visible layers:
a `#DD70DF` canvas at 375×667 points and a centered 120×120-point white card with a
15-point corner radius. The interaction region used to calculate drag limits is not a
visible panel. The current-head PR screenshot triplet verifies the rendered result
rather than this page assuming a match.

## Interaction

Touching the 120×120-point card engages a zero-distance drag. The placed graph's
315×607-point logical region exists only as geometry used to derive the movement
bounds; it creates no layout frame, hit-area panel, shape, or pixels. While the card
is moving, the `drag` modifier:

- publishes position, translation, and velocity;
- preserves the placed graph's calculated limits (`±97.5` horizontally and `±243.5`
  vertically) as state derived from its 315×607-point logical region;
- applies the Drag patch's documented 0.15 rubber-band friction beyond those limits;
- computes release velocity from the gesture's explicit touch-up sample, projects
  momentum, and settles within those boundaries;
- begins every fresh gesture from Drag's configured Start input rather than inheriting
  a previous momentum endpoint; and
- accepts every placed-graph reset pulse through the monotonic `resetCount` adapter.

The pattern composes the reset decision outside the helper, matching the placed
`Snap to origin` branch: two approximately-equal comparisons feed an And when
interaction turns off. The helper's release callback reports the touch-up position
without installing a competing gesture. A touch-up within 100 points of center on
both axes increments `resetCount`; each increment clears position, translation, and
velocity and returns the card to its origin.

## Verification media

The pull-request delivery generated from the same commit supplies the native
Swami, Origami, and difference screenshots plus the H.264 Maestro recording. The
recording demonstrates press, drag, bounded momentum, rubber-band settling, release,
and a fresh gesture/reset cycle. A small runner-host indicator follows the injected
touch from touch-down through its trajectory and disappears on release; that evidence
modifier is not part of `Interaction_DragView`. The page image is populated by the
documentation publication pipeline from the verified Swami render; it is not a
hand-authored substitute.

## See Also

- ``Interaction_DragView``
- ``Drag``
