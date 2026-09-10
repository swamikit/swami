# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `fcd120d0a457304e3add5af2d08ff39dec394f32`
- Previous: `65ec647c1af331e5126db099f6f37c218c45704c`, which had itself
  consolidated a split state: role callers on
  `c3eed6391a74817210931d40f104e9823a001d14`; evidence publication and
  verification on `e3997588ef4df9eeb0b666537891b9ff905edc29`.
- Upstream evidence: role protocol
  https://github.com/samuelalake/agent-factory/compare/65ec647c1af331e5126db099f6f37c218c45704c...fcd120d0a457304e3add5af2d08ff39dec394f32
- First consumer target: Swami Interaction Drag PR #150. Reviewer and revising
  Builder now authenticate GitHub-native screenshots and extensionless video
  through Builder-authored, exact-head manifests bound to repository, pull
  request, ordered URLs, media types, and SHA-256 digests. Concurrent stale or
  same-head publishers cannot substitute or deadlock the canonical evidence.
- Rollback: revert this pin-bump commit. Confirm `agent-builder.yml`,
  `agent-steward.yml`, `agent-review.yml`, `agent-gate.yml`,
  `provider-tool-smoke.yml`, `publish-builder-delivery.yml`, and `verify.yml`
  return to `65ec647c1af331e5126db099f6f37c218c45704c`. Do not partially apply
  this rollback.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
