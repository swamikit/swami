# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `4873638d28b6746aca1ca03eb2562c1272a18c9d`
- Previous: `57381f903da08ad8935429046423516a8d0d09ef`
- Upstream evidence: https://github.com/samuelalake/agent-factory/compare/cf28b0fb011e84c2eda85b3d6a7da7222962691e...4873638d28b6746aca1ca03eb2562c1272a18c9d
- First consumer target: Swami Interaction Drag PR #150. This pin configures
  Reviewer to require authenticated current-head evidence for Swami app and
  Origami changes, including failed deterministic evidence. Runtime observation
  on the default-branch event path begins after this pin lands.
- Rollback: revert the pin-bump commit so all five workflow references return to
  the previous SHA atomically.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
