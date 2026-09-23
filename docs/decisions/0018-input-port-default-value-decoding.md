# ADR-0018: Decode input-port default values (inline f64 in the port value-table)

- Status: Accepted (scalar core validated; Color/Point deferred pending an Inspector oracle)
- Date: 2026-09-23
- Follows: ADR-0017 (structural placed-graph detection). Retires the constants half of the
  ADR-0009 `drag()` TODO.

## Context

The parser reads node types, names, and edges (ADR-0017) but not a node's **input-port
default values**. Without them, faithful patch constants (e.g. `origami.DragSettings`
Momentum / Rubber Band Friction) fall back to iOS-standard stand-ins, so a translated
`drag()` does not reproduce Origami's real physics. `AGENTS.md` lists this as the open
parser TODO. Naive vtable field-offset walking returned zeros or canvas coordinates because
the value is not where a flat scalar read expects it.

## Decision

A port's default value is stored **inline as an IEEE-754 f64 double** in the port's `f[4]`
value-table:

- A node's ports are its `f[5]` (and `f[6]`) child vectors.
- Each port table is `f[1]` = ordinal id, `f[2]` = name, `f[4]` = value-table, `f[5]` =
  compiled doc metadata.
- The default lives in `f[4]` as an inline double. `_port_default()` reads the clean inline
  doubles from `f[4]`'s field slots (a uoffset misread as f64 is huge or denormal, filtered
  by magnitude) and attaches them to each node's `ports` in the parser output. Additive —
  edge decoding is unchanged.

## Validation

On `Interaction_Drag`, decoded values reproduce Origami's documented defaults exactly:
`builtin.layer.layer` Opacity **1.0**, Scale **1.0**, Pivot **0.5**; and
`origami.DragSettings` **Momentum Friction 8.0** is now read from the graph rather than an
iOS stand-in. Node/edge counts are unchanged (24 / 19). Regression guard:
`TestPortDefaults` in `test_generalize.py`.

## Consequences / deferred

- **Union tag.** The populated *slot* within `f[4]` encodes the value *type* (scalar number
  vs Point vs Color-RGBA). Only the scalar case is decoded; a slot→type map is needed for
  multi-component values.
- **Color is a packed `uint32`.** The card fill `#B0E0B27B` appears in the placed region as
  the bytes `7B B2 E0 B0` (little-endian `0xB0E0B27B`) — not four doubles, not a hex string,
  not a ColorKit name reference in the graph. So decoding a color to a hex is a `u32` read;
  the only open question is the **channel order** (ARGB vs RGBA), which is not determinable
  from the bytes alone (the ambiguity `BACKLOG.md` records). Locking the order in requires an
  Origami Inspector AX readout (the macOS runner / Samuel's Mac), so the order — not the
  extraction — is what stays deferred rather than guessed.
- **Geometry is not a stored literal.** The card size (220×140) and artboard (888×1212)
  appear nowhere in the buffer as f32 or f64 — they are derived or device-preset, so layout
  geometry needs separate handling from scalar port defaults.
