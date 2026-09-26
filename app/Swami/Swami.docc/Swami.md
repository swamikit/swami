# ``Swami``

A gallery of Origami patterns rebuilt in SwiftUI — each one a small, self-contained
view you can drop into a project and use.

## Overview

Every entry in the gallery started life as an Origami prototype and was translated
into an idiomatic SwiftUI view. Browse the previews, copy the usage snippet, and
reach for the matching helper when you want the same behavior on your own layers.

`Swami` is also the library those views are built on: one helper per Origami patch,
named after the patch, so a Drag stays a ``Drag`` and an Interaction stays an
``Interaction``. Where SwiftUI already has the right tool, the translation uses it
directly; where it doesn't, the helper fills the gap.

## Gallery

@Links(visualStyle: detailedGrid) {
    - <doc:Interaction_Drag>
    - <doc:Interaction_Pinch>
}

The Touch demo — tap, press, double-tap, and long-press on a card — lives as the
``TouchOrigamiExampleView`` example.

## Topics

### Patterns

- <doc:Interaction_Drag>
- <doc:Interaction_Pinch>
- ``TouchOrigamiExampleView``

### Reference

- <doc:OrigamiMappings>
- <doc:Beats>

### Helpers

- ``Interaction``
- ``Drag``

### Examples

- ``Interaction_DragView``
- ``Interaction_PinchView``
