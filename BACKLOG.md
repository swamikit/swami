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
- **Interaction_Drag (examples/Interaction_Drag.draft.swift).** STRUCTURAL DRAFT only. The parser
  now isolates the real 24-node / 19-edge placed graph and decodes instance values, but catalog
  defaults and parent/child layer membership still block faithful SwiftUI emission. Must:
  (a) decode those remaining facts, (b) generate from the semantic IR, (c) drive-verify.

## Verify-gate — ADR-0013 (runner installs Origami, live render, no cache)
- **Path B pivot** ✅ landed. Superseded ADR-0012's cache approach. Runner fetches
  Origami's Sparkle appcast, installs the app, opens each pattern from origami.design's
  public URL, drives `View → Take Screenshot`, then diffs against SwamiHost's sim render.
  No cross-repo dep, no secrets.
- **PATTERNS growth**: current single entry `touch:Interaction_Touch`. Add one line per
  translated pattern (`<slug>:<origami-filename-stem>`) as the corpus grows; the ContentView
  switch in `app/SwamiHost/ContentView.swift` gets a matching case.
- **Parser generalization.** Placed-vs-library separation is structural for zipped documents.
  The next live blockers are catalog default values and layer hierarchy.

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
- **Revoke retired review secrets** — remove the repository's unused
  `GEMINI_API_KEY` and `OPENROUTER_API_KEY` Actions secrets after PR #93 lands;
  ADR-0016 removed their final workflow consumer.
- **swami-private/references/ deletion** — cache is now dead weight per ADR-0013. Delete
  the directory in a follow-up swami-private commit; keep `scripts/render-references.sh`
  (still useful for local troubleshooting).
- **ADRs 0001–0003 accounting**: the ADR directory jumps from 0004 to 0011 with no 0001-0003.
  Either recover them from history or explicitly note they were archived — silent gaps read
  as "you forgot how to number files."

## Parser TODOs blocking faithful output
- **Catalog default-value decoding**: instance overrides now decode (including Drag Settings
  Momentum = true and Momentum Friction = 4), but inputs without overrides inherit values from the
  embedded patch catalog. Resolve that link rather than treating absent overrides as zero.
- **Layer hierarchy decoding**: node and edge membership is exact, but parent/child layer placement
  is not represented yet. Codegen stops instead of guessing a SwiftUI stack.

## Infra self-healing loop (V4 prerequisites)
- **`.github/ISSUE_TEMPLATE/infra-blocker.md`** (landed in PR #24) — structured evidence template for when a Builder or Review GA hits a runner-level failure (Origami install broken, sim boot fails, ImageMagick not available, etc.). Template auto-applies `label: infra-blocker` so downstream queries are label-based.
- **`skill/troubleshooting/`** (landed in PR #24) — living runbook of known infra issues and their fixes. Each entry: symptom, evidence signature, workaround, verification. Referenced by both Builder and Review skills as a pre-flight check.
- **Builder pre-flight step** (blocked on Builder GA — PR #27) — before real work, `gh issue list --label infra-blocker --state open --limit 100` and check for matches against current environment. Apply workaround or escalate.
- **Triage GA** (in-flight — PR #22) — fires on `on: issues: [opened, edited]`. Runs on ubuntu-latest (Claude API). Categorize, dedupe, route (label 'ready' / 'needs-info' / 'translate' / etc.). Closes the loop Codex findings → issues → routed to Builder or human.
- **Triage on PRs** (not yet scheduled) — extend triage.yml to also fire on `pull_request: [opened, edited]` so it can proactively skim new PRs for cross-ADR contradictions and stale assumptions. Gap surfaced 2026-09-04.
