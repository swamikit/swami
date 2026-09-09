# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `8c92c353a3d36b71ea36e278953da656ccc6c905`
- Previous: `ac8e3e45e953149e55ec4d87a5606e31edbe8369`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/ac8e3e45e953149e55ec4d87a5606e31edbe8369...8c92c353a3d36b71ea36e278953da656ccc6c905
- First consumer: Swami Interaction Drag PR #150. Reviewer now inspects its
  authenticated current-head Swami, Origami, and diff images whether the
  deterministic sanity check passes or fails, while Builder receives the
  resulting visual diagnosis on revision. Builder revisions now also receive
  the authenticated exact-head Reviewer's eligible inline findings and fail
  closed rather than truncating an oversized review brief. OpenRouter Builder
  requests now constrain endpoint prices, enforce reported billed cost after
  every response, and share one $1 budget across primary and fallback attempts.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
