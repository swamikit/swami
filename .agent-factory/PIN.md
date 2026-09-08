# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `1e0d83f8a673e5477b2dabaf644dd2aee81d170c`
- Previous: `d74be452b38e6d86891bf666b52b98a84c9f7281`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/d74be452b38e6d86891bf666b52b98a84c9f7281...1e0d83f8a673e5477b2dabaf644dd2aee81d170c
- First consumer: Swami Interaction Drag PR #150, whose next Builder revision
  exercises deterministic current-base evidence regeneration.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
