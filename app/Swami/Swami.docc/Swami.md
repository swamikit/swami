# ``Swami``

Origami patterns, rebuilt as SwiftUI you can read — each one a worked example of the
patches behind it, so you can see how a prototype's behavior is written and reach for
the same patch on your own layers.

## Overview

`Swami` is a set of patch helpers — one per Origami patch, named after the patch, so an
`origami.Drag` becomes a `.drag(…)` modifier and an Interaction becomes `.interaction(…)`
— plus a gallery of Origami prototypes translated to SwiftUI. The patches are the reusable
part; each entry in the gallery shows those patches composed into a working view. Where
SwiftUI already has the right tool the translation uses it directly; where it doesn't, a
patch helper fills the gap.

## Gallery

@Links(visualStyle: detailedGrid) {
    - <doc:Interaction_Drag>
    - <doc:Interaction_Pinch>
}

## Topics

### Patterns

- <doc:Interaction_Drag>
- <doc:Interaction_Pinch>

### Patches

- <doc:DragPatch>
- <doc:InteractionPatch>

### Shapes

- ``RoundedTriangle``

### Reference

- <doc:OrigamiMappings>
