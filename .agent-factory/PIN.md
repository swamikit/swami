# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `a666e2d3788d8360bdfc625fbd3594ed03042a07`
- Previous: `fcd120d0a457304e3add5af2d08ff39dec394f32`.
- Upstream evidence: Reviewer-to-Steward arbitration handoff
  https://github.com/samuelalake/agent-factory/compare/fcd120d0a457304e3add5af2d08ff39dec394f32...a666e2d3788d8360bdfc625fbd3594ed03042a07
- First consumer target: Swami Interaction Drag PR #217. Reviewer now searches
  authenticated delivery history for the latest matching reference digest and
  preserves an explicit, affirmative P1 evidence-arbitration request even when
  the model omitted its companion structured flag. Negated, quoted, unrelated,
  and wrong-severity prose cannot manufacture the reserved routing signal.
- Rollback: revert this pin-bump commit. Confirm `agent-builder.yml`,
  `agent-steward.yml`, `agent-review.yml`, `agent-gate.yml`,
  `provider-tool-smoke.yml`, `publish-builder-delivery.yml`, and `verify.yml`
  return to `fcd120d0a457304e3add5af2d08ff39dec394f32`. Do not partially apply
  this rollback.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
