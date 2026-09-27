# Interaction — Pinch

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Pinch")
    @CallToAction(url: "SWAMI_DOWNLOAD_BASE/Interaction_Pinch.zip", purpose: download, label: "Download Xcode sample")
}

Pinch a shape to scale it. Past a threshold it pops to an enlarged size with a
spring; pinch back in and it pops home.

## Preview

![A white rounded triangle centered on a magenta background. Pinching out springs it to a larger size; pinching in springs it back.](Interaction_Pinch)

## The patch

Origami drives this with an `origami.PopSwitch` — a remembered on/off state — flipped by
a pinch and fed into a Transform Scale. There's no helper to reach for: it maps straight
onto native SwiftUI, which is the reusable idea worth taking away. A `MagnifyGesture`
reads the pinch, a `@State` flag flips at a threshold, and a `.spring` animates the
scale between the two states (see the State/memory → `@State` row in
<doc:OrigamiMappings>).

```swift
@State private var popped = false

RoundedTriangle(cornerRadius: 20)
    .frame(width: 90, height: 80)
    .scaleEffect(popped ? 2 : 1)
    .animation(.spring(response: 0.35, dampingFraction: 0.7), value: popped)
    .gesture(
        MagnifyGesture().onEnded { value in
            if value.magnification > 1.25 { popped = true }
            else if value.magnification < 0.8 { popped = false }
        }
    )
```

The pop is the point: a discrete state the gesture toggles, animated with a spring — not
a scale that tracks your fingers continuously.

## How it's built

The full view sits the white rounded triangle on the magenta artboard and adds a live
`@GestureState` so the shape follows your fingers mid-pinch before it settles on the
popped state. Read the source (below) for the whole thing.

## Behavior

- Pinch out on the shape to grow it; pinch in to shrink it.
- Cross the threshold and it snaps to the next size with a spring, rather than
  tracking your fingers continuously.
- The switch remembers its state, so a release between pinches holds the current size.

## Downloads

- **Xcode sample** — [`Interaction_Pinch.swiftpm`](SWAMI_DOWNLOAD_BASE/Interaction_Pinch.zip) — a runnable App Playground. Unzip, open in Xcode 15+, and press Run to launch this pattern as an app.
- **Swift source** — [`Interaction_Pinch.swift`](https://github.com/swamikit/swami/blob/development/app/Swami/Patterns/Interaction_Pinch.swift) — the single source file, to read how the pop maps to `@State` + a spring.
- **Origami source** — [`Interaction_Pinch.origami`](https://origami.design/public/origami_files/patterns/Interaction_Pinch.origami) — the original prototype (opens in Origami Studio).

## See Also

- <doc:OrigamiMappings>
