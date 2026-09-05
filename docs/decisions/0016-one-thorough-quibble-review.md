# ADR-0016: One thorough Quibble review

- Status: Accepted
- Date: 2026-09-05

## Context

The review workflow ran a fast Gemini pre-pass and a deeper Claude pass under
the same Quibble identity. The extra pass produced another summary and another
set of findings before the authoritative review, making the pull request harder
to scan. The pre-pass also depended on provider fallback code whose configured
Gemini model was retired, so it was routinely served by Anthropic instead of
providing the intended cheap, independent read.

The repository already has a second independent reviewer in Codex. Two Quibble
passes did not create two independent authorities; they created two presentations
of one role.

## Decision

Quibble runs one thorough current-head review. It posts a compact summary,
inline findings, a formal verdict, and the existing machine-readable markers
consumed by merge-gate. Codex remains the separate external review.

The Swami workflow uses Anthropic directly for this pass. If that request fails,
the workflow posts the existing failure marker and merge-gate stays pending. It
does not silently substitute another provider. Provider-neutral selection and
fallback policy belong in Agent Factory, where they can be shared and tested
without coupling Swami to a second presentation tier.

## Consequences

- Pull requests get one Quibble summary instead of a fast and deep pair.
- Gemini/OpenRouter review dependencies and the local fallback client are
  removed from Swami.
- A provider outage is visible and fail-closed rather than hidden by fallback.
- Changing provider policy later requires a deliberate Agent Factory contract,
  not another Swami-only reviewer script.
