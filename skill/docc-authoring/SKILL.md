---
name: docc-authoring
description: Swami DocC house style — which directives we use, sample-code page shape, gallery shape, naming conventions, resource organization. Load when writing anything under app/Swami/Swami.docc/.
metadata:
  type: procedural
---

# DocC authoring — Swami house style

Rules for anything written under `app/Swami/Swami.docc/`. Directives, page shapes,
file layout. Keep pages boring and consistent — the design lives in the pattern renders,
not in prose.

## Directives we use

Only these. If you reach for something else, stop and check first.

### `@Metadata { … }`

Page-level config wrapper. Everything below sits inside it.

```markdown
@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Touch")
    @CallToAction(url: "https://…/Interaction_Touch.zip", purpose: download, label: "Download")
}
```

### `@PageKind(article)` / `@PageKind(sampleCode)`

Page classification. `sampleCode` gives the page the sample-code chrome (download
button slot, code-forward layout).

**Caveat:** `@PageKind(sampleCode)` on a Swift *symbol* doc-comment has been
inconsistent in earlier PRs — it sometimes renders as an article regardless.
When you need `sampleCode` layout, author a **standalone `.md` file**, not a
symbol comment. Article pages take `@PageKind(article)` and work reliably in
both places.

### `@PageImage(purpose: card, source: "<name>")`

Preview image for gallery cards. `<name>` is the resource basename (no
extension). Ships from `Resources/Patterns/<name>.png`.

### `@CallToAction(url: "<zip-url>", purpose: download, label: "Download")`

Download button on a pattern page. `url` points at the Xcode-project zip we
publish alongside the site.

### `@Links(visualStyle: detailedGrid)`

Content-aware gallery cards. Give it a list of page links; each card pulls its
preview from the linked page's own `@PageImage`. Do not hand-build the grid.

```markdown
@Links(visualStyle: detailedGrid) {
    - <doc:Interaction_Touch>
    - <doc:Interaction_Drag>
}
```

### `@TabNavigator`

Category grouping on gallery pages. One tab per Origami sidebar category
(Featured, Interaction, Layer, …).

```markdown
@TabNavigator {
    @Tab("Interaction") {
        @Links(visualStyle: detailedGrid) {
            - <doc:Interaction_Touch>
            - <doc:Interaction_Drag>
        }
    }
    @Tab("Layer") {
        @Links(visualStyle: detailedGrid) {
            - <doc:Layer_Frame>
        }
    }
}
```

### `@Row` / `@Column`

Finer layout only when `@Links` doesn't fit — for example, mixing prose with a
single preview. Never use these to build the gallery.

## File and resource conventions

- **Sample-code pages**: `app/Swami/Swami.docc/Patterns/<Interaction_Touch>.md`.
  One file per pattern. Filename = pattern ID = image basename = doc link.
- **Preview images**: `app/Swami/Swami.docc/Resources/Patterns/<Interaction_Touch>.png`.
  Same basename as the `.md`. Ships inside the DocC archive.
- **Framework symbol docs**: `///` comments in Swift source. DocC auto-generates
  the symbol pages. Do not shadow them with hand-written articles.
- **Collection pages**: `app/Swami/Swami.docc/<Collection>.md`. One article per
  Origami sidebar category (Animation, Interaction, Layer, …). These are the
  gallery pages that host `@TabNavigator` + `@Links`.

## Mapping tables

On each collection page, ship a **GFM table** mapping Origami patches to their
SwiftUI equivalents. Not `@Links` — a real table. One row per patch.

```markdown
| Origami patch                     | SwiftUI                              |
|-----------------------------------|--------------------------------------|
| `interaction.tap` — Tap           | ``onTap(_:)`` (native)               |
| `interaction.drag` — Drag         | ``drag(position:enable:)`` (helper)  |
| `layer.oval` — Oval               | `Circle()` (native)                  |
```

Symbol references go in double backticks so DocC auto-links them. Mark each
right-hand cell `(native)` or `(helper)` so readers know whether it's stock
SwiftUI or one of ours.

## Sample-code page shape

Image + code + minimal context. That is the whole page.

```markdown
# Interaction — Touch

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "Interaction_Touch")
    @CallToAction(url: "https://patterns.swami.dev/downloads/Interaction_Touch.zip", purpose: download, label: "Download")
}

Tap the card to grow the hidden oval inside it. Uses ``onTap(_:)`` with a
`withAnimation(.easeInOut(duration: 0.5))` block to interpolate the scale.

```swift
struct InteractionTouch: View {
    @State private var pressed = false

    var body: some View {
        ZStack {
            Circle()
                .fill(Color(hex: 0xDD70DF))
                .frame(width: 100, height: 100)
                .scaleEffect(pressed ? 5 : 0)
        }
        .frame(width: 300, height: 300)
        .background(.white)
        .cornerRadius(20)
        .onTap { pressed.toggle() }
        .animation(.easeInOut(duration: 0.5), value: pressed)
    }
}
```
```

## Gallery article shape

`@TabNavigator` around one tab per category, `@Links(visualStyle: detailedGrid)`
inside each. No hand-authored prose per card.

```markdown
# Patterns

@Metadata {
    @PageKind(article)
    @PageImage(purpose: card, source: "Gallery")
}

Every Origami pattern, ported to SwiftUI.

@TabNavigator {
    @Tab("Featured") {
        @Links(visualStyle: detailedGrid) {
            - <doc:Interaction_Touch>
            - <doc:Interaction_Drag>
            - <doc:Layer_Frame>
        }
    }
    @Tab("Interaction") {
        @Links(visualStyle: detailedGrid) {
            - <doc:Interaction_Touch>
            - <doc:Interaction_Drag>
            - <doc:Interaction_DoubleTap>
            - <doc:Interaction_LongPress>
        }
    }
    @Tab("Layer") {
        @Links(visualStyle: detailedGrid) {
            - <doc:Layer_Frame>
            - <doc:Layer_Oval>
        }
    }
}
```

## What not to do

- **No per-pattern prose articles.** Sample-code pages are image + code +
  minimal context. If you catch yourself writing a walkthrough, delete it — the
  code and the render are the walkthrough.
- **No `@Row`/`@Column` for the gallery.** `@Links` auto-cards from
  `@PageImage` metadata. Rows and columns are for one-off layouts, not the
  main grid.
- **No hand-added binaries.** `Resources/Patterns/*.png` come from
  CI-composited renders. Don't drop a hand-cropped screenshot in and commit it
  — regenerate through the render pipeline so the image matches the code.
