# skill — IR → SwiftUI translation

The judgment half of the project: a skill that reads the IR plus the Origami and
SwiftUI docs and the mapping rules, and emits idiomatic SwiftUI for the user's
selection.

**Not built yet.** Codify the mapping table and hard-cases from `CLAUDE.md`
(`NEXT_STEPS.md` step 5). Principles:

- Map to SwiftUI's **state graph**, not to free functions (the dataflow thesis).
- Scope output to the selection; use the whole-file IR as context (ADR 0002).
- **Flag, don't fake** the hard cases (continuous springs, custom JS patches, cyclic
  dataflow, absolute layout).
- Use `examples/` as worked-examples that steer translation.
