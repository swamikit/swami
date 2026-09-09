# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `ac8e3e45e953149e55ec4d87a5606e31edbe8369`
- Previous: `a08460356ec152cba4b4290089256da8394a09ae`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/a08460356ec152cba4b4290089256da8394a09ae...ac8e3e45e953149e55ec4d87a5606e31edbe8369
- First consumer target: Swami Interaction Drag PR #150. This pin configures
  Reviewer to require authenticated current-head evidence for Swami app and
  Origami changes, including failed deterministic evidence. Builder revisions
  now receive the authenticated exact-head Reviewer's inline findings as well
  as its summary and visual evidence, and fail closed rather than truncating an
  oversized review brief. OpenRouter Builder requests now also constrain
  endpoint pricing to the configured cost estimate before a provider can serve
  the request.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
