# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
}

Translate Origami's Drag interaction into a bounded SwiftUI gesture with the
same momentum, rubber-band, and reset stages.

## Composition

``Interaction_DragView`` presents the source artboard without application or
status-bar chrome. A 220×140 Purple (`#DD70DF`) card with a 20-point continuous
corner radius rests at the center of the white 888×1212 artboard.

The values are source facts, not screenshot sampling. Swami's schema-less
FlatBuffers reader decodes Origami colors as Float64 **RGBA** and recovers Drag
Settings' typed input-port defaults. Purple's decoded channels—221, 112, 223,
255—also provide the channel-order oracle.

## Interaction

The view maps the placed graph in the same order:

1. `Drag` publishes Position, Translation, and Velocity while the touch moves.
2. Momentum integrates the release velocity with Momentum Friction **8**.
3. Rubber Band Friction **8** resists travel beyond the calculated card-edge
   bounds; Rubber Band Tension **100** settles the card at a boundary.
4. The separate `Interaction → Equals → Pulse` chain sends `Reset` when touch
   ends within 100 points of the center on both axes.

The bounds are derived from source geometry: `±(888/2 − 220/2) = ±334`
horizontally and `±(1212/2 − 140/2) = ±536` vertically.

## Evidence

The verification runner opens the current public `Interaction_Drag.origami`,
renders Origami and Swami at the reference dimensions, and publishes the Swami,
Origami, and difference images with an H.264 recording. The recording's touch
indicator is evidence-only and is not part of ``Interaction_DragView``.

## See Also

- ``Interaction_DragView``
- ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:momentumFriction:rubberBandFriction:rubberBandTension:)``
