# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `001eecfa14680de5c25040513bb92b7df5e0d596`
- Previous: `d4c7299d93181d67d6af23664f324d3e140be479`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/d4c7299d93181d67d6af23664f324d3e140be479...001eecfa14680de5c25040513bb92b7df5e0d596
- First consumer: Swami PR #111, whose next Builder revision exercises protected-path reconciliation.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
