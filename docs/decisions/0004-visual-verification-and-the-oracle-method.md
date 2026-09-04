# ADR-0004: Visual verification is the fidelity gate; the graph is the source of truth

- Status: Accepted
- Date: 2026-09-03

## Context

The first codegen of Touch Origami Example compiled, passed a tree-sitter syntax
parse, and mapped every patch — and was still visibly wrong: it emitted `Ellipse()`
on a gray background where Origami renders rounded-rectangle cards on magenta, and it
scaled the whole card where Origami grows a hidden 100×100 circle inside it. Textual
and structural checks could not see any of that.

## Decision

1. **Fidelity is a visual property.** The correctness gate for a translation is
   "render the SwiftUI and diff it against the Origami render," not textual diff or
   compile-success. Compile-clean is necessary, not sufficient.

2. **The graph is the source of truth for VALUES.** Sizes, colors, corner radii,
   spacing, positions, and wiring must be read from the `.origami` document by the
   parser — never eyeballed from a screenshot. Reading a value off the Origami
   Inspector is an **oracle / answer-key**, used to (a) hit exact fidelity today and
   (b) validate the parser, but it is NOT the method. The product is the parser
   reproducing those values from the bytes.

3. **Visual checking keeps a narrower, permanent job:** the things the graph can't
   cheaply tell you — does the interaction *feel* right, does the result *look* right
   (catching mapping bugs). Interaction + appearance validation, not value sourcing.

## Consequences

- Every ground-truthed prototype becomes a permanent test case (values + expected
  render). The oracle set compounds; the visual crutch shrinks as the parser grows.
- Worked example: the "magenta" is Origami Core **"Purple"** = `#DD70DF` (RGB 221,112,223),
  read from the picker — an exact answer the parser must reproduce.
- The verification loop is: parse → generate → render → visual-diff vs Origami →
  adjust → repeat. Visual diff is the loop's scoring function.
