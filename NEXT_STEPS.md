# Next steps

Ordered. First two steps are **done** (format cracked + first seed translation); the
work now shifts to building the real parser so translations are read, not inferred.

## ✅ 0. Seed source in the repo

`examples/Touch Origami Example.origami` is committed.

## ✅ 1. `.origami` format confirmed

`.origami` = ZIP → `<name>.diamond/graph` = FlatBuffers (identifier `ORGM`, Origami
208.0). Node types, layer/port names, and values are readable without a schema; the
**wiring is not**. Full findings: `docs/format/origami-graph-format.md`, ADR 0001.

## ✅ 2. First translation test (seed worked-example)

`examples/TouchOrigamiExample.swift` + `.notes.md` — a pattern-level reconstruction of
the interactive modal. Surfaced the real hard cases (continuous velocity spring,
edge-swipe gating, wireless links, groups). This validated the mapping table against a
real file.

## ✅ 3. FlatBuffers parser (`tool/src/parser/`), structural graph working

`tool/src/parser/origami_graph.py` follows root field 4 into the current document and
reads its declared child-node, port, and connection vectors by strict reflection (no
schema, no dependencies). The public Drag pattern yields 24 unique placed nodes and 19
identifier-resolved edges; boolean, number, point, and four-component instance values
are decoded without flattening the embedded component library.

Remaining refinements (not blockers):
- Canonical **port names** for builtin patches (some ports name-by-tag).
- **Group/component nesting** → hierarchical, not flat.
- Collapse **wireless** broadcaster/receiver into direct edges by name.
- Decode catalog defaults for inputs without an instance override.
- Recover parent/child layer membership for SwiftUI body emission.
- **Validate** against Origami's v221 `.origami → JSON` export if that's confirmed
  in-app (would be the ground-truth oracle).

## 4. Define the IR (`src/ir/`)

Nail down node/edge/layer/binding types from what the parser produces and what the
translation needs. Keep it minimal.

## 5. Draft the translation skill (`skill/`)

Codify the `CLAUDE.md` mapping table + hard-cases as a skill reading IR → SwiftUI. Use
the Touch Origami Example as its primary worked-example; regenerate the seed from the
parsed graph and diff against the hand-inferred one to measure fidelity.

## 6. Selection capture (open problem — ADR 0003)

Start by letting the user pick a subtree from the parsed IR tree; add an Accessibility
menu-bar companion later.
