# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `5b450d9f419345a7eb79f3a0ff619f88ce0ec757`
- Previous: `1f72a5c791c3781dcaa83d92d047e12b6f7fdf00`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/1f72a5c791c3781dcaa83d92d047e12b6f7fdf00...5b450d9f419345a7eb79f3a0ff619f88ce0ec757
- First consumer: Swami Interaction Drag PR #150, whose next Builder revision
  receives its rejected-head Swami, Origami, and diff images through bounded,
  authenticated visual context.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
