# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `329362a264752e8f56712f004e77571c58ea4098`
- Previous: `11a97b33459d393ef882ef054eaf044911f9522e`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/11a97b33459d393ef882ef054eaf044911f9522e...329362a264752e8f56712f004e77571c58ea4098
- First consumer: Swami PR #111, whose next Builder revision exercises current-base conflict handling.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
