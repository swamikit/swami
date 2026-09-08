# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `1f72a5c791c3781dcaa83d92d047e12b6f7fdf00`
- Previous: `aa17556afab5edc49700063570bef6f206545b11`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/aa17556afab5edc49700063570bef6f206545b11...1f72a5c791c3781dcaa83d92d047e12b6f7fdf00
- First consumer: Swami Interaction Drag PR #150, whose next Builder revision
  exercises deterministic current-base evidence regeneration.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
