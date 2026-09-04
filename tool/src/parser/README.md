# src/parser — `.origami` → IR

Deterministic code that reads a `.origami` document and produces a structured graph.

## Status: first cut working (`origami_graph.py`)

Proven against `examples/Touch Origami Example.origami` (Origami 208.0). Recovers
nodes, types, names, ports, port defaults, canvas positions, and the port-to-port
**wiring** — by strict FlatBuffers reflection, **no schema, no dependencies**. See ADR
0004 and `docs/format/origami-graph-format.md`.

```sh
python3 src/parser/origami_graph.py "examples/Touch Origami Example.origami" out.json
# -> "356 nodes, 395 edges (395 fully name-resolved), version 208.0 (837960526)"
```

API: `parse(path) -> Graph` (dataclasses: `Graph`, `Node`, `Port`, `Edge`);
`to_dict(graph)` for JSON.

## Remaining work

- Canonical **port names** for builtin patches (some ports name-by-tag, not inline).
- **Group/component nesting** → hierarchical IR (currently flat harvest).
- **Wireless broadcaster/receiver** → collapse into direct edges by name.
- Filter comment/annotation/library artifacts from the node count; validate against
  Origami's own view (v221 JSON export, if confirmed).
- Formalize the output as the shared **IR** in `src/ir/`.
- Selection scoping (whole-file parse, selection-scoped output — ADR 0002).
