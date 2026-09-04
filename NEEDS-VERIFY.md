# NEEDS-VERIFY — drive-gate backlog (verified-delivery)

Nothing here is "done." Each item is DRAFT/UNVERIFIED until an agent drives the real running
product (XcodeBuildMCP `build_run_sim` → `screenshot`, read against intent, compared to the
Origami artboard) AND Samuel spot-checks. A clean compile is necessary, never sufficient.

Gate is blocked until the `SwamiHost` app target is wired into Swami.xcodeproj (framework has
nothing to launch). Compile-gating also requires code synced into the framework by Samuel's local
agent — the cloud loop does not write there.

## Queue
- **Touch (Interaction_Touch)** — LAYOUT-VERIFIED via SwamiHost screenshot (2026-09-03, Trove
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
- **Interaction_Drag (examples/Interaction_Drag.draft.swift)** — STRUCTURAL DRAFT only. Geometry,
  colors, bounds, layer count NOT read from the graph (parser tail heuristic over-includes the
  embedded Drag component on this 534 KB file). Must: (a) generalize the parser to isolate the real
  placed graph, (b) re-generate from true values, (c) drive-verify.

## Verify-gate — ADR-0013 (runner installs Origami, live render, no cache)
- **Path B pivot** ✅ landed. Superseded ADR-0012's cache approach. Runner fetches
  Origami's Sparkle appcast, installs the app, opens each pattern from origami.design's
  public URL, drives `View → Take Screenshot`, then diffs against SwamiHost's sim render.
  No cross-repo dep, no secrets.
- **PATTERNS growth**: current single entry `touch:Interaction_Touch`. Add one line per
  translated pattern (`<slug>:<origami-filename-stem>`) as the corpus grows; the ContentView
  switch in `app/SwamiHost/ContentView.swift` gets a matching case.
- **Parser generalization** — biggest live blocker. Currently only Touch-sized files parse
  cleanly (placed-vs-library fixed tail offset). Interaction_Drag over-includes the embedded
  Drag component. Until this generalizes, we can't feed the loop pattern N+1.

## Reviewer + agent factory (from 2026-09-04 architecture pass)
- **Deprecating Codex** — Codex's review has been useful (P1 findings on PR#2 caught real
  bugs) but it doesn't take custom instructions. Once the Claude review GA ships, disable Codex
  at chatgpt.com/codex to avoid duplicate review noise. Not urgent — Codex catching things is
  better than nothing during the transition window.
- **Build Claude review GA** (`.github/workflows/review.yml`) — replaces adversarial-review
  skill idea. GitHub Action + Claude API call. Reads the diff + verify evidence + sticky comment.
  Posts inline comments on the PR. Triggers on `pull_request` open/synchronize + `@claude review`
  comment for manual re-review. Deserves its own PR; ~day of work.
- **Parser port extraction** — unblocks the Builder's *structural self-verify*. Right now the
  Builder can produce a helper whose parameter list silently drifts from Origami's patch ports.
  Adding port extraction to the parser + a script that diffs helper signature vs. Origami's
  patch definition closes the loop. Parser TODO, real Python work.
- **Agent factory shape → AGENTS.md** — the architecture diagram from today's session (actors,
  loop steps, knowledge surfaces, autonomy trajectory) should land in AGENTS.md as prose + a
  Mermaid-ish diagram. Its own tiny PR.

## Skill queue (in priority order)
- **`skill/workflow/`** — swami-repo house rules. Branch naming, PR template usage, review
  invocation, video-in-PR expectations, agent factory. Codifies stuff currently living in
  session transcripts. Highest priority — this is where "what to review per PR" and "PR shape"
  actually get written down.
- **`skill/pattern-translation/`** — community-portable. How to translate one Origami pattern.
  Reads Swami's DocC mapping tables + helpers + this skill's learned rules. Output: a SwiftUI
  view. Deliberately does not know about our PR flow. Deep skill — deserves its own focused
  session.
- **`skill/docc-authoring/`** — Swami's DocC house style. Which directives we use (Metadata,
  PageKind, PageImage, Links, TabNavigator, CallToAction), sample-code page shape, gallery
  article shape. Ensures any agent producing DocC pages produces them in the house style.
- **`skill/visual-review/`** — checks list the review GA runs. State mismatch, alignment,
  chrome, semantic correctness, evidence completeness. Same shape as unslop — a house rulebook
  the reviewer follows.
- **`skill/adversarial-review/`** — DEFERRED / likely subsumed by visual-review + Claude review
  GA. Sam wanted to "visit soon" but Codex's showing (three real P1s on PR#2) makes the
  standalone skill less urgent.

## Follow-up ADRs on the same runner substrate (ADR-0013 enables)
- **Parser verification via Origami Inspector** — osascript can read AX attributes of
  Origami's Inspector panel (layer heights, corner radii, colors, positions) and diff
  against the parser's IR. Gives the parser a live oracle without human eyes.
- **Interaction gate** — same runner drives a gesture on both Origami's viewer and
  SwamiHost's sim, screenshots the responses, diffs. Closes the ISAT loop
  (Interaction → State → Animation → Transition).
- **Video side-by-side** — sim `xcrun simctl io … recordVideo` on one side + Origami's
  `View → Record…` on the other, both driven by a synthesized touch sequence. Blocked
  on the interaction gate landing; for static renders, video is overkill. Post as MP4
  in the sticky comment (GitHub embeds .mp4 inline in PR comments).

## Deferred — Tutorials (post-first-few-patterns)
- **Translating visually** — pick one patch (say `builtin.layer.hover`), show Origami's
  editor screenshot, walk through the SwiftUI equivalent with a live render at each step.
- **Using the skill** — designer opens their own .origami in swami, gets SwiftUI back.
  Only earns its slot once the skill/MCP actually exists.
- **ISAT in declarative SwiftUI** — how *Interaction → State → Animation → Transition*
  (Samuel's framing of Origami's dataflow) lands in SwiftUI's `gesture → @State →
  withAnimation → interpolation` stack. Live example per stage.

## Deferred — future ambitions
- **Native-vs-helper side-by-side** — every pattern generated in TWO forms: pure SwiftUI (no
  helpers) and with-helpers. Shows honestly which helpers earn their weight; exposes cases
  where native is nearly-enough. Requires codegen to support two output modes.
- **Sample-code Download button** — CI builds a mini Xcode project per pattern
  (`Interaction_Touch.zip` with Swami as SPM dep + a simple app target), uploads to release
  assets. DocC sample-code page's `@CallToAction(url:, purpose: download)` links to it.
- **Phone-framed previews** — Sam provides SVG; ImageMagick composites the raw render inside
  the frame at CI time. One asset serves gallery cards, sample-code page, PR evidence.
  Video path: FFmpeg composites the same frame around an MP4.

## Housekeeping
- **swami-private/references/ deletion** — cache is now dead weight per ADR-0013. Delete
  the directory in a follow-up swami-private commit; keep `scripts/render-references.sh`
  (still useful for local troubleshooting).
- **ADRs 0001–0003 accounting**: the ADR directory jumps from 0004 to 0011 with no 0001-0003.
  Either recover them from history or explicitly note they were archived — silent gaps read
  as "you forgot how to number files."
- **CLAUDE.md → AGENTS.md consolidation** — AGENTS.md is the agent-agnostic name (Cursor,
  Codex, Claude, etc. read it). Move workflow content into AGENTS.md; reduce CLAUDE.md to a
  one-line pointer or delete. Gentle cleanup, do after 3-4 more patterns land.

## Parser TODOs blocking faithful output
- **Placed-vs-library generalization** (core challenge): fixed tail offset (360000) is tuned to the
  Touch example; on Interaction_Drag (534 KB) it captures Drag's component internals as false
  "placed" nodes. Need a structural way to find the document's placed graph (root reference), not a
  byte offset. Blocks trustworthy translation of any pattern embedding composite patches.
- **Input-port default-value decoding**: DragSettings port defaults (Momentum/Rubber Band Friction,
  Clip) are NOT reachable by naive vtable field-offset walking (returns zeros / canvas coords).
  Values are a typed value-union stored indirectly — needs real union tag→payload decoding. Blocks
  faithful momentum constants in drag().
- **Port list extraction** (new, per architecture pass) — extract each patch's input/output port
  names and types so the Builder can self-verify its helper signature matches Origami's patch.
  Enables the structural gate that turns "compile-clean" into "compile-clean AND port-matched."
