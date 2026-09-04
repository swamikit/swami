# examples — seed worked-examples

Worked-examples that steer the translation skill. Each pairs a real Origami source with
its SwiftUI translation and notes on what didn't map.

## Touch Origami Example (first seed)

- `Touch Origami Example.origami` — the source (Origami 208.0). ZIP →
  `…​.diamond/graph` → FlatBuffers (`ORGM`). Format analysis:
  `docs/format/origami-graph-format.md`.
- `TouchOrigamiExample.swift` — the translation. **Pattern-level reconstruction** from
  the recoverable patch inventory + labels; exact wiring pending the parser.
- `TouchOrigamiExample.notes.md` — recovered inventory, the mapping applied, hard cases,
  and what the parser must extract to make the translation faithful.

The prototype is an interactive iOS **modal card** (push up, drag/edge-swipe to dismiss,
velocity physics, bouncy pop). It exercises a wide slice of the mapping table, which is
exactly what a seed example is for.
