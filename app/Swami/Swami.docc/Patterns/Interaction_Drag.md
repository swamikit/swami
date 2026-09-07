# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
}

Drags a layer in any direction with momentum and rubber-band bounds. The draggable
card responds to touch input via Origami's `origami.Drag` patch, which wires its
output `Position` to the layer's transform. When released near the center, the
card snaps back to its resting position.

## See Also

- ``Interaction_DragView``
- ``Drag``
