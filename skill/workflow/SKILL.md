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
   stakes; the pixel gate is the real one.
4. **Ship** — squash-merge with a PR body a human can read months later.

The beat vocabulary comes from AGENTS.md's methodology section. If a PR skips a
beat, say so and say why.

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
template and pass it with `--template=<name>`:

- `pattern.md` — a pattern translation PR (Origami example → SwiftUI).
- `helper.md` — a reusable Swift helper (`drag()`, `sample()`, etc.).
- `parser.md` — parser or IR change.
- `harness.md` — verify.yml, runner, evidence tooling.
- `docs.md` — ADRs, README, methodology docs.
- `fix.md` — bug fix or regression.

If none fits and this PR shape has appeared before, **propose a new template** in
a doc/methodology follow-up — don't quietly force it into the closest one. If it
is truly one-off, use `fix.md` and describe freely; the freeform template exists
for exactly that.

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
sticky-comment side-by-side (swami / Origami / diff). Nothing merges on a green
pixel gate alone; a human looks at the images.

Interaction-gated PRs — Touch, Drag, Scroll, anything the user drives — will also
get an MP4 side-by-side once the interaction gate lands. Until then, an
interaction PR calls out that its evidence is deferred and points at the
harness/interaction-gate tracking issue.

Never accept a green gate without eyeballing the frames. A green gate that shows
the wrong pattern is worse than a red one.

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
