# Interaction Drag

`Interaction_Drag` is the faithful SwiftUI rendering of the Origami drag pattern.
It uses the exact 888×1212 artboard framing, centered 220×140 rounded card, tan card
fill, and full-bleed presentation required by the runner evidence for issue #140.

## Behavior

- Press and drag the card with touch or pointer input.
- Motion is bounded within the artboard with rubber-band resistance while dragging.
- Release settles the card with momentum-aware spring animation.
- A fresh appearance resets the card to the centered resting position.

## Evidence

This page is bound to the current head and is intended to render useful content,
not an empty shell. See the Builder sticky comment for the Swami / Origami / diff
image triplet and the H.264 interaction recording from the GitHub macOS runner.
