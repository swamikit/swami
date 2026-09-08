# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `57381f903da08ad8935429046423516a8d0d09ef`
- Previous: `f109e8800a3e07389bb65c14e2566786f9386ec9`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/f109e8800a3e07389bb65c14e2566786f9386ec9...57381f903da08ad8935429046423516a8d0d09ef
- First consumer target: Swami Interaction Drag PR #150. This pin configures
  Reviewer to require authenticated current-head evidence for Swami app and
  Origami changes, including failed deterministic evidence. Runtime observation
  on the default-branch event path begins after this pin lands.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
