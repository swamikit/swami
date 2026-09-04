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
tool/                Python parser + codegen
├── src/parser/      the schema-less FlatBuffers walker (stdlib only)
├── src/codegen/     IR → SwiftUI writer (stdlib only)
└── examples/        working seed translations (Touch is the oracle)
app/                 Swami.xcodeproj — framework + SwamiHost verify host
docs/decisions/      ADRs — read these when in doubt about a design call
skill/               verified-delivery notes + adopted skills (unslop, …)
```

Meta assets (patterns/, catalog snapshots, .origami downloads) are `.gitignore`d and
live in a separate private repo. Do not add any `.origami` file to this repo.

## What you (Codex, Linux) CAN do

- Iterate on `tool/src/parser/*.py` and `tool/src/codegen/*.py` — pure Python stdlib,
  no build step, run directly with `python3`.
- Run the tree-sitter-swift syntax **pre-gate** on generated Swift (`scripts/codex-setup.sh`
  installs the grammar). This catches syntax errors — not type errors.
- Read the Swami framework sources (`app/Swami/`) for reference but do NOT try to
  build the Xcode project here — Apple-only.
- Draft ADRs, update `BACKLOG.md`, refine the IR schema, propose codegen changes.
- Open PRs; the Mac-side runner will do the pixel gate on merge candidates.

## What you CAN'T do here

- **Build the Xcode project** (`app/Swami.xcodeproj`) — macOS only.
- **Run the iOS simulator, screenshot, pixel-verify** — that's the macOS runner's job
  (driven by a Cowork/local agent via XcodeBuildMCP).
- **Read the installed Origami Studio app's Patches folder** — that's on Samuel's Mac.
  Use the origami.design docs mirror (private repo) as the fallback reference.

## What "done" means

A compile is necessary, never sufficient. A patch translation is only *done* when the
Reviewer has read the swami / origami / diff triplet from the runner and Samuel
has spot-checked flagged cases. SSIM is evidence in that read, not the verdict
(ADR-0014). Your job here is to make the code correct enough to reach that gate;
the gate itself is Mac-side. See `BACKLOG.md` for what's queued and what's earned.

**Interim (until Reviewer GA ships):** the Reviewer skill (skill/review) is in flight
on PR #11 and hasn't landed yet, so *today's* visual gate is Sam reading the same
evidence triplet by hand. The workflow shape is the same either way — the sticky
PR comment is the Reviewer's input surface — so the flip is a one-line target change,
not a re-plumb.

## Learned rules — Origami rendering

**Safe-area behavior**: Origami's artboard rendering may ignore safe insets (top
device area / Dynamic Island region missing in the exported PNG). When comparing
Swami's sim screenshot to Origami's "Take Screenshot" output:

- Origami: often no top-safe-area strip
- Swami sim: renders full screen including status bar / Dynamic Island

Symptoms: vertical offset in overlays; SSIM penalizes but real content matches.

Mitigations (pick per pattern):

- Use `.ignoresSafeArea(.all)` on Swami's top-level view (matches Origami's rendering)
- Composite a phone-frame SVG around both renders at CI time (normalizes both to the same frame)
- Crop Swami's screenshot to remove the top ~100px before compare (least ideal; loses visual context)

Note: this rule is an example of what the V4 self-improving loop would surface
automatically — agents observing recurring offset across 3+ PRs would propose the
rule and land it here.

## Beats

Reframe first: **each pattern that lands is a deliverable, not a test.** The corpus
is a public gallery for the Origami community *and* the training set that teaches
swami the general rules. Every PR = one more entry in the gallery + one more mapping
rule earned. That's the shape of the loop.

Names borrowed from `michaelshimeles/skills`; content is swami-specific.

1. **Isolate** — one pattern per branch (per worktree when a Mac agent is running
   alongside). The unit of change is *one .origami → one generated view → one PR*.
2. **Build** — parser and/or codegen edits in `tool/`. Run the tree-sitter-swift
   pre-gate on the generated `.swift` before opening a PR. Compile-clean is the
   ticket to enter the queue, not proof of correctness.
3. **Prove** — the GHA macos-15 runner installs Origami itself (from its Sparkle
   appcast) and runs both sides in the same job: opens each pattern's `.origami`
   in Origami and screenshots via `View → Take Screenshot`; boots SwamiHost with
   `SWAMI_PATTERN=<slug>` and screenshots the sim; SSIM-compares and posts the
   score as evidence. Runner mechanics per ADR-0013. **SSIM is a data point, not
   a verdict** — the metric over-rewards palette match on our flat-color subject
   matter and has repeatedly greenlit obvious mismatches (ADR-0014, supersedes
   ADR-0013's implicit SSIM-as-gate). Sticky PR comment posts swami / origami /
   diff side by side so the visual gate can read them.
4. **Ship** — merge on Reviewer approval + Sam's spot-check on flagged cases
   (ADR-0014). The Reviewer skill (skill/review) reads the swami / origami / diff
   triplet and calls state match, alignment, chrome, semantic correctness — that's
   the visual gate. Human sign-off remains for interactions (gesture-driven
   behavior). Resolve the matching `BACKLOG.md` item on merge. *Until Reviewer
   GA lands (PR #11), that read is Sam's by hand on the same posted evidence — same
   surface, same criteria, just not yet automated.*

Cross-cutting: **`unslop`** (`skill/unslop/`) is a pass on anything a human will
read — commit messages, PR titles/bodies, ADRs, `BACKLOG.md` entries. Run it
before you push.

## Conventions

- Parser stays deterministic and dependency-light (stdlib only, per ADR-0004).
- IR is **semantic-rich** — preserve names (colors, type styles, patch labels), not
  just values (ADR-0007).
- Record non-trivial decisions as ADRs in `docs/decisions/`.
- One-purpose commits; PR title describes the change, body explains the why.
