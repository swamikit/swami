# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `1fdf9a96a6ff394231ecd5a609ea4e664cbb3adc`
- Previous: `5b450d9f419345a7eb79f3a0ff619f88ce0ec757`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/5b450d9f419345a7eb79f3a0ff619f88ce0ec757...1fdf9a96a6ff394231ecd5a609ea4e664cbb3adc
- First consumer: Swami Interaction Drag PR #150, whose next Builder revision
  receives its rejected-head Swami, Origami, and diff images through bounded,
  authenticated visual context.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
