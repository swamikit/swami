# swami

Translate [Origami Studio](https://origami.design) prototypes into idiomatic **SwiftUI**.

## Pipeline

```
.origami (FlatBuffers, "ORGM")  ──▶  [parser]  ──▶  semantic IR  ──▶  [codegen]  ──▶  SwiftUI
                                     (deterministic)              (mapping rules)
```

- **parser** (`src/parser`) — decode the `.origami` graph, separating the *placed*
  patches/layers from the embedded component *library* (the hard part). Deterministic.
- **IR** (`src/ir`) — a **semantic-rich** dataflow graph: nodes, edges, and semantics
  (named colors, type styles, component identity) — not just resolved values. See ADR-0007.
- **codegen** (`src/codegen`) — lowers the IR onto SwiftUI's reactive state graph.

## Verification

Fidelity is **visual** (ADR-0004): render the SwiftUI and diff it against the Origami
render. The graph is the source of truth for values; reading them from Origami's Inspector
is an *oracle*, not the method. The test corpus is Origami's built-in **Patterns gallery**
(ADR-0005). The verify gate lives in `.github/workflows/verify.yml` + `app/SwamiHost`
(ADR-0013 Path B): on a `macos-15` runner, install Origami from its Sparkle appcast, boot
an iPhone 16 sim, build+install `SwamiHost`, then `xcrun simctl io … screenshot` the
sim while an AppleScript-driven Origami window screenshots the artboard — same pattern
on each side — and SSIM-diff the pair with ImageMagick's `compare`.

## Status

First worked example verified: `examples/TouchOrigamiExample.*` (see the ground-truth
values in `CLAUDE.md`). Parser edge/color extraction is the active work. Decisions in
`docs/decisions/`.
