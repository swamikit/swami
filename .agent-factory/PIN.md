# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `0ecbb8cd82eee9b626e44f0f9a4bd15040edd24a`
- Previous: `4cedf7986466993db55a62ba3da69debe09170c9`.
- Upstream evidence: least-privilege Steward arbitration publication
  https://github.com/samuelalake/agent-factory/compare/4cedf7986466993db55a62ba3da69debe09170c9...0ecbb8cd82eee9b626e44f0f9a4bd15040edd24a
- First consumer target: Swami Interaction Drag PR #217. Steward's short-lived
  arbitration token now has repository contents read and pull-request write,
  which permits the authenticated PR timeline ruling without granting contents
  write or merge authority.
- Rollback: revert this pin-bump commit. Confirm `agent-builder.yml`,
  `agent-steward.yml`, `agent-review.yml`, `agent-gate.yml`,
  `provider-tool-smoke.yml`, `publish-builder-delivery.yml`, and `verify.yml`
  return to `4cedf7986466993db55a62ba3da69debe09170c9`. Do not partially apply
  this rollback.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
