# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `ac8e3e45e953149e55ec4d87a5606e31edbe8369`
- Previous: `a08460356ec152cba4b4290089256da8394a09ae`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/a08460356ec152cba4b4290089256da8394a09ae...ac8e3e45e953149e55ec4d87a5606e31edbe8369
- First consumer: Swami Interaction Drag PR #150. Reviewer now inspects its
  authenticated current-head Swami, Origami, and diff images whether the
  deterministic sanity check passes or fails, while Builder receives the
  resulting visual diagnosis on revision. Builder revisions now also receive
  the authenticated exact-head Reviewer's eligible inline findings and fail
  closed rather than truncating an oversized review brief. OpenRouter Builder
  requests now constrain endpoint prices to the same conservative rates used
  for the cumulative $1 estimate.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
