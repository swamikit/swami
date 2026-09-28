# Interaction — Swipe

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Swipe")
    @CallToAction(url: "SWAMI_DOWNLOAD_BASE/Interaction_Swipe.zip", purpose: download, label: "Download Xcode sample")
}

Swipe sideways to page between photos. Let go mid-swipe and it keeps gliding, then
settles on the nearest page.

## Preview

![A photo centered on a black background; swiping horizontally pages to the next photo, carrying momentum after release.](Interaction_Swipe)

## The patch

The swipe is Origami's momentum-scrolling Drag stack — `builtin.momentumScrolling` plus
`origami.Velocity` and `origami.Slip` — which is exactly what the
``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)`` modifier
ports from `origami.Drag`. Attach it to the photo row with `momentum` on and lock
`bounds` to the horizontal axis (`height: 0`), so a swipe pages sideways only:

```swift
@State private var position: CGSize = .zero

photoRow
    .drag(
        momentum: true,
        bounds: (min: CGSize(width: -pageWidth, height: 0), max: .zero),
        position: $position
    )
```

That one modifier is the reusable piece: a throw-with-momentum drag constrained to one
axis is a swipe.

## How it's built

The full view lays the two photo layers side by side, offsets the row by the `.drag`
output, and pins the vertical bounds to zero so the paging stays horizontal. Read the
source (below) for the whole thing.

## Behavior

- Swipe left or right to page between photos.
- Release mid-swipe and the row keeps gliding, then eases onto the nearest page.
- Push past the last page and it rubber-bands back inside.

## Downloads

- **Xcode sample** — [`Interaction_Swipe.swiftpm`](SWAMI_DOWNLOAD_BASE/Interaction_Swipe.zip) — the runnable project (same as the button above).
- **Swift source** — [`Interaction_Swipe.swift`](https://github.com/swamikit/swami/blob/development/app/Swami/Patterns/Interaction_Swipe.swift) — the single source file to read.
- **Origami source** — [`Interaction_Swipe.origami`](https://origami.design/public/origami_files/patterns/Interaction_Swipe.origami)

## See Also

- ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)`` — the patch this pattern uses, ready for your own layers
- <doc:OrigamiMappings>
