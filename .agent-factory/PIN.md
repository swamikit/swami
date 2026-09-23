# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `9fd45842a57d26b184725f0f73d119f398eebd7a`
- Previous: `4a65843726c4bd4ddc7191e2204d85d6b7d03374` (all role callers,
  `provider-tool-smoke.yml`, `publish-builder-delivery.yml`, and `verify.yml`
  shared this commit).
- Upstream evidence:
  https://github.com/samuelalake/agent-factory/compare/4a65843726c4bd4ddc7191e2204d85d6b7d03374...9fd45842a57d26b184725f0f73d119f398eebd7a
- Substance of this bump: the Builder now runs on the Claude Pro/Max
  subscription. Agent Factory `9fd4584` (PR #79) adds a `claude-code` agentic
  Builder harness that runs the pinned Claude Code CLI headless in edit mode,
  leaving working-tree changes for the existing publication path — the same
  contract the Gemini and OpenAI-compatible harnesses use. This is the Builder
  half of "Claude behind the loop": the Reviewer already ran on `claude-code`
  since `4a65843`, so `issue → Builder → PR → Reviewer → merge` now runs on the
  subscription. Only `builder.yml` and the Python package changed between the
  two commits; every other reusable workflow Swami calls is byte-identical.
- Consumer config change accompanying this bump: `.agent-factory/config.json`
  `builder` moves from `provider: minimax` / `harness: openai-compatible` /
  `model: MiniMax-M2.7` to `provider: claude-code` / `harness: claude-code` /
  `model: claude-opus-4-8`. The `openrouter` fallback pair is unchanged, and
  `agent-builder.yml` now forwards `CLAUDE_CODE_OAUTH_TOKEN`.
- Rollback: revert this pin-bump commit. Confirm `agent-builder.yml`,
  `agent-steward.yml`, `agent-review.yml`, `agent-gate.yml`,
  `provider-tool-smoke.yml`, `publish-builder-delivery.yml`, and `verify.yml`
  return to `4a65843726c4bd4ddc7191e2204d85d6b7d03374`; confirm
  `.agent-factory/config.json` `builder` returns to `minimax` /
  `openai-compatible` / `MiniMax-M2.7`; and remove the `CLAUDE_CODE_OAUTH_TOKEN`
  secret added to `agent-builder.yml`. Do not partially apply this rollback.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
