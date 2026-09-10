# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `4cedf7986466993db55a62ba3da69debe09170c9`
- Previous: `a666e2d3788d8360bdfc625fbd3594ed03042a07`.
- Upstream evidence: sticky, reauthenticated Reviewer-to-Steward arbitration
  https://github.com/samuelalake/agent-factory/compare/a666e2d3788d8360bdfc625fbd3594ed03042a07...4cedf7986466993db55a62ba3da69debe09170c9
- First consumer target: Swami Interaction Drag PR #217. Unresolved structured
  conflicts remain sticky for the same head. Legacy affirmative P1 handoff
  prose is accepted only with authenticated same-reference Builder and Reviewer
  continuity. Head, evidence binding, history, and Reviewer state are all
  reauthenticated before Steward can publish a ruling.
- Rollback: revert this pin-bump commit. Confirm `agent-builder.yml`,
  `agent-steward.yml`, `agent-review.yml`, `agent-gate.yml`,
  `provider-tool-smoke.yml`, `publish-builder-delivery.yml`, and `verify.yml`
  return to `a666e2d3788d8360bdfc625fbd3594ed03042a07`. Do not partially apply
  this rollback.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
