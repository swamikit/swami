# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `d4c7299d93181d67d6af23664f324d3e140be479`
- Previous: `329362a264752e8f56712f004e77571c58ea4098`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/329362a264752e8f56712f004e77571c58ea4098...d4c7299d93181d67d6af23664f324d3e140be479
- First consumer: Swami PR #111, whose next Builder revision exercises protected-path reconciliation.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
