# ADR-0008: Opt-in usage capture, baked into v1 — CLI-native consent, no UI required

- Status: Accepted
- Date: 2026-09-03

## Context

The tool improves fastest from real usage: prototypes that fail or map badly, and — the
gold signal — user *corrections* (tool emitted X, user changed it to Y), which are labeled
`(prototype → good SwiftUI)` pairs. But prototypes are the user's IP. Silent harvesting
would kill trust in a small community (ADR-0005 corpus, community sharing). And v1 is
headless-first (ADR-0006), so consent can't rely on a UI.

## Decision

Bake an **opt-in, CLI-native** capture path into v1. No UI needed — consent is expressed
the way CLI tools already express it:

1. **Private by default.** With no opt-in, the tool collects and sends nothing.
2. **Explicit opt-in**, any of: a `--contribute` run flag, a persisted config
   (`swami config set contribute true`), or a first-run terminal Y/N prompt. Never on by default.
3. **Local-first.** Contributions are written to a local `contributions/` folder the user
   can open, inspect, and redact. Nothing leaves the machine on its own; upload/submit is a
   *separate, explicit* action (`swami contribute submit`).
4. **Minimal payload.** Capture the parsed **graph IR** (structure) and the user's
   **correction diff** — not raw visual assets or copy, unless separately opted in. Prefer
   the smallest thing that improves the parser/mapping.
5. **Transparent + reversible.** The tool states exactly what a contribution contains, and
   opt-out is one flag/config away; per-run override always wins.

## Consequences

- The feedback loop reads as a feature ("help improve the tool") rather than surveillance.
- Contributions feed the oracle corpus and the mapping skill (ADR-0004/0005); the verify
  harness makes their impact measurable. ML fine-tuning is a later, data-gated phase — this
  ADR is about capturing the data ethically now, regardless of how it's later used.
- Because it's config/flag-based, it works identically in headless, CI, and (future) UI modes.
