# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
}

Translate Origami's Drag interaction into a bounded SwiftUI gesture with the
same momentum, rubber-band, and reset stages.

## Composition

``Interaction_DragView`` fills the 375×667-point reference viewport with
Purple (`#DD70DF`) and hides application and status-bar chrome. A pale
`#E5A6E6` rounded screen is inset by 30 points. Its centered 120×120 white
layer is the drag target. These dimensions and rendered colors are pinned to the current runner's
Origami reference rather than inferred from simulator chrome or an unrelated
library definition.

## Interaction

The view maps the placed graph in the same order:

1. `Drag` publishes Position, Translation, and Velocity while the touch moves.
2. Momentum integrates the release velocity with Momentum Friction **8**.
3. Rubber Band Friction **8** resists travel beyond the layer-edge bounds;
   Rubber Band Tension **100** settles the layer at a boundary.
4. The separate `Interaction → Equals → Pulse` chain sends `Reset` when touch
   ends within 100 points of the origin on both axes. Each qualifying release
   creates a new pulse edge, including consecutive releases.

The parser reads the three Drag Settings values from typed Number payloads. Its
Color decoder additionally requires the FlatBuffers union discriminator and
payload fields, with regression coverage rejecting unrelated tables and an
invalid discriminator.

## Evidence

The verification runner opens the current public `Interaction_Drag.origami`,
renders Origami and Swami at the same reference dimensions, and publishes the
Swami, Origami, and difference images with an H.264 drag recording. The
recording's touch indicator is evidence-only and is not part of
``Interaction_DragView``.

## See Also

- ``Interaction_DragView``
- ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:momentumFriction:rubberBandFriction:rubberBandTension:)``
