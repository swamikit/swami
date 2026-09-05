# src/parser — `.origami` → IR

Deterministic code that reads a `.origami` document and produces a structured graph.

## Status: structural document graph working (`origami_graph.py`)

Proven against the public Interaction Touch and Drag patterns. It walks the document's
declared node, port, and connection vectors by strict FlatBuffers reflection. No schema,
no dependencies. Instance-level boolean, number, point, and four-component values are
decoded; unresolved catalog defaults stay explicit. See ADR 0004 and
`docs/format/origami-graph-format.md`.

```sh
python3 tool/src/parser/origami_graph.py Interaction_Drag.origami out.json
# -> 24 unique placed nodes, 19 identifier-resolved edges
```

API: `parse(path) -> dict`.

## Remaining work

- Canonical **port names** for builtin patches (some ports name-by-tag, not inline).
- **Group/component nesting** → hierarchical IR (currently flat harvest).
- **Wireless broadcaster/receiver** → collapse into direct edges by name.
- Decode typed catalog defaults when an instance has no override.
- Recover parent/child layer hierarchy for SwiftUI body emission.
- Validate against Origami's JSON export if that route is confirmed in-app.
- Formalize the output as the shared **IR** in `src/ir/`.
- Selection scoping (whole-file parse, selection-scoped output — ADR 0002).
