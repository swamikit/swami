# ADR-0018: Decode input-port default values (inline f64 in the port value-table)

- Status: Accepted (scalar arm). The value-type **union tag is decoded**, and a **type-gated
  scalar-number reader** is implemented (`Graph._port_scalar_default`) and oracle-validated. The
  first attempt was reverted because, without the union tag, it emitted a double for every slot
  and so mis-typed Point/Color ports; the tag now gates it, so only confident scalar-number
  defaults are emitted and every Point/Color/enum port is skipped rather than mis-read. Point,
  Color, and integer/enum arms remain **deferred** (color additionally needs an Inspector
  channel-order oracle — see Consequences).
- Date: 2026-09-23
- Follows: ADR-0017 (structural placed-graph detection). Delivers the scalar half of the
  constants side of the ADR-0009 `drag()` TODO (DragSettings Momentum Friction is now read
  from the graph).

## Context

The parser reads node types, names, and edges (ADR-0017) but not a node's **input-port
default values**. Without them, faithful patch constants (e.g. `origami.DragSettings`
Momentum / Rubber Band Friction) fall back to iOS-standard stand-ins, so a translated
`drag()` does not reproduce Origami's real physics. `AGENTS.md` lists this as the open
parser TODO. Naive vtable field-offset walking returned zeros or canvas coordinates because
the value is not where a flat scalar read expects it.

## Decision

A port's default value is stored **inline as an IEEE-754 f64 double** in the port's `f[4]`
value-table. The value-type **union is discriminated by that value-table's own vtable**:

- A node's ports are its child vectors; each port table carries the port `id`, `name`, and an
  `f[4]` value-table.
- **The union tag is vtable field 0 of the value-table.** When field 0 is present it holds a
  small-int type tag — observed `1`/`2` for point-like (2-component) values and `3` for Color
  (the packed-`u32` color case) — and the value is multi-component, so it is **not** a scalar
  number.
- **The scalar-number case is: field 0 ABSENT, and field 1 present as an inline finite double
  at table offset 4.** `Graph._port_scalar_default()` reads exactly that and returns the float;
  for every tagged (Point/Color) or otherwise-shaped table it returns `None`. Decoded scalars
  are attached to each node as `scalar_port_defaults: {port_name: float}` in the parser output
  (additive — node/edge decoding is unchanged). This is the type-gating whose absence caused
  the first attempt to be reverted: a Point/Color port can no longer be emitted as a bogus
  scalar, because its field-0 tag excludes it.

## Validation

On `Interaction_Drag` the reader reproduces Origami's documented defaults **from the graph**,
not iOS stand-ins: `origami.DragSettings` **Momentum Friction 8.0** and `builtin.layer.layer`
**Opacity 1.0** / **End 1.0**, with node/edge counts unchanged (24 / 19). Corpus sanity across
12 diverse private fixtures: 243 scalar defaults decoded, **0 out-of-range / garbage values**,
and every Point/Color port (3124 tagged across the sample) correctly skipped. Regression guard:
`TestScalarPortDefaults` in `test_generalize.py` (oracle assertions + a corpus-wide check that
no decoded value is NaN/∞ or of implausible magnitude). `Scale`/`Pivot` are stored as tagged
2-component values in this buffer (tag `2`), so they are intentionally **not** emitted as
scalars — skipping is the safe behavior.

## Consequences / deferred

- **Point / integer-enum arms.** Point-like (tag `1`/`2`) and integer/enum defaults are not
  decoded yet — the tag is identified, but the per-component layout (and the enum value map)
  are follow-up work. The scalar reader deliberately leaves them untouched.
- **Color is a packed `uint32` in a color-object table.** The card fill `#B0E0B27B` is stored
  as `0xB0E0B27B` (LE bytes `7B B2 E0 B0`) at field `f[4]` of a small color-object table — NOT
  inline in the port's value table (which carries only a type tag `3`), not four doubles, not a
  hex string, not a name reference. So color decode is three steps: (1) **link** the color port
  to its color-object table — the linkage is not a nearby FlatBuffers offset, so it is still
  open; (2) **read** the packed `u32` — solved; (3) **resolve channel order** (ARGB vs RGBA) —
  not determinable from the bytes (the ambiguity `BACKLOG.md` records), needs an Origami
  Inspector AX readout (macOS runner / Samuel's Mac). Steps 1 and 3 stay deferred; the
  extraction itself is understood.
- **Geometry is not a stored literal.** The card size (220×140) and artboard (888×1212)
  appear nowhere in the buffer as f32 or f64 — they are derived or device-preset, so layout
  geometry needs separate handling from scalar port defaults.
