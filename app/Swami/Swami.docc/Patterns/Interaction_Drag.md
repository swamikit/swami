# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
    @CallToAction(url: "https://origami.design/public/origami_files/patterns/Interaction_Drag.origami", purpose: download, label: "Open in Origami")
}

A card you can drag anywhere on screen. It carries momentum when you let go and
springs back from the edges.

## Preview

![A rounded card centered on the artboard that follows your finger, keeps gliding after release, and rubber-bands back inside the edges.](Interaction_Drag)

## The patch

The behavior is Origami's `origami.Drag`, ported as the
``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)`` modifier.
Attach it to any layer: `momentum` carries the throw after release, `bounds` is the
min/max extent it rubber-bands back inside, and `position` writes the live offset back
to your own `@State`.

```swift
@State private var position: CGSize = .zero

RoundedRectangle(cornerRadius: 20, style: .continuous)
    .frame(width: 220, height: 140)
    .drag(momentum: true, bounds: dragBounds, position: $position)
```

That one modifier is the reusable piece. The pattern is just it dropped onto a centered
card whose `bounds` come from the artboard.

## How it's built

The full view centers the card on the Origami artboard, derives `bounds` from the card
size, and hands the `origami.Drag` output straight to the card's offset — the view is
interesting only as a demonstration of the patch. Read the source (below) for the whole
thing.

## Behavior

- Drag the card in any direction with one finger.
- Release it and it keeps moving, then eases to a stop (momentum).
- Push it toward an edge and it rubber-bands back inside the artboard.

## Downloads

- **Swift sample** — [`Interaction_Drag.swift`](https://github.com/swamikit/swami/blob/development/app/Swami/Patterns/Interaction_Drag.swift) — the full source. Read it to see how the patch composes into a view; paste it to run it.
- **Origami source** — [`Interaction_Drag.origami`](https://origami.design/public/origami_files/patterns/Interaction_Drag.origami) — the original prototype (opens in Origami Studio).

## See Also

- ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)`` — the patch this pattern uses, ready for your own layers
- <doc:OrigamiMappings>
