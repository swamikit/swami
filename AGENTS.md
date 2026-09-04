# AGENTS.md — project memory for swami

The single agent-facing memory file for this repo. `AGENTS.md` is the
agent-agnostic standard (Cursor, Codex, Claude Code all read it). Load before
working here. Durable project context, not a task list.

`CLAUDE.md` at the root is a pointer to this file.

---

## Domain — what this project is

An Origami→SwiftUI translator: a deterministic **parser** (`.origami` → semantic
IR) plus a **codegen** (IR → SwiftUI). Parser for facts, codegen for the mapping.
Read `docs/decisions/`.

Origami's patch graph and SwiftUI are both reactive dataflow. The mapping targets
SwiftUI's **state graph** (computed properties, `@State`, `withAnimation`), not
imperative functions.

### Deliverables (what's shipped at the end)

Earlier drafts listed seven; there are really four. Overlap collapsed for real:

1. **The Swift package (`Swami`)** — the patch-matched helper library (native-first,
   sized by Origami's patch surface per ADR-0009), the DocC in `Swami.docc/` (which is
   how the mapping reference reaches a human reader — there is no separate mapping
   doc), and a gallery/showcase surface for the translated corpus.
2. **The tool (`tool/`)** — parser + codegen. The "skill / MCP" packaging is the same
   code with an agent-facing entry point, not a separate artifact.
3. **The verified corpus** — every Origami Pattern translated + auto-compare-verified,
   living as DocC-embedded examples inside the Swift package (start there — keeps
   docs and examples in sync; split to a sibling repo only if it grows heavy).
4. **The methodology** — ADRs, verified-delivery, the beats. Not a shipped artifact;
   it's how 1–3 stay honest.

The harness (macOS-runner verify gate) sits under all four as the fidelity oracle —
means, not a deliverable.

### Format facts (`.origami`)

- `.origami` is a **zip**; the graph doc is `<name>.diamond/graph`, **FlatBuffers**,
  file_identifier **`ORGM`**, root table at offset 0x30. No `.fbs` schema ships
  (it's compiled in) → schema-less walk.
- The file embeds Origami's whole component **library**; the *placed* graph is a
  small subset. **Separating placed patches from library definitions is THE core
  parsing challenge.** Root field 14 (EdgeSwipe, Velocity, StickyBoundaries, …) is
  the LIBRARY, not the placed graph — do not mistake it for the document (a prior
  session did, and generated the wrong app).
- Placed nodes cluster in the file **tail region (~373k–401k)** for the Touch
  example. ~25 placed nodes / ~44 edges is the real graph (vs 356/395
  library-inclusive).
- Design tokens follow Origami's ColorKit/TypeKit model: a color is
  `{name, hex, alpha}` plus `colorUsages` (semantic roles); type styles likewise.
  Preserve these names in the IR (ADR-0007).
- **Patch docs are compiled into the app** (2026-09-03). Structural metadata is
  FlatBuffers fields: `category`, `enumOptions`, `libraryInfo`,
  `availableInComponentsOnly`, and a per-patch `useNewDocumentation` bool (newer
  patches defer to origami.design docs; older carry inline prose). Human-readable
  descriptions ship as compiled strings (e.g. Velocity: "Measure the speed that a
  value is changing… ex: Drag, Scroll").
- **Complete catalog = the app itself, not the web.**
  `Origami Studio.app/Contents/Resources/Patches/*.origami-system/` holds
  **66 composite/system patches** as readable `.diamond/graph` FlatBuffers (our
  format): **origami core 24, iOS 16, Android 24 (material.*), Desktop 1**, each
  with `info.json`, icons, and `.m4a` SoundKit assets. Primitive patches
  (Interaction, Transition, Add, Switch, Pop Animation…) live in the binary, not
  as `.diamond` files. Web docs = secondary human cross-check only.
- **Composite graphs give faithful physics.** `origami.Drag` contains the full
  momentum impl as named nodes: Add Momentum, Rubber Band Friction, Rubber Band
  Tension, Stick To Boundaries, "Reset remaining velocity on touch up", Round to
  Screen Pixels, Clip/Set Position + Momentum. Port these 1:1 instead of
  approximating (retires the `drag()` TODOs from ADR-0009). Same for
  origami.Velocity, DoubleTap, LongPress, LegacyScroll, PopSwitch, ProgressRing,
  Shimmer, HitArea, GridLayout.

### The mapping model

| Origami | SwiftUI |
|---|---|
| Pure value patch (Add, Transition/interpolate, logic) | computed property / expression |
| Interaction (Tap, Down/press, Double Tap, Long Press) | gesture + `@State`/`@GestureState` |
| State/memory (Switch, Sample and Hold) | `@State` + update logic |
| Animation (Classic Animation, Pop/Spring) | `withAnimation` / `.animation(.spring)` |
| Layer tree | the `View` body |

Origami `Transition` = interpolation (not SwiftUI's `.transition()` modifier).
Flag, don't fake: continuous-time springs, custom JS patches, absolute layout.

### Verified oracle — Touch Origami Example

The document is the tap/down/double-tap/long-press demo. Values read from the
Inspector (parser must reproduce):

- Frame (card): cornerRadius **20** all corners, Size **Grow**, stroke width 0;
  Tap-frame background **white**.
- Oval: **100×100**, fill Origami Core **"Purple" = `#DD70DF`** (RGB 221,112,223),
  Transform Scale **0 at rest → 5** on Down (Classic Animation, quadratic, 0.5s).
- Group: vertical, spacing **30**. Artboard background = the same Purple.
- Mechanism: pressing grows the hidden 100×100 Oval inside the card — NOT scaling
  the card.

---

## Process — how work moves

### Layout

```
tool/                Python parser + codegen + Swift harness package
├── src/parser/      the schema-less FlatBuffers walker (stdlib only)
├── src/codegen/     IR → SwiftUI writer (stdlib only)
├── harness/         Swift Package (build target — Apple platforms only)
└── examples/        working seed translations (Touch is the oracle)
app/                 Swami.xcodeproj — framework + SwamiHost verify host
docs/decisions/      ADRs — read these when in doubt about a design call
skill/               verified-delivery notes + adopted skills (unslop, …)
```

Meta assets (patterns/, catalog snapshots, .origami downloads) are `.gitignore`d
and live in a separate private repo. Do not add any `.origami` file to this repo.

### What Codex (Linux) CAN do

- Iterate on `tool/src/parser/*.py` and `tool/src/codegen/*.py` — pure Python
  stdlib, no build step, run directly with `python3`.
- Run the tree-sitter-swift syntax **pre-gate** on generated Swift
  (`scripts/codex-setup.sh` installs the grammar). Catches syntax errors —
  not type errors.
- Read the harness Swift for reference (`tool/harness/Sources/`) but do NOT try
  to build it here — most of it depends on SwiftUI, which is Apple-only.
- Draft ADRs, update `NEEDS-VERIFY.md`, refine the IR schema, propose codegen
  changes.
- Open PRs; the Mac-side runner will do the pixel gate on merge candidates.

### What Codex CAN'T do here

- **Build the Xcode project** (`app/Swami.xcodeproj`) — macOS only.
- **Run the iOS simulator, screenshot, pixel-verify** — that's the macOS runner's
  job (driven by a Cowork/local agent via XcodeBuildMCP).
- **Read the installed Origami Studio app's Patches folder** — that's on Samuel's
  Mac. Use the origami.design docs mirror (private repo) as the fallback
  reference.

### What "done" means

A compile is necessary, never sufficient. A patch translation is only *done* when
the running host app in the simulator matches the Origami artboard visually AND
Samuel has spot-checked. Your job here is to make the code correct enough to
reach that gate; the gate itself is Mac-side. See `NEEDS-VERIFY.md` for what's
queued and what's earned.

### Beats

Reframe first: **each pattern that lands is a deliverable, not a test.** The
corpus is a public gallery for the Origami community *and* the training set that
teaches swami the general rules. Every PR = one more entry in the gallery + one
more mapping rule earned. That's the shape of the loop.

Names borrowed from `michaelshimeles/skills`; content is swami-specific.

1. **Isolate** — one pattern per branch (per worktree when a Mac agent is running
   alongside). The unit of change is *one .origami → one generated view → one PR*.
2. **Build** — parser and/or codegen edits in `tool/`. Run the tree-sitter-swift
   pre-gate on the generated `.swift` before opening a PR. Compile-clean is the
   ticket to enter the queue, not proof of correctness.
3. **Prove** — the GHA macos-15 runner installs Origami itself (from its Sparkle
   appcast) and runs both sides in the same job: opens each pattern's `.origami`
   in Origami and screenshots via `View → Take Screenshot`; boots SwamiHost with
   `SWAMI_PATTERN=<slug>` and screenshots the sim; SSIM-compares (threshold 0.95).
   Score gates the merge (ADR-0013). Sticky PR comment posts swami / origami /
   diff side by side for spot-checks.
4. **Ship** — merge on green auto-compare. Human sign-off remains for interactions
   (gesture-driven behavior) and for anything the compare flags; that's a
   shrinking surface, not the default path. Resolve the matching `NEEDS-VERIFY.md`
   item on merge.

Cross-cutting: **`unslop`** (`skill/unslop/`) is a pass on anything a human will
read — commit messages, PR titles/bodies, ADRs, `NEEDS-VERIFY.md` entries. Run it
before you push.

### Conventions

- Parser deterministic and dependency-light (stdlib only, per ADR-0004).
- IR **semantic-rich** — preserve names (colors, type styles, patch labels), not
  just values (ADR-0007).
- Record non-trivial decisions as ADRs in `docs/decisions/`.
- One-purpose commits; PR title describes the change, body explains the why.
- **Verify gate = XcodeBuildMCP** (local MCP on the Mac, proxied
  `mcp__remote-devices__XcodeBuildMCP__*`). Build/test/screenshot over MCP — no
  Terminal typing (Terminals/IDEs are click-only by macOS policy) and no Linux VM.
  Project: `app/Swami.xcodeproj`, scheme `SwamiHost`, sims are iOS 26.2. Compile
  gate is live; visual gate is the runner job per ADR-0013.
- Verification is visual against the Origami render; corpus = Origami Patterns
  gallery.
- **Parser TODO** (unblocks faithful constants): decode a node's **input-port
  default values** (schema-less FlatBuffers union), not just node types/names.
  Needed to read exact patch defaults — e.g. origami.DragSettings' Momentum
  Friction / Rubber Band Friction — instead of iOS-standard stand-ins.

---

## Architecture — the agent factory

Two orchestrators as peers (Human, Claude session) driving three workers
(Builder GA, Verify GA, Review GA) around a shared substrate. Learning surfaces
sit under the loop and each hold one kind of durable knowledge; work rolls
through intent → build → verify+review (parallel) → merge → post-merge.

```mermaid
flowchart TB
    subgraph Orchestrators["Orchestrators (peers)"]
        direction LR
        H[Human]
        C[Claude session]
    end

    subgraph Workers["Workers (GitHub Actions)"]
        direction LR
        B["Builder GA<br/>(future)"]
        V["Verify GA<br/>(existing — verify.yml)"]
        R["Review GA<br/>(future)"]
    end

    subgraph Loop["The loop"]
        direction LR
        I[Intent] --> BLD[Build]
        BLD --> P{{Verify + Review in parallel}}
        P --> M[Merge]
        M --> PM[Post-merge]
    end

    subgraph Learning["Learning surfaces (knowledge kinds)"]
        direction TB
        S["structural<br/>→ parser (tool/src/parser)"]
        F["functional<br/>→ helpers (Swami package)"]
        D["documentation<br/>→ DocC (Swami.docc)"]
        PR["procedural<br/>→ skill: pattern-translation"]
        PW["process<br/>→ skill: workflow"]
        E["evaluative<br/>→ skill: visual-review"]
        CX["contextual<br/>→ AGENTS.md"]
        FA["factual<br/>→ CLAUDE.md (pointer to AGENTS.md)"]
        RA["rationale<br/>→ ADRs (docs/decisions)"]
    end

    Orchestrators --> Loop
    Loop --> Workers
    Workers -.evidence.-> Loop
    Loop -.writes-back.-> Learning
    Learning -.loads on next turn.-> Orchestrators
```

- **Orchestrators (peers).** Human and Claude session both drive the loop; either
  can initiate intent, delegate, or take a spot-check pass. Neither owns the
  other.
- **Workers.** Verify GA is live today (`.github/workflows/verify.yml` — Path B
  per ADR-0013: runner installs Origami, live-renders both sides, SSIM-compares).
  Builder GA and Review GA are planned lanes on the same substrate.
- **Learning surfaces.** Each knowledge kind writes into exactly one place, so a
  new agent boots by reading the surface and the pointer is unambiguous:
  - **structural** — the parser's model of `.origami` (fields, tags, layouts).
  - **functional** — patch-matched helpers in the Swift package.
  - **documentation** — human-facing prose via DocC.
  - **procedural** — the "how to translate one pattern" skill.
  - **process** — the "how the loop moves" skill.
  - **evaluative** — the "how to read a compare" skill.
  - **contextual** — this file: what the project is, how to work here.
  - **factual** — the durable oracle values and format facts; the on-disk file
    (`CLAUDE.md`) is a pointer to AGENTS.md so agents that only read CLAUDE.md
    still land in the same place.
  - **rationale** — ADRs. Why a call was made, not what to do next.
- **The loop.** Intent lands, Builder produces a change, Verify and Review run
  in parallel on the PR (pixel gate + human-readable review), merge on both
  green, post-merge writes back to the relevant learning surface so the next
  turn starts smarter.
