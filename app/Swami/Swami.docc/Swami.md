# ``Swami``

An Origami → SwiftUI translator: a deterministic parser reads Facebook's `.origami`
patch graph into a semantic IR, and a codegen writes that IR out as SwiftUI. Swami
is also the patch-matched helper library that fills gaps between Origami patches
and native SwiftUI — one helper per Origami patch, named after the patch, sized by
Origami's patch surface. Every pattern that lands is a deliverable, verified against
Origami's own render, and shipped as a DocC-embedded example.

## Overview

Origami's patch graph and SwiftUI are both reactive dataflow. Swami targets SwiftUI's
state graph (computed properties, `@State`, `withAnimation`) rather than imperative
functions, so the two graphs stay aligned. Where a native SwiftUI construct maps
cleanly, Swami uses it. Where Origami's semantics need a helper — for example the
Interaction patch's four discrete output ports, or Drag's momentum + rubber-band
physics — Swami ships a helper named after the Origami patch and shaped like it.

## Topics

### Reference

- <doc:OrigamiMappings>
- <doc:Beats>

### Helpers

- ``Interaction``
- ``Drag``

### Examples

- ``TouchOrigamiExampleView``
