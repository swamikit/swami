# New pattern

One `.origami` → one generated view → one PR (AGENTS.md Beat 1: Isolate).

## Pattern
- **Name:**
- **`.origami` source URL:**
- **Primary Origami patch(es):**
- **Helpers touched (new / existing):**

## Structural check
- [ ] Ports match the mirrored patch (names + directions)
- [ ] Native SwiftUI used where it covers the patch; helper justified where it doesn't
- [ ] Generated Swift passes the tree-sitter pre-gate (Beat 2)
- [ ] IR preserves semantic names (colors, type styles, patch labels) per ADR-0007

## Verify evidence
- [ ] Sticky comment link (swami / origami / diff side-by-side, Beat 3):
- [ ] `BACKLOG.md` entry resolved on merge (Beat 4)
