# ADR-0006: Headless first; the first UI is selection capture, not a codegen studio

- Status: Accepted
- Date: 2026-09-03

## Context

Tempting to build a tool UI early. But a UI wrapped around an engine that still
produces wrong output is a prettier way to ship wrong output.

## Decision

**Build headless first.** Parser + IR + codegen as a CLI/library, proven against the
graded corpus (ADR-0005), until the core reliably produces good SwiftUI across a range
of prototypes.

**Trigger to build UI (both must hold):**
1. The headless pipeline is trustworthy on the corpus, AND
2. The selection-capture need is real (ADR-0003) — a designer pointing at a selection
   and getting a reviewable chunk back.

**The first UI's job is selection capture, not codegen display.** The thin menu-bar
companion reads Origami's live selection (Accessibility hook) and shows/diffs the
output. Richer UI — including the side-by-side visual diff from ADR-0004 — comes after.

## Sequence

parser solid on corpus → codegen good → thin selection-capture UI → visual-diff UI.

## Consequences

- Effort stays on the engine while it's unreliable; UI arrives when it removes a real
  bottleneck (selection capture) rather than as decoration.
