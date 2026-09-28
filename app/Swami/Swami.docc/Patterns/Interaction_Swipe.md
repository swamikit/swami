# Interaction — Swipe

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Swipe")
    @CallToAction(url: "SWAMI_DOWNLOAD_BASE/Interaction_Swipe.zip", purpose: download, label: "Download Xcode sample")
}

A card on a magenta artboard you can swipe sideways. Let go mid-swipe and it keeps
gliding, then springs back to center.

## Preview

![A lighter-pink card with two white swipe arrows, centered on a magenta background; swiping the card horizontally carries momentum after release.](Interaction_Swipe)

## The patch

The swipe is Origami's momentum-scrolling Drag stack — `builtin.momentumScrolling` plus
`origami.Velocity` and `origami.Slip` — which is exactly what the
``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)`` modifier
ports from `origami.Drag`. Attach it to the card with `momentum` on and lock `bounds` to
the horizontal axis (`height: 0`), so a swipe stays sideways only:

```swift
@State private var position: CGSize = .zero

card
    .drag(
        momentum: true,
        bounds: (min: CGSize(width: -cardWidth, height: 0), max: .zero),
        position: $position
    )
```

That one modifier is the reusable piece: a throw-with-momentum drag constrained to one
axis is a swipe.

## How it's built

The full view centers a rounded card on a magenta fill, lays two white swipe arrows across
it, and hands the card to `.drag` with the vertical bounds pinned to zero so the motion
stays horizontal. Read the source (below) for the whole thing.

## Behavior

- Swipe the card left or right.
- Release mid-swipe and it keeps gliding, then eases back.
- Push past the edge and it rubber-bands back to center.

## Downloads

- **Xcode sample** — [`Interaction_Swipe.swiftpm`](SWAMI_DOWNLOAD_BASE/Interaction_Swipe.zip) — the runnable project (same as the button above).
- **Swift source** — [`Interaction_Swipe.swift`](https://github.com/swamikit/swami/blob/development/app/Swami/Patterns/Interaction_Swipe.swift) — the single source file to read.
- **Origami source** — [`Interaction_Swipe.origami`](https://origami.design/public/origami_files/patterns/Interaction_Swipe.origami)

## See Also

- ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)`` — the patch this pattern uses, ready for your own layers
- <doc:OrigamiMappings>
