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
- **drag() helper (origami.Drag)** — source constants are parser-decoded: Momentum Friction 8,
  Rubber Band Friction 8, and Rubber Band Tension 100. Issue #215 drives fling decay,
  over-drag resistance, boundary settlement, release-at-rest, and fresh-touch velocity reset.
- **Interaction_Drag** — **ITEM 2 OF 69**, UNVERIFIED pending the refreshed Issue #215
  runner verdict. The current implementation targets the oracle's plain Purple `#DD70DF`
  375×667 artboard with only the centered 120×120 white drag layer, momentum,
  rubber-band bounds, and near-origin reset pulse. Parser regression coverage pins the
  Drag constants (Momentum Friction 8, Rubber Band Friction 8, Rubber Band Tension 100).

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

## Parser fidelity
- **Placed-vs-library generalization**: `placed_root_offset()` follows the root component vector;
  Interaction_Drag regression coverage prevents embedded Drag internals from becoming placed nodes.
- **Input-port default values**: typed Float64 Number and RGBA Color union payloads are decoded.
  Interaction_Drag corpus tests pin Momentum Friction 8, Rubber Band Friction 8, Rubber Band
  Tension 100, and Purple `#DD70DF` in RGBA order.

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

The parser now successfully uses `placed_root_offset()` to structurally isolate the placed graph from embedded component internals. However, the following gaps remain:

**Resolved for Interaction Drag (Issue #215)**: typed input-port Number values and Color
RGBA payloads are parser output with corpus regression coverage. The prior `#B0E0B27B`
interpretation came from non-color bytes and is retired; the source color payload is the named
Purple token `#DD70DF` at full opacity.

**Not expanded** (per issue scope): This issue focused on delivering Interaction_Drag as the first corpus entry. Parser, codegen, and DocC improvements are by-products recorded here, but not expanded to a second pattern.
