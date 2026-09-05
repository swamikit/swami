# ADR-0016: One thorough Quibble review

- Status: Accepted
- Date: 2026-09-05
- Relates to: PRs [#70](https://github.com/swamikit/swami/pull/70),
  [#71](https://github.com/swamikit/swami/pull/71), and
  [#72](https://github.com/swamikit/swami/pull/72)

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

The fast tier and provider client were introduced directly by PRs #70-72; no
earlier ADR recorded that decision. This ADR is the first durable rationale for
the tier and supersedes the workflow-level choice made in those PRs.

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

## Compatibility evidence

- `scripts/merge-gate.sh` and `scripts/audit-p2s.sh` identify Quibble by its
  machine marker and severity buckets. The summary heading and status label are
  presentation, not parser keys.
- `scripts/test_run_claude_review.py` exercises the remaining formatter through
  the shared summary-only fallback for both blocking and non-blocking findings.
- The deleted fast worker's provider-schema assertion is intentionally not
  copied: Quibble accepts file-less review-meta findings and missing lines, then
  routes them to the unanchored body section. Its partitioning tests cover both
  cases directly.
- `rg -n 'model_client|run-fast-review|run_fast_review|reviewer:fast|GEMINI_API_KEY|OPENROUTER_API_KEY' -g '!docs/**' .`
  returns no matches. Builder and triage call their model runtimes independently.
