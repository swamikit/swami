# `.origami` graph format — reverse-engineering notes

Reference for `src/parser`. Findings are from `examples/Touch Origami Example.origami`
(Origami Studio version **208.0 (837960526)**). Confirms ADR 0001; the decoded layout
below is implemented in `tool/src/parser/origami_graph.py` (ADR 0004).

## Container

```
Touch Origami Example.origami            ZIP archive (compression: store)
└── Touch Origami Example.diamond/       the document bundle ("diamond")
    └── graph                            the payload — FlatBuffers binary
```

- The `.origami` file is a plain ZIP (`unzip -l` works). One entry.
- The bundle directory carries the `.diamond` extension (Origami's internal document
  package name; the app stores data under `~/Library/Application Support/Diamond/`).

## Payload: FlatBuffers

First 16 bytes of `graph`:

```
30 00 00 00  4F 52 47 4D  00 00 00 00  24 00 30 00
└─uoffset─┘  └─ "ORGM" ─┘
```

- Bytes 0–3: little-endian uoffset to the root table (`0x30`).
- Bytes 4–7: FlatBuffers **file identifier `ORGM`** (ORiGaMi). Canonical FlatBuffers
  header, so the payload is FlatBuffers, not a custom format.
- The rest is standard FlatBuffers vtables/tables/vectors/strings.

No public `.fbs` schema or parser exists (web + GitHub search, 2026-09). So we either
reverse-engineer, or use Origami's own JSON export if present (see "Alternatives").

## Parsing method: strict reflection (no schema)

We walk the buffer by the wire format alone — root uoffset → tables (soffset → vtable)
→ strings (len-prefixed, null-terminated) and vectors (count-prefixed). Field *names*
aren't in the buffer (FlatBuffers uses vtable offsets), but structure + strings are.

**The one thing that makes blind reflection reliable here:** *strict* table validation.
Loose validation makes random byte runs validate as enormous fake tables (we saw vtables
claiming thousands of fields), and the walk explodes into garbage. Real Origami vtables
are small, so capping vtable size (`MAX_VSIZE = 200`, ≤ ~98 fields) and requiring
in-bounds table size rejects the false positives. With that cap the walk finishes in
~0.2 s and yields coherent structure.

## Decoded structure

Field indices are vtable slots (stable within this version).

**Document root and component container**:
- root `[4]` uoffset → current document component (do not confuse this with the
  embedded component/library vector in root `[14]`)
- document component `[4]` name, `[9]` child-node vector, `[10]` connection vector

**Placed node** (including `ios.Screen`):
- `[2]` type string (`ios.Screen`), `[4]` name
- `[5]` vector → the screen's own ports
- `[6]` vector → output ports
- `[8]`, `[13]` metadata tables

**Node table**:
- `[0]` u32 **node id**
- `[2]` **type** string (`builtin.transition`, `origami.Velocity`, …)
- `[4]` **name** string (designer-facing: "Screen Progress", "Option Picker")
- `[5]` vector<table> **input ports**
- `[6]` vector<table> **output ports**
- `[8]` metadata table — a key/value list including `position` (canvas coords) and
  `libraryInfo`

**Port table**:
- `[0]` u32 **port id**
- `[1]` ordinal
- `[2]` **name** string *when stored inline* (builtin patches often omit it and
  reference a canonical port by tag — `passthroughForPortTag`/`referencePortTag`)
- `[5]` default **value** table (e.g. a Transition's easing default "Exponential In")

**Connection table** (the wiring):
- `[0]` src node id, `[1]` src port id, `[2]` dst node id, `[3]` dst port id

The parser walks root `[4]` → component `[9]` for placed nodes and component `[10]`
for edges, then indexes each node's `[5]`/`[6]` port vectors. On the current public
Interaction Drag corpus this yields **24 unique placed nodes / 19 edges**, with every
edge's node and port identifiers resolved. This avoids the duplicate node/metadata
records produced by the old type-string owner scan.

## Still gated / TODO for the parser

- **Port names for builtin patches** (some are blank): needs a per-patch-type port
  catalog to name ports referenced by tag rather than inline string.
- **Group/component nesting** (`builtin.group.input`/`output`): currently harvested
  flat; the IR should represent the hierarchy.
- **Wireless broadcaster/receiver**: represented as ordinary nodes; not yet collapsed
  into direct name-resolved edges.
- **Nested component implementations**: placed composite nodes remain semantic units;
  their library implementation is intentionally not flattened into the placed graph.

## Alternatives / cross-check

Origami Studio **v221 (reported 2026-06)** is said to add an official
`.origami → JSON` CLI and "Copy-Paste As JSON" (unconfirmed — verify in-app; the
release page was not reachable from the build environment). If real, that JSON is an
authoritative oracle to validate this reflection parser against, and a cleaner,
version-stable ingestion path for newer files. The reflection parser remains the route
for 208.0-era files, offline use, and anything pre-221.

## Recovered patch inventory (this prototype)

Grouped by role. (String-occurrence counts; inflated by bundled library metadata.)

**Screen / device**: `ios.Screen`, `builtin.deviceInfo`.
**Layers**: `builtin.layer.layer/.text/.ellipse/.fill/.gradient/.sublayerPlaceholder/
.binding/.combinerBinding/.interaction`.
**Interaction**: `ios.EdgeSwipe(+Detection)`, `ios.StickyBoundaries`,
`ios.Smoothvalueondragrelease`, `ios.Reset`, `origami.LongPress`, `origami.DoubleTap`,
`origami.Velocity`.
**Animation / interpolation**: `builtin.transition`, `builtin.classicAnimation`,
`builtin.bouncy`, `builtin.smoothValue`, `builtin.progress`, `builtin.curve`,
`builtin.pulse(+OnStart)`, `builtin.delay(+1)`, `builtin.sample`.
**Logic**: `builtin.switch`, `builtin.logic.and/or/not`, `builtin.compare.lt/gt/eq`,
`builtin.counter`, `builtin.multiplexer`, `builtin.demultiplexer`.
**Math / geometry**: `builtin.math.add/sub/mul/div`, `builtin.range`, `builtin.point(3D)`,
`builtin.getPoint`.
**Structure**: `builtin.group.input/output`, `builtin.wirelessBroadcaster/Receiver`
(link by name), `builtin.splitter`, `builtin.comment`.
