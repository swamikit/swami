# ADR-0005: The test corpus is Origami's built-in Patterns gallery, graded by category

- Status: Accepted
- Date: 2026-09-03

## Context

Building the parser needs example prototypes to validate against. Hand-authoring them
is slow and biased toward the shapes we already understand. Origami ships a **Patterns
gallery** (Getting Started → Patterns) of canonical, self-contained example prototypes,
already grouped by concept: Interaction, Logic, Animation, Layers, Scroll, Loops,
Utilities. "Touch Origami Example" — our first worked example — was created from the
Touch pattern.

## Decision

Use the **Patterns gallery as the graded test corpus.** It is Origami-authored (an
authoritative ground truth), each pattern is small and self-contained (a clean oracle),
and the categories map directly onto the complexity ladder the parser must climb.

Method:
- **Simple first, complex early.** Bootstrap the parser on tier-1 patterns (Touch,
  simple Transition), then bring in harder tiers (Loops, Scroll, nested Components,
  JavaScript patches) before declaring the core done — a parser trained only on simple
  files overfits to the easy structure.
- The parser must keep passing every lower tier as higher tiers are added (regression net).
- Complexity axes to cover deliberately: patch count, component nesting/instances,
  JS patches, multiple artboards, layout kits, loops/arrays, scroll.

## Acquisition

Prefer reading the pattern `.origami` files directly if Origami ships them inside its
app bundle (`Origami Studio.app/Contents/Resources/…`) — the whole corpus for free.
Otherwise drive Origami to instantiate each pattern and save it into a corpus folder
(e.g. on the SSD), then parse.

## Consequences

- A standing, versioned corpus of `(prototype, oracle values, expected render)` triples.
- Each new pattern ground-truthed adds permanent regression coverage (compounding).
