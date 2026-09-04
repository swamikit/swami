# skill: verified-delivery notes, first-party skills, adopted skills

Three things live here:

1. **Notes on the swami-specific skill** we're building (the IR → SwiftUI translator
   half — the "judgment" side of the project).
2. **First-party skills** written for this repo's Build↔Review loop.
3. **Adopted skills** vendored from external repos when their shape fits our loop.

## The swami skill (not built yet)

A skill that reads the IR plus the Origami and SwiftUI docs and the mapping rules,
and emits idiomatic SwiftUI for the user's selection. Codify the mapping table and
hard-cases from `CLAUDE.md` (`NEXT_STEPS.md` step 5). Principles:

- Map to SwiftUI's **state graph**, not to free functions (the dataflow thesis).
- Scope output to the selection; use the whole-file IR as context (ADR 0002).
- **Flag, don't fake** the hard cases (continuous springs, custom JS patches, cyclic
  dataflow, absolute layout).
- Use `examples/` as worked-examples that steer translation.

## First-party skills

- **`review/`.** The Reviewer GA's playbook (`review/SKILL.md`). Codifies context
  reads, PR-type-specific checks, evidence-required findings, rebuttal handling,
  and the Build/Review message-exchange model. Load into any GA whose trigger is
  a PR event or an `@claude review` comment. Renamed from `visual-review` because
  the Reviewer's job covers visual, structural, methodology, and evidence, not
  pixels alone.
- **`troubleshooting/`.** Living runbook of known infra blockers (Origami install,
  sim boot, missing tools, license expiration). Builder and Review pre-flight
  checks read it before real work starts; any agent that ships a fix for a
  runner-level failure appends an entry. Companion issue template lives at
  `.github/ISSUE_TEMPLATE/infra-blocker.md`.

## Adopted skills

- **`unslop/`** — cuts AI tells from anything a human will read. Vendored from
  [michaelshimeles/skills](https://github.com/michaelshimeles/skills) (MIT, © Lauren Tan;
  see `unslop/LICENSE`). Run before every commit message, PR body, ADR, or NEEDS-VERIFY entry.

## In-repo skills

- **`workflow/`** — swami house rules: Beats, branch naming, PR templates,
  review flow, evidence expectations. Load before opening any PR against
  `swamikit/swami`.
- **`pattern-translation/`** *(stub)* — mapping-table judgment for translating
  one Origami pattern into idiomatic SwiftUI. Not written yet.
- **`docc-authoring/`** *(stub)* — how a translated pattern gets documented in
  DocC (article, tutorial, code listing, screenshot). Not written yet.
- **`review/`** *(stub)* — how the Reviewer GA runs its checks (visual,
  structural, methodology) — the Reviewer's skill. Not written yet.

## Prior art worth tracking

- [michaelshimeles/skills](https://github.com/michaelshimeles/skills) — same
  "evidence or it didn't happen" instinct as verified-delivery, packaged as a
  four-beat spine (Isolate → Build → Prove → Ship). AGENTS.md borrows the beat
  names; the `evidence-driven-testing` MPEG-TS-durable ffmpeg recorder is worth
  porting to the macOS runner once the pixel gate is live (interaction-driven
  patterns like Touch need video, not just a static shot).
