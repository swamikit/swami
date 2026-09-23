# Agent Factory pin

Swami's Steward, Builder, Reviewer, Gate, and integration workflows must use the
same immutable Agent Factory commit.

- Current: `9fd45842a57d26b184725f0f73d119f398eebd7a`
- Previous: `0ecbb8cd82eee9b626e44f0f9a4bd15040edd24a` (steward caller lagged at
  `5cd18eb89a0d51aefa1f871f7d701e030ca09606`; this bump realigns every workflow
  onto one commit).
- Upstream evidence:
  https://github.com/samuelalake/agent-factory/compare/0ecbb8cd82eee9b626e44f0f9a4bd15040edd24a...9fd45842a57d26b184725f0f73d119f398eebd7a
- Substance of this bump: the Builder now runs on the Claude Pro/Max
  subscription. Agent Factory `9fd4584` (PR #79) adds a `claude-code` agentic
  Builder harness that runs the pinned Claude Code CLI headless in edit mode,
  leaving working-tree changes for the existing publication path — the same
  contract the Gemini and OpenAI-compatible harnesses use.
- Consumer config change accompanying this bump: `.agent-factory/config.json`
  `builder` moves to `provider: claude-code` / `harness: claude-code` /
  `model: claude-opus-4-8`. `visual_revision_context` and
  `fallback_visual_revision_context` are set to `false` because the
  subscription harness is text-only. The `openrouter` fallback pair is
  unchanged, and `agent-builder.yml` now forwards `CLAUDE_CODE_OAUTH_TOKEN`.
  This is a targeted Builder flip; the Reviewer and other `development`-only
  settings are intentionally left as they are on this branch.
- Rollback: revert this pin-bump commit. Confirm `agent-builder.yml`,
  `agent-steward.yml`, `agent-review.yml`, `agent-gate.yml`,
  `provider-tool-smoke.yml`, `publish-builder-delivery.yml`, and `verify.yml`
  return to `0ecbb8cd82eee9b626e44f0f9a4bd15040edd24a` (steward to
  `5cd18eb89a0d51aefa1f871f7d701e030ca09606`); confirm
  `.agent-factory/config.json` `builder` returns to `openrouter` /
  `openai-compatible` / `openai/gpt-6-astra` with
  `visual_revision_context`/`fallback_visual_revision_context` `true`; and
  remove the `CLAUDE_CODE_OAUTH_TOKEN` secret added to `agent-builder.yml`. Do
  not partially apply this rollback.

Update this record with every Factory pin change so the behavior and rollback
remain inspectable from Swami's history.
