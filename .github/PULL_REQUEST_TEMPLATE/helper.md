# New helper

Native-first per ADR-0009 — add a helper only when SwiftUI doesn't already cover the patch.

## Helper
- **Name:**
- **Origami patch mirrored:**
- **Standalone or paired with a pattern PR:**

## Ports mapped
| Origami port | Direction | Swift signature |
|---|---|---|
|  | in / out |  |

## Native-first justification
- Why SwiftUI's built-ins don't cover this:
- What breaks / gets approximated without the helper:

## Example usage
```swift
// minimal call site the generator will emit
```

## Checks
- [ ] Port names match the composite `.diamond/graph` (not just the web docs)
- [ ] tree-sitter pre-gate passes on `Sources/Swami/*.swift` (Beat 2)
