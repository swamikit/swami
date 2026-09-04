# skill — verified-delivery notes + adopted skills

Two things live here:

1. **Notes on the swami-specific skill** we're building (the IR → SwiftUI translator
   half — the "judgment" side of the project).
2. **Adopted skills** vendored from external repos when their shape fits our loop.

## The swami skill (not built yet)

A skill that reads the IR plus the Origami and SwiftUI docs and the mapping rules,
and emits idiomatic SwiftUI for the user's selection. Codify the mapping table and
hard-cases from `CLAUDE.md` (`NEXT_STEPS.md` step 5). Principles:

- Map to SwiftUI's **state graph**, not to free functions (the dataflow thesis).
- Scope output to the selection; use the whole-file IR as context (ADR 0002).
- **Flag, don't fake** the hard cases (continuous springs, custom JS patches, cyclic
  dataflow, absolute layout).
- Use `examples/` as worked-examples that steer translation.

## Adopted skills

- **`unslop/`** — cuts AI tells from anything a human will read. Vendored from
  [michaelshimeles/skills](https://github.com/michaelshimeles/skills) (MIT, © Lauren Tan;
  see `unslop/LICENSE`). Run before every commit message, PR body, ADR, or NEEDS-VERIFY entry.

## Prior art worth tracking

- [michaelshimeles/skills](https://github.com/michaelshimeles/skills) — same
  "evidence or it didn't happen" instinct as verified-delivery, packaged as a
  four-beat spine (Isolate → Build → Prove → Ship). AGENTS.md borrows the beat
  names; the `evidence-driven-testing` MPEG-TS-durable ffmpeg recorder is worth
  porting to the macOS runner once the pixel gate is live (interaction-driven
  patterns like Touch need video, not just a static shot).
