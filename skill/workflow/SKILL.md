---
name: workflow
description: swami-repo house rules — PR shape, Beats, review flow, evidence expectations, branch naming, which PR template to use for which change type. Load when opening any PR against swamikit/swami.
metadata:
  type: procedural
---

# Workflow — swami house rules

House rules for opening a PR against `swamikit/swami`. Read before you branch,
commit, or push. The point is a boring, legible git log and PRs that a human can
skim in thirty seconds and trust.

## Beats

Every pattern PR moves through four beats, in order:

1. **Isolate** — narrow the pattern to a testable slice. One Origami example, one
   IR fixture, one SwiftUI target.
2. **Build** — parser change, codegen change, or helper. Small, deterministic, ADR
   if it's a load-bearing choice.
3. **Prove** — visual evidence against Origami's render. Compile gate is table
   stakes; the SSIM score is posted as evidence, not a merge gate (per
   ADR-0014). The merge gate is Reviewer approval plus a human spot-check on
   flagged cases — interaction PRs and any comparison the Reviewer flags for
   human eyes.
4. **Ship** — squash-merge with a PR body a human can read months later. Once
   Claude Review GA is live, the merge path is **auto-merge on double green**
   (Codex + Claude Review both approving, no Reviewer human-eyes flag). Until
   then, the interim is a Sam spot-check on every merge — no auto-merge, even
   on a clean gate.

The beat vocabulary comes from AGENTS.md's methodology section. If a PR skips a
beat, say so and say why.

## Evidence-gated pickup

`ready` on an issue is a signal, not a start gun. Before an agent (Builder,
Triage, meta-Builder) picks up an issue or a task from its queue, it judges
whether the issue is *actually* ready to act on. Mechanical execution is how
you burn hours on the wrong thing.

Five checks, in order — the first that fails decides the outcome:

1. **Evidence threshold** — does the issue have enough concrete evidence
   (linked PRs, file:line refs, logs, screenshots) to act on? If not, comment
   asking for what's missing and don't start work.
2. **Recency** — was the evidence reproduced against current `HEAD` (per
   verified-delivery's evidence-required-claims)? Stale evidence gets
   re-verified against HEAD *before* acting; if it no longer reproduces, say so
   and close or re-scope.
3. **Priority alignment** — is this the highest-priority `ready` issue right
   now? Don't pull a p3 while a p1 is sitting `ready`. Sort the queue before
   you take from it.
4. **Blockedness** — are there dependencies (linked issues, waiting-on-review
   PRs on the same surface) that mean starting now creates a merge conflict or
   a rebased-away branch? Wait if so, and say what you're waiting on.
5. **Threshold for meta-issues** — `type:meta` issues (patterns, drift
   reports, "we keep hitting X") need **N=3 or more** independent pieces of
   evidence before Builder acts. One or two instances get a
   *"will pick up when a third instance appears"* comment and stay in the
   queue — meta-work on a sample of one is how the corpus gets bent to a coincidence.

**Decision, out loud.** The agent posts one of:

- **pick up** — start work; the checks passed. Note briefly why (which
  evidence, current HEAD ref).
- **defer** — comment on the issue with which check failed and what would
  unblock it; leave `ready` on or take it off per the check (missing evidence
  loses `ready`; blocked keeps it).
- **escalate** — needs a human call (priority tie, scope ambiguity,
  contradictory evidence). Comment, tag Sam, stop.

This is the "prioritizing judge" step. It's what makes `ready` mean *ready*
instead of *stale*.

## Branch naming

One prefix per change kind. Keeps `git log` and the branch picker readable.

- `translate/<pattern-slug>` — pattern translation work (Touch, Drag, Scroll…).
- `cleanup/<what>` — dead code, renames, moves. No behavior change.
- `docs/<what>` — ADRs, README, AGENTS.md, docs sites.
- `fix/<what>` — a bug or regression with a concrete reproduction.
- `skill/<name>-add` — new skill directory under `skill/`.
- `harness/<what>` — verify.yml, runner setup, MCP wiring, evidence pipeline.

Slugs are kebab-case and describe the thing, not the verb. `translate/touch`, not
`translate/add-touch-support`.

## PR templates

Before `gh pr create`, check `.github/PULL_REQUEST_TEMPLATE/` for a matching
template and pass it with `--template=<name>`. The full set lives there today:

- `pattern.md` — a pattern translation PR (Origami example → SwiftUI).
- `helper.md` — a reusable Swift helper (`drag()`, `sample()`, etc.).
- `parser.md` — parser or IR change.
- `harness.md` — verify.yml, runner, evidence tooling.
- `docs.md` — ADRs, README, methodology docs.
- `fix.md` — bug fix or regression, and the freeform fallback for one-off shapes.

If none fits and this PR shape has appeared before, **propose a new template** in
a doc/methodology follow-up — don't quietly force it into the closest one. If it
is truly one-off, use `fix.md` and describe freely.

## PR description shape

Regardless of template, every PR body answers:

- **What changed** — the diff in one paragraph a human can skim.
- **Why** — motivation, and link the ADR if the choice is load-bearing.
- **Evidence** — verify.yml sticky-comment link, DocC screenshot when relevant.
- **Deferred** — anything intentionally left for a follow-up, with a pointer.

No filler. No "This PR does X" restatements of the title. If there is nothing to
defer, drop the section — don't write "N/A".

## Review flow

Three reviewers, three lenses. Multi-reviewer habit, not multi-review-tool habit —
each catches what the others miss.

- **Codex** — automatic code review on every PR. Being deprecated once Claude
  Review GA lands; treat findings as one input, not the verdict.
- **Claude Review (GA)** — visual and methodology review. Reads screenshots,
  ADRs, and PR body against the beat.
- **Human** — final merge call. Merges nothing that hasn't been eyeballed.

A green Codex or a green Claude Review is not merge authority. A green human is.

## Evidence expectations

Static PRs — the ones where the pattern is a still frame at rest — get the
sticky-comment side-by-side (swami / Origami / diff). On a clean auto-compare
plus a Reviewer approve, auto-merge is the path — no separate human eyeball
required. Mandatory human review is limited to (a) interaction PRs (video
gate, below) and (b) PRs where the Reviewer explicitly flags for human eyes
(e.g. suspects the gate is green on the wrong pattern).

Interaction-gated PRs — Touch, Drag, Scroll, anything the user drives — will also
get an MP4 side-by-side once the interaction gate lands. Until then, an
interaction PR calls out that its evidence is deferred and points at the
harness/interaction-gate tracking issue. Interaction PRs always require a
human eyeball on the frames — auto-merge is off until the video gate ships.

## Video expectations

Deferred until the interaction gate lands. When it does:

- Swami side recorded via `xcrun simctl io recordVideo` against the preview host.
- Origami side recorded via **View → Record** in the Origami app.
- Merged side-by-side with FFmpeg, uploaded as a GitHub Actions artifact, and
  embedded in the sticky-comment thread.

Until that pipeline exists, don't hand-roll a one-off video for a PR. Wait or say
"deferred."

## Learning capture

New rules go where their kind lives. The **knowledge surfaces table** in the
Architecture section of AGENTS.md names each surface (CLAUDE.md, AGENTS.md,
ADRs, skills, PR templates) and what belongs on it. Read that table before you
write a rule down — a rule in the wrong surface is a rule nobody finds.

## Agent factory reference

The agent-factory model — how skills, PR templates, verify.yml, and the reviewer
loop compose — is diagrammed in the Architecture section of AGENTS.md. Read it
before touching the harness or adding a new skill.
