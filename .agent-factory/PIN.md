# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `1e667cad232b86b03d93ca7be68187b73bd543e6`
- Previous: `ced51f6c8f67b69080125cfb21f712c9b9a1ef1d`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/ced51f6c8f67b69080125cfb21f712c9b9a1ef1d...1e667cad232b86b03d93ca7be68187b73bd543e6
- First consumer target: Swami Interaction Drag PR #150. This pin configures
  Reviewer to require authenticated current-head evidence for Swami app and
  Origami changes, including failed deterministic evidence. Runtime observation
  on the default-branch event path begins after this pin lands.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
