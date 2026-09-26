# Interaction — Pinch

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Pinch")
}

Pinch a shape to scale it. Past a threshold it pops to an enlarged size with a
spring; pinch back in and it pops home.

## Preview

![A white rounded triangle centered on a magenta background. Pinching out springs it to a larger size; pinching in springs it back.](Interaction_Pinch)

## Usage

Drop the view into any SwiftUI hierarchy:

```swift
import Swami

struct ContentView: View {
    var body: some View {
        Interaction_PinchView()
    }
}
```

## Behavior

- Pinch out on the shape to grow it; pinch in to shrink it.
- Cross the threshold and it snaps to the next size with a spring, rather than
  tracking your fingers continuously.
- The switch remembers its state, so a release between pinches holds the current size.

## Downloads

- **Swift sample** — the source for `Interaction_PinchView`, ready to paste into a project.
- **Origami source** — `Interaction_Pinch.origami`, the pattern this view was translated from.

@Comment {
    TODO(downloads): wire these to a `@CallToAction(url:, purpose: download, label:)`
    in the @Metadata block above once the artifacts have a stable home. The Swift
    sample is bundled by post-merge.yml as `dist/Interaction_Pinch.zip` (currently
    an ephemeral workflow artifact, no public URL). The `.origami` is deliberately
    not committed to this repo (private corpus) — a home is proposed in the PR that
    introduced this page. Until then this section names what will be downloadable
    without shipping a broken button.
}

## See Also

- ``Interaction_PinchView``
- <doc:OrigamiMappings>

## Translation notes

This view was translated from Origami by Swami. The pinch drives an
`origami.PopSwitch` (a remembered on/off state) that feeds a Transform Scale;
Swami maps that to a `MagnifyGesture`, a `@State` flag flipped on a threshold, and
a `.spring` animation. Where a value could not yet be read from the `.origami`
graph (the enlarged scale, the shape's exact size and fill), the source file marks
it with an inline `TODO`. Those parser and fidelity details live in the comments of
`Interaction_Pinch.swift`, not on this page.
