# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `451fb7683249376ad5fb5a01e04ce09f5c200279`
- Previous: `1fdf9a96a6ff394231ecd5a609ea4e664cbb3adc`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/1fdf9a96a6ff394231ecd5a609ea4e664cbb3adc...451fb7683249376ad5fb5a01e04ce09f5c200279
- First consumer: Swami Interaction Drag PR #150, whose next Builder revision
  receives its rejected-head Swami, Origami, and diff images through bounded,
  authenticated visual context.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
