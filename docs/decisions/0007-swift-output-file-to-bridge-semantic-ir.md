# ADR-0007: Swift output is a spectrum — file handoff now, project-aware bridge later; IR must be semantic-rich

- Status: Accepted
- Date: 2026-09-03

## Context

"How do we deliver the Swift?" is not one decision but a spectrum:

- **File handoff:** emit a clean, self-contained `.swift` the engineer pastes in.
  Decoupled, testable, the right unit for "selection → reviewable chunk" (ADR-0002).
  But context-blind — knows nothing of the target app's design system, naming, existing
  components, or navigation.
- **Project-aware bridge:** read the target Xcode project — design tokens, existing
  views/components, naming conventions, state/navigation patterns — and generate code
  that *fits in* rather than duplicating. The difference between a neat transpiler and
  something usable in a real codebase.

Worked example: Origami's card color is not a raw hex — it is the **named** Origami Core
color "Purple" (`#DD70DF`). File mode hardcodes `Color(hex: "#DD70DF")`. Bridge mode maps
"Origami Core / Purple" onto the app's own `Color.brandPurple` design token.

## Decision

**Start at file handoff; design toward the bridge.** Ship self-contained files first
(provable, shippable). Add project-awareness as a later *backend*, not a rewrite.

**Rule that makes this possible — the IR must preserve SEMANTICS, not just resolved
values.** Store `{ color: "#DD70DF", semanticName: "Purple", palette: "Origami Core" }`,
the named typography style, the component identity, the layout-kit intent — not only the
flattened value. You can always resolve a semantic name to a value; you cannot recover the
name from a value. Flattening early permanently destroys what a project-aware backend needs.

## Consequences

- Codegen has two backends over one semantic IR: (1) self-contained file (resolve
  semantics to literals), (2) project-aware (map semantics to the project's tokens/components).
- Parser work must capture named colors, type styles, and component identity — not just geometry.
