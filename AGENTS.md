# AGENTS.md — Codex context for swami

Codex agents: this is your project memory. Deeper technical facts (`.origami` binary
format, ColorKit values, verified oracle numbers) live in `CLAUDE.md` at the same
level — read that first when parser/codegen questions get specific.

## What this project is

Deterministic **parser** (`.origami` → semantic IR) plus **codegen** (IR → SwiftUI).
Parser for facts; codegen for the mapping. The mapping targets SwiftUI's *state graph*
(computed properties, `@State`, `withAnimation`) rather than imperative functions —
Origami's patch graph is reactive dataflow, so is SwiftUI, keep them aligned.

## Layout

```
tool/                Python parser + codegen + Swift harness package
├── src/parser/      the schema-less FlatBuffers walker (stdlib only)
├── src/codegen/     IR → SwiftUI writer (stdlib only)
├── harness/         Swift Package (build target — Apple platforms only)
└── examples/        working seed translations (Touch is the oracle)
app/                 Swami.xcodeproj — framework + SwamiHost verify host
docs/decisions/      ADRs — read these when in doubt about a design call
skill/               verified-delivery skill notes
```

Meta assets (patterns/, catalog snapshots, .origami downloads) are `.gitignore`d and
live in a separate private repo. Do not add any `.origami` file to this repo.

## What you (Codex, Linux) CAN do

- Iterate on `tool/src/parser/*.py` and `tool/src/codegen/*.py` — pure Python stdlib,
  no build step, run directly with `python3`.
- Run the tree-sitter-swift syntax **pre-gate** on generated Swift (`scripts/codex-setup.sh`
  installs the grammar). This catches syntax errors — not type errors.
- Read the harness Swift for reference (`tool/harness/Sources/`) but do NOT try to
  build it here — most of it depends on SwiftUI, which is Apple-only.
- Draft ADRs, update `NEEDS-VERIFY.md`, refine the IR schema, propose codegen changes.
- Open PRs; the Mac-side runner will do the pixel gate on merge candidates.

## What you CAN'T do here

- **Build the Xcode project** (`app/Swami.xcodeproj`) — macOS only.
- **Run the iOS simulator, screenshot, pixel-verify** — that's the macOS runner's job
  (driven by a Cowork/local agent via XcodeBuildMCP).
- **Read the installed Origami Studio app's Patches folder** — that's on Samuel's Mac.
  Use the origami.design docs mirror (private repo) as the fallback reference.

## What "done" means

A compile is necessary, never sufficient. A patch translation is only *done* when the
running host app in the simulator matches the Origami artboard visually AND Samuel has
spot-checked. Your job here is to make the code correct enough to reach that gate; the
gate itself is Mac-side. See `NEEDS-VERIFY.md` for what's queued and what's earned.

## Conventions

- Parser stays deterministic and dependency-light (stdlib only, per ADR-0004).
- IR is **semantic-rich** — preserve names (colors, type styles, patch labels), not
  just values (ADR-0007).
- Record non-trivial decisions as ADRs in `docs/decisions/`.
- One-purpose commits; PR title describes the change, body explains the why.
