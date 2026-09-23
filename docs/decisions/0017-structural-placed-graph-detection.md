# ADR-0017: Find the placed graph structurally (artboard-anchored), not by byte offset

- Status: Accepted (validated head-to-head across the corpus; see Consequences)
- Date: 2026-09-23
- Supersedes: the `placed_root_offset()` approach (root field-14 `entries[0]` boundary
  + string scan) that this parser used previously.

## Context

A `.origami` document embeds Origami's whole component **library** plus the small
**placed** graph (the artboard and its patches). Separating them is the core parsing
challenge (AGENTS.md). Iteration 1 used a hardcoded byte offset (`tail=360000`) tuned to
the Touch example — it happened to work only because that document's placed nodes are
serialized last. On a larger file that embeds a composite patch (e.g. `Interaction_Drag`,
534 KB) the embedded component's internals also land in the tail and pollute the result.

Iteration 2a tried to find the placed graph by taking the **highest-offset entry of the
root's field-14 vector** as a boundary (`placed_root_offset()`), then string-scanning
above it. Measured against the private fixture corpus this was unreliable: it isolated
`Interaction_Drag` acceptably (46 nodes) but ballooned on other patterns —
`Animation_Delay` 148, `Logic_Counter` 205, `Scroll_Vertical_Page` 151 — each reporting
**three** `*.Screen` nodes (library bleed), and it decoded no edges.

Attempts that don't work:
- **Byte offset** — file-specific; breaks the moment layout changes.
- **Offset-reachability from the library root (field 14)** — components reference their
  internal nodes by **id**, not by nested FlatBuffers offsets, so an offset-following walk
  from the library root does not enumerate a component's node tables. Library-exclusion by
  reachability therefore fails to exclude big library components.

## Decision

Detect the placed graph by **structure + semantics**, no byte offset:

1. **Node-vectors.** Scan for FlatBuffers vectors whose elements are (strictly validated)
   tables that own a patch-type string (`builtin.*`/`origami.*`/`ios.*`). Every component —
   library or placed — has exactly one.
2. **Artboard anchor.** The placed document is the node-vector that contains the artboard
   (a `*.Screen` node). Library patch-definitions never contain a screen. This is the
   load-bearing discriminator.
3. **Edges.** Find the sibling connection-vector by content — elements shaped
   `[srcNodeId, srcPortId, dstNodeId, dstPortId]` whose node ids resolve into the placed
   node set — and decode name-resolved edges.
4. **Strict table validation** (vtable-size cap, `MAX_VTABLE`/`MAX_TABLE`) throughout:
   without it, random bytes read as giant fake tables and the walk explodes. This is the
   single most important lever for a schema-less walk.

## Consequences

- Validated on Touch: **51 placed nodes / 41 edges**, and the edges reproduce the documented
  mechanism (Interaction.Down → Sample and Hold → Position/Scale → Oval). The parser now
  emits edges, not just nodes.
- **Correct by construction for embedded composites**, confirmed on `Interaction_Drag`:
  **24 placed nodes / 19 edges / 1 artboard**, with `origami.Drag` = a single node and
  `origami.DragSettings` = a single node — Drag's internals (Add Momentum, Rubber Band
  Friction/Tension, Stick To Boundaries, …) are a library definition without an artboard,
  so they are never selected. Across the corpus the artboard-bearing patterns collapse from
  the old 148–205 nodes / 3 phantom screens to ~17–24 nodes / 1 screen.
- **No-artboard soft spot:** the artboard test keys on a `*.Screen` type; a document with no
  detected screen (observed on `Loops_Sum`, `Layers_List`) falls back to the largest
  non-library node-vector, which can grab a big library component. Hardening this fallback
  (and understanding why some patterns don't surface a `*.Screen`) is tracked in BACKLOG.
- **Multi-artboard documents** may expose more than one `*.Screen` node-vector — open
  question whether to merge or scope per artboard.
- Input-port **default-value** decoding (the typed value-union) is still unsolved and still
  blocks faithful patch constants (e.g. DragSettings momentum/friction).
