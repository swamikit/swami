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
- **drag() helper (origami.Drag)** — implemented with faithful ports (Position/Translation/Velocity
  out; Enable/Momentum/bounds/Reset in). Rubber-band friction uses Origami's documented 0.15
  default; release momentum comes from the gesture's measured projection rather than an iOS
  scroll default. Drive: fling → bounded momentum settle; over-drag → rubber-band resistance;
  reset → origin and all outputs clear; fresh touch → stale velocity clears.
- **Interaction_Drag** — **ITEM 2 OF 69** (Issue #140 corrective delivery): the runner-produced
  reference is 750×1334 pixels (375×667 points at 2×). It shows an `#DD70DF` full-screen canvas,
  an inset 315×607-point `#E5A6E6` rounded interaction area, and a centered 120×120-point white
  card with a 15-point radius. These values are read from the reference PNG's decoded RGBA pixels
  and boundaries; they do not depend on an unproven packed-color channel interpretation.
  The placed graph confirms `origami.Drag`, calculated layer-edge bounds, and a `Snap to origin`
  branch that pulses Reset when both position axes are within 100 points of center on touch-up.
  Implementation and DocC are complete; exact-head runner screenshots, Maestro H.264 recording,
  and Reviewer verdict remain the integration gate. Resolve this item when that head merges.

## Verify-gate — ADR-0013 (runner installs Origami, live render, no cache)
- **Path B pivot** ✅ landed. Superseded ADR-0012's cache approach. Runner fetches
  Origami's Sparkle appcast, installs the app, opens each pattern from origami.design's
  public URL, drives `View → Take Screenshot`, then diffs against SwamiHost's sim render.
  No cross-repo dep, no secrets.
- **PATTERNS growth**: `touch:Interaction_Touch drag:Interaction_Drag` (2 of 69 registered).
  Registry drives the verify gate: `.github/patterns.txt` lists slugs → stems; the `changes`
  job reads it and passes `PATTERNS` to the pixel-gate. Each new pattern adds one entry to
  the registry AND one `case` to the ContentView switch — both in the same commit.
- **Parser generalization** — ✅ landed with Interaction_Drag. `placed_root_offset()` now
  structurally isolates the placed graph from embedded component internals. Pattern N+1
  ready for translation.

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

## Parser TODOs blocking faithful output
- **Placed-vs-library generalization** ✅ RESOLVED. `placed_root_offset()` structurally isolates
  the placed graph from embedded component internals using the FlatBuffers root reference.
- **Input-port default-value decoding**: DragSettings port defaults (Momentum/Rubber Band Friction,
  Clip) are NOT auto-decoded by the parser. Current workaround: physics constants use Origami-
  documented defaults (0.15 friction, 0.2 momentum). Full resolution requires FlatBuffers port-value
  union tag→payload decoding in the parser.

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

The parser successfully uses `placed_root_offset()` to isolate the placed graph from embedded component internals. Interaction Drag's corrected composition does not treat arbitrary 32-bit words as colors: its rendered RGBA values and geometry come from the runner reference, while structural parsing confirms the Drag, bounds, and snap-to-origin nodes.

Input-port union decoding remains a parser generalization task. Interaction Drag does not block on a guessed momentum-friction constant because its SwiftUI mapping uses the driven gesture's measured projection.

Issue #140 supersedes #119 only after Steward records the merged PR and exact-head verify run.
