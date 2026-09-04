# ADR-0013: Runner installs Origami per run and renders live — supersedes ADR-0012

- Status: Accepted
- Date: 2026-09-04
- Supersedes: ADR-0012

## Context

ADR-0012 said cache Origami's rendered references in `swami-private`, CI diffs
against them. That worked (60/62 rendered locally, script at
`swami-private/scripts/render-references.sh`). But a 2026-09-04 spike proved the
GHA macos-15 runner can just install Origami from its Sparkle appcast (~12s
end-to-end) and drive it directly via osascript — no TCC dialog on the fresh
runner image, no accessibility-permission prompt.

That collapses three things:

1. No cross-repo dependency — no fetch from `swami-private`, no `REFERENCES_TOKEN`
   secret to set up and maintain.
2. References are always current for whatever Origami version the runner just
   installed — no cache-invalidation race when Origami ships a point release.
3. Parser verification via Origami's Inspector (AXAttributes) and interaction
   verification (drive a gesture on Origami's live viewer, capture response)
   become possible from the same runner substrate — big future unlocks for the
   ISAT-style verification the loop needs.

## Decision

1. **Runner installs Origami per run.** Fetch DMG URL from
   `https://www.facebook.com/mobile_builds/appcast.xml?app_id=892075810923571&flavor=production`,
   install to `/Applications/`, `lsregister -f -R`, strip quarantine attributes so
   Gatekeeper doesn't block the first launch.
2. **Fetch each pattern's `.origami` from origami.design directly.** Public URLs
   at `https://origami.design/public/origami_files/patterns/<Name>.origami`. No
   `swami-private` hop needed for the runner. The `swami-private/patterns/`
   corpus stays as a local working copy for the Mac side.
3. **Per pattern: render both sides in one loop.** Open the `.origami` file in
   Origami, trigger `View → Take Screenshot` via osascript, save the resulting
   PNG; launch SwamiHost with `SWAMI_PATTERN=<slug>`, screenshot the sim; SSIM
   compare. Threshold 0.95 = ✅.
4. **Push evidence to a `ci-screenshots` branch** — three files per pattern
   (swami, origami, diff), sticky PR comment embeds them side by side via
   `raw.githubusercontent.com` URLs (public repo → works without auth).
5. **Delete `swami-private/references/`** once Path B lands. The renderer
   script stays — still useful for local Mac-side troubleshooting — but the
   cached PNG set becomes dead weight the moment the runner produces its own.

## Consequences

- ADR-0012 is superseded. Its NEEDS-VERIFY bootstrap items move to done (renderer
  script + first 60 references were valuable proof; the artifact itself is gone).
- `REFERENCES_TOKEN` secret is not needed. Do not create it.
- CI run time grows by ~12s (install Origami) + ~15–20s per pattern (Origami
  open + render + close). For the 62-pattern corpus that's ~20–25 min per full
  run. Acceptable.
- Enables two follow-up ADRs, both now on a shared substrate:
  - **Parser verification via Origami Inspector** — osascript reads AX attributes
    of the Inspector panel (layer height, corner radius, position) and checks
    them against the parser's IR.
  - **Interaction gate** — drive a gesture on both Origami and SwamiHost, screenshot
    the response, diff.
