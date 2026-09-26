# Interaction — Drag

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Drag")
}

A card you can drag anywhere on screen. It carries momentum when you let go and
springs back from the edges.

## Preview

![A rounded card centered on the artboard that follows your finger, keeps gliding after release, and rubber-bands back inside the edges.](Interaction_Drag)

## Usage

Drop the view into any SwiftUI hierarchy:

```swift
import Swami

struct ContentView: View {
    var body: some View {
        Interaction_DragView()
    }
}
```

The drag physics come from the ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)``
modifier, so you can reuse the same behavior on your own layers:

```swift
RoundedRectangle(cornerRadius: 20)
    .drag(momentum: true, bounds: bounds, position: $position)
```

## Behavior

- Drag the card in any direction with one finger.
- Release it and it keeps moving, then eases to a stop (momentum).
- Push it toward an edge and it rubber-bands back inside the artboard.

## Downloads

- **Swift sample** — the source for `Interaction_DragView`, ready to paste into a project.
- **Origami source** — `Interaction_Drag.origami`, the pattern this view was translated from.

@Comment {
    TODO(downloads): wire these to a `@CallToAction(url:, purpose: download, label:)`
    in the @Metadata block above once the artifacts have a stable home. The Swift
    sample is bundled by post-merge.yml as `dist/Interaction_Drag.zip` (currently
    an ephemeral workflow artifact, no public URL). The `.origami` is deliberately
    not committed to this repo (private corpus) — a home is proposed in the PR that
    introduced this page. Until then this section names what will be downloadable
    without shipping a broken button.
}

## See Also

- ``Interaction_DragView``
- ``View/drag(enable:momentum:bounds:position:translation:velocity:reset:)`` — the ``View`` extension that ports `origami.Drag`'s momentum and rubber-band ports
- <doc:OrigamiMappings>

## Translation notes

This view was translated from Origami by Swami. Where a value could not yet be
read from the `.origami` graph (the card and artboard colors, exact bounds), the
source file marks it with an inline `TODO` next to the placeholder. Those parser
and fidelity details live in the comments of `Interaction_Drag.swift`, not on this
page.
