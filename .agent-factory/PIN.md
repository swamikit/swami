# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `8c92c353a3d36b71ea36e278953da656ccc6c905`
- Previous: `ac8e3e45e953149e55ec4d87a5606e31edbe8369`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/ac8e3e45e953149e55ec4d87a5606e31edbe8369...8c92c353a3d36b71ea36e278953da656ccc6c905
- First consumer target: Swami Interaction Drag PR #150. This pin configures
  Reviewer to require authenticated current-head evidence for Swami app and
  Origami changes, including failed deterministic evidence. Builder revisions
  now receive the authenticated exact-head Reviewer's inline findings as well
  as its summary and visual evidence, and fail closed rather than truncating an
  oversized review brief. OpenRouter Builder requests now also constrain
  endpoint pricing before a provider can serve the request, enforce reported
  billed cost after each response, and share one budget across primary and
  fallback attempts.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
