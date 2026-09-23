# BACKLOG — drive-gate backlog (verified-delivery)

Nothing here is "done." Each item is DRAFT/UNVERIFIED until an agent drives the real running
product (XcodeBuildMCP `build_run_sim` → `screenshot`, read against intent, compared to the
Origami artboard) AND Samuel spot-checks. A clean compile is necessary, never sufficient.

Gate is blocked until the `SwamiHost` app target is wired into Swami.xcodeproj (framework has
nothing to launch). Compile-gating also requires code synced into the framework by Samuel's local
agent — the cloud loop does not write there.

## Queue
- **Touch (TouchOrigamiExample)** — LAYOUT-VERIFIED via SwamiHost screenshot (2026-09-03, Trove
  ProMax iOS 26.2): magenta bg #DD70DF ✓, white Tap card ✓, radius ~20 ✓, spacing ~30 ✓, 4 rows in
  order ✓, ovals correctly invisible at rest ✓. NOT done — two open items:
  (a) Down/DoubleTap/LongPress card tints (progressive pink) are UNCONFIRMED vs the real Origami
      artboard — the oracle only pinned "Tap frame white"; compare side-by-side or Samuel's eye.
  (b) INTERACTION undriven — static shot can't verify the 100×100 oval growing from the touch point
      on press/tap. Needs a driven gesture in the sim (touch-injection tool) or Samuel driving live.
- **drag() helper (origami.Drag)** — drafted, syntax-clean, NOT compiled in-framework, NOT driven.
  Momentum/rubber-band CONSTANTS are placeholders (iOS-standard), not Origami's real defaults
  (see parser TODO). Drive: fling → momentum decay matches Origami feel; over-drag past bounds →
  rubber-band resists then settles; release at rest → clamps; velocity reset on fresh touch.
- **Interaction_Drag** — **ITEM 2 OF 69** (2026-09-07): Artboard 888×1212, tan card
  #B0E0B27B, 220×140 centered, corner radius 20, drag with momentum + rubber-band bounds,
  snap-to-center. Parser generalized via node-vector/artboard detection (ADR-0017):
  24 placed nodes / 19 edges, `origami.Drag` as ONE node.
  TRANSLATION COMPLETE — pending runner verification (pixel triplet + Reviewer verdict).
  Card color channel order unproven; marked as TODO in source until parser confirms.

## Verify-gate — ADR-0013 (runner installs Origami, live render, no cache)
- **Path B pivot** ✅ landed. Superseded ADR-0012's cache approach. Runner fetches
  Origami's Sparkle appcast, installs the app, opens each pattern from origami.design's
  public URL, drives `View → Take Screenshot`, then diffs against SwamiHost's sim render.
  No cross-repo dep, no secrets.
- **PATTERNS growth**: `touch:Interaction_Touch drag:Interaction_Drag` (2 of 69 registered).
  Registry drives the verify gate: `.github/patterns.txt` lists slugs → stems; the `changes`
  job reads it and passes `PATTERNS` to the pixel-gate. Each new pattern adds one entry to
  the registry AND one `case` to the ContentView switch — both in the same commit.
- **Parser generalization** — ✅ landed (ADR-0017). Node-vector scan + artboard
  (`*.Screen`) anchoring structurally isolates the placed graph from embedded component
  internals, and the parser now decodes edges. Validated head-to-head across the corpus
  (Interaction_Drag 24 nodes / 19 edges; Animation/Logic/Scroll patterns collapse from
  148–205 nodes / 3 phantom screens to ~17–24 / 1 screen). Supersedes the earlier
  `placed_root_offset()` boundary. Pattern N+1 ready for translation.

## Follow-up ADRs on the same runner substrate (ADR-0013 enables)
- **Parser verification via Origami Inspector** — osascript can read AX attributes of
  Origami's Inspector panel (layer heights, corner radii, colors, positions) and diff
  against the parser's IR. Gives the parser a live oracle without human eyes.
- **Interaction gate** — same runner drives a gesture on both Origami's viewer and
  SwamiHost's sim, screenshots the responses, diffs. Closes the ISAT loop
  (Interaction → State → Animation → Transition).

## Deferred — Tutorials (post-first-few-patterns)
- **Translating visually** — pick one patch (say `builtin.layer.hover`), show Origami's
  editor screenshot, walk through the SwiftUI equivalent with a live render at each step.
- **Using the skill** — designer opens their own .origami in swami, gets SwiftUI back.
  Only earns its slot once the skill/MCP actually exists.
- **ISAT in declarative SwiftUI** — how *Interaction → State → Animation → Transition*
  (Samuel's framing of Origami's dataflow) lands in SwiftUI's `gesture → @State →
  withAnimation → interpolation` stack. Live example per stage.

## Housekeeping
- **Revoke retired review secrets** — `GEMINI_API_KEY` is active again through
  Agent Factory's Builder and Reviewer callers. Remove only
  `OPENROUTER_API_KEY` if no configured Factory provider uses it.
- **swami-private/references/ deletion** — cache is now dead weight per ADR-0013. Delete
  the directory in a follow-up swami-private commit; keep `scripts/render-references.sh`
  (still useful for local troubleshooting).
- **ADRs 0001–0003 accounting**: the ADR directory jumps from 0004 to 0011 with no 0001-0003.
  Either recover them from history or explicitly note they were archived — silent gaps read
  as "you forgot how to number files."
- **Regenerate the Touch example artifacts** — `tool/examples/TouchOrigamiExample.graph.json`
  (and downstream `.ir.json` / `.generated.swift`) predate ADR-0017's parser and still carry the
  old 49-node / no-edge shape. Regenerate from the Touch `.origami` (Mac-side; the fixture is
  gitignored out of this repo) with the new parser and re-verify.

## Parser TODOs blocking faithful output
- **Placed-vs-library generalization** (core challenge) — ✅ RESOLVED (ADR-0017). Structural
  node-vector + artboard (`*.Screen`) anchoring replaces the `tail=360000` byte offset and the
  later `placed_root_offset()` boundary; `origami.Drag` now reads as one placed node and the
  parser decodes edges.
- **No-artboard fallback** — ✅ RESOLVED FOR THE CORPUS (M1, ADR-0017 amended); a **heuristic**,
  provisional where the artboard isn't serialized in a candidate vector — not a settled general
  guarantee. When no candidate node-vector owns a `*.Screen` (the artboard node isn't always
  serialized inside a clean patch vector, and some patterns use a non-iOS artboard like
  `desktop.Screen`), the selector falls back to the node-vector with the highest **visual-layer
  density**, not the largest vector; `TYPE_RE` was broadened to recognize non-iOS artboards.
  Full-corpus sweep (64 fixtures): 0 blobs (was 33 of 64 over 150 nodes), every placed graph
  carries a visual layer tree. `Layers_List` 171→15, `Loops_Sum` 36→11, `Logic_Counter` 205→20,
  `Utilities_Grid` 276→56. `parse()` marks every fallback result `selection:
  "visual-density-fallback"` **plus** a `selection_warning`, so callers treat it as provisional;
  the screen→vector linkage for the general no-artboard case is the residual open problem.
- **Input-port default-value decoding** (M2, encoding cracked — impl pending): a port's default
  lives INLINE as an **f64 double** in the port's `f[4]` value-table. Ports are the node's `f[5]`
  (and `f[6]`) child vectors; each port table is `f[1]`=ordinal, `f[2]`=name, `f[4]`=value-table.
  Verified on Interaction_Drag: layer `Opacity`=1.0, `Scale`=1.0, `Pivot`=0.5 (exact Origami
  defaults), `origami.DragSettings` `Momentum Friction`=8.0. REMAINING: the populated slot within
  `f[4]` is the union tag (scalar number vs Point vs Color-RGBA) — map slot→type so multi-component
  values decode, then oracle-check the `drag()` physics constants. NOTE: card/artboard dimensions
  (220×140, 888×1212) are NOT stored as literal doubles anywhere in the buffer — they're derived or
  device-preset, so geometry needs separate handling from scalar port defaults.

## Infra self-healing loop (V4 prerequisites)
- **`.github/ISSUE_TEMPLATE/infra-blocker.md`** (landed in PR #24) — structured evidence template for when a Builder or Review GA hits a runner-level failure (Origami install broken, sim boot fails, ImageMagick not available, etc.). Template auto-applies `label: infra-blocker` so downstream queries are label-based.
- **`skill/troubleshooting/`** (landed in PR #24) — living runbook of known infra issues and their fixes. Each entry: symptom, evidence signature, workaround, verification. Referenced by both Builder and Review skills as a pre-flight check.
- **Builder pre-flight step** — Agent Factory Builder must query open
  `infra-blocker` issues before real work and apply a known workaround or
  return a concrete blocker to Steward. The old in-repository Builder GA item
  from PR #27 is superseded by the reusable Builder role.
- **Issue qualification and routing** — Agent Factory Steward supersedes the
  in-repository Triage GA from PR #22. It admits well-formed `ready` work,
  dispatches Builder, and owns blocker routing without creating issue spam.
- **Steward PR intake** (not yet scheduled) — consider letting Steward skim
  new PRs for cross-ADR contradictions and stale assumptions. Keep this
  separate from the required independent Reviewer verdict.

## Generalization Gap (Issue #83 learning)

The parser now uses structural node-vector + artboard (`*.Screen`) detection (ADR-0017) to isolate the placed graph from embedded component internals, and decodes edges. However, the following gaps remain:

**Unresolved (port values)**: Exact drag physics constants (Momentum Friction, Rubber Band Friction, decel rate) are still placeholders from iOS defaults. These live as port default *values* inside origami.DragSettings — reading them needs FlatBuffers port-value decoding, which the parser doesn't implement yet.

**Unresolved (color channels)**: Card fill `#B0E0B27B` decoded as ARGB (alpha-first, yielding tan rgb 224,178,123). The RRGGBBAA reading would yield pale green rgba(176,224,178,123). Both interpretations are structurally valid; neither has parser-IR evidence. Locking in requires either: (a) extending the parser to emit color value objects with known channel order, or (b) an Origami Inspector AX readout confirming the hex. Until then, the literal in `Interaction_Drag.swift` is marked TODO.

**Not expanded** (per issue scope): This issue focused on delivering Interaction_Drag as the first corpus entry. Parser, codegen, and DocC improvements are by-products recorded here, but not expanded to a second pattern.
