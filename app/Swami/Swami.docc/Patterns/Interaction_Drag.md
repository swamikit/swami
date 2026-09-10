# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
}

Translate Origami's Drag interaction into a bounded SwiftUI gesture with the
same momentum, rubber-band, and reset stages.

## Composition

``Interaction_DragView`` fills the 375×667-point reference viewport with
Purple (`#DD70DF`) and hides application and status-bar chrome. The centered
120×120 white layer is the only visible shape and is the drag target; there is
no inset interaction-area rectangle. These dimensions and rendered colors are
pinned to the current runner's Origami reference rather than inferred from
simulator chrome or an unrelated library definition.

## Interaction

The view maps the placed graph in the same order:

1. `Drag` publishes Position, Translation, and Velocity while the touch moves.
2. Momentum integrates the release velocity with Momentum Friction **8**.
3. Rubber Band Friction **8** resists travel beyond the layer-edge bounds;
   Rubber Band Tension **100** settles the layer at a boundary.
4. At touch-up, the drag helper reports its final position to the separate
   `Interaction → Equals → Pulse` chain. That chain sends `Reset` when both axes
   are within 100 points of the origin. There is only one gesture recognizer, so
   the pulse cannot race a second local drag gesture.

Release velocity uses the final newer touch-up sample, including zero movement
when the finger stops before release. Duplicate or older timestamps preserve the
last valid sample; a new touch starts with zero velocity.

The parser reads the three Drag Settings values from typed Number payloads. It
accepts only Number fields `{1, 17}` and Color fields `{0, 4, 17}`, with matching
owner and payload tags. Color requires subtype 3 and four Float64 RGBA channels.
Populated fields must fit inside the table without overlapping each other or its
header. Regression tests cover the corpus values, relocated fields, unexpected
fields, invalid offsets, truncation, and nonfinite values.

## Evidence

The verification runner opens the current public `Interaction_Drag.origami`,
renders Origami and Swami at the same reference dimensions, and publishes the
Swami, Origami, and difference images with an H.264 drag recording. The
recording's touch indicator is evidence-only and is not part of
``Interaction_DragView``.

## See Also

- ``Interaction_DragView``
- ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:momentumFriction:rubberBandFriction:rubberBandTension:onRelease:)``
