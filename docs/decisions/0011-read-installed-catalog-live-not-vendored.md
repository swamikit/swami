# ADR-0011: Source the patch catalog from the installed app, live — don't vendor it

- Status: Accepted
- Date: 2026-09-03

## Context

Origami's complete patch catalog is compiled into the app (see CLAUDE.md format facts):
`Origami Studio.app/Contents/Resources/Patches/<system>.origami-system/patches/<id>.diamond/graph`
— 66 composite/system patches as the same FlatBuffers we parse, plus `info.json` manifests,
icons, and `.m4a` SoundKit assets. Primitive patches (Interaction, Transition, Add, Switch,
Pop Animation…) live in the binary, not as `.diamond` files. Concept prose
(`origami.design/documentation/concepts/*`, e.g. ShaderLayer) is **not** in Resources, and the
installed catalog is version-pinned (origami core v1.0.6, iOS v2.1.4 on the dev machine) so it
lacks anything newer than what's installed.

## Decision

1. **Read the catalog live from the installed app; do not vendor it into the repo.**
   - Version-matched: always reflects what the user's Origami actually emits.
   - No redistribution problem: shipping Meta's graphs/sounds/icons in a (to-be-public) repo is
     not OK; a skill that reads the user's *own installed copy* is clean. This is load-bearing
     for the community-sharing goal.
   - Origami-installed is a safe assumption (you can't make/open `.origami` without it).
2. **The skill carries the recipe, not the files:** the catalog path, that graphs are ORGM
   FlatBuffers read by our parser, and which patch to read for a given node.
3. **Web docs are a fallback, not a corpus.** Fetch a patch page on demand only for (a) concept
   prose the app doesn't contain, and (b) patches/layers newer than the installed version. Never
   bulk-crawl.
4. **Fixtures, if copied at all, live in a PRIVATE repo.** CI may need a tiny pinned set of
   `.diamond/graph` files as deterministic parser/codegen inputs (so CI runs without a Mac), but
   because these are Meta's assets they must not go in a public repo — keep them in a private
   fixtures repo/submodule, clearly marked, never the source of truth.

## Consequences

- Helper internals are ported from real graphs (e.g. `origami.Drag` momentum) rather than
  approximated — retires the deferred-physics TODOs from ADR-0009.
- Cloud/CI work uses fixtures or files staged from the device; the skill's live path requires a
  Mac with Origami. Parser must resolve a patch id → its catalog graph path.
- Add a version check: compare `info.json` `version` to fixture provenance; fall back to web when
  a referenced patch is absent from the installed catalog.
