---
name: docc-authoring
description: Everything the DocC surface for a translated pattern needs. The emitted `.swift` file's shape (filename, struct, symbol-comment header, public API, verification-host switch) AND the DocC catalog conventions that receive it (directive whitelist, collection/gallery page shape, `Resources/Patterns/<PatternID>.png` basename contract, GFM patch→SwiftUI mapping table). Community-portable, sibling to `skill/pattern-translation`. Load whenever you're about to write a pattern's `.swift` file, a catalog page, or a mapping-table row.
metadata:
  type: procedural
---

# DocC authoring: pattern file + catalog surface

Sibling to `skill/pattern-translation`. That skill decides *what* the SwiftUI
looks like (patch-to-construct mapping, ISAT staging, native-first). This skill
decides *what reaches the reader*: the pattern file on disk (filename, struct,
symbol-comment DocC header, public API, verification-host switch) and the DocC
catalog that renders it (directives, gallery shape, resource naming, patch→SwiftUI
mapping table).

Repo-specific details (env var names, workflow filenames, `sed`/`tr` slug
derivation) are marked as the reference project's — community ports mirror the
shape, not the identifiers. No PR flow, no issue numbers.

## One file per pattern

- **One `.swift` file per Origami pattern.** No shared multi-pattern files, no
  helper spillover into a pattern file (helpers live in the Swami module).
- **Filename = the Origami source stem.** `Interaction_Touch.origami` becomes
  `Interaction_Touch.swift`. Category prefix and underscore separator preserved
  from the source; do not rename, re-case, or resegment.
- **Location.** In the reference project, pattern files sit in the same module
  the Swami helpers ship from. Community ports place them wherever the
  module's public sources live.

## Struct shape

```swift
public struct <PatternID>View: View {
    public init() {}
    public var body: some View {
        // single expression; the artboard's layer tree, translated
    }
}
```

- **`PatternID`** = the Origami source stem, verbatim. `Interaction_Touch.origami`
  produces `public struct Interaction_TouchView`. Keep the underscore. The 1:1
  mapping from Origami's filename to the Swift type is deliberate; readers use
  it to find one from the other.
- **`View` suffix.** Every pattern struct ends in `View`. `Interaction_TouchView`,
  not `Interaction_Touch`. The suffix disambiguates from Swami helpers that
  share a patch name (`Interaction` the helper vs. `Interaction_TouchView` the
  pattern).
- **`public`.** The struct and its `init()` are public. A pattern that can't be
  instantiated from outside the module can't be verified by the host and can't
  be embedded from a downstream DocC.
- **Single-expression body.** The body renders the Origami artboard and nothing
  else. No `NavigationStack`, no `NavigationView`, no toolbar, no debug HUD, no
  safe-area filler. The verification screenshot must be pixel-comparable to the
  Origami artboard; host chrome would break the compare.

## DocC sample-code header

Every pattern file opens with a `///` doc-comment block on the public struct.
That comment is the pattern's DocC symbol page.

```swift
/// # <Category> — <Pattern name>
///
/// @Metadata {
///     @PageKind(sampleCode)
///     @PageImage(purpose: card, source: "<PatternID>")
/// }
///
/// <One or two sentences describing what the pattern does, matching how the
/// Origami editor's canvas reads. Name the patches that drive it.>
///
/// - Origami source: <URL to the .origami file in the corpus, if hosted>
/// - Translated: <YYYY-MM-DD>, when known
public struct <PatternID>View: View { ... }
```

Rules:

- **Title.** `# <Category> — <Pattern name>`, matching Origami's own naming
  (e.g. `# Interaction — Touch`).
- **`@PageKind(sampleCode)`.** Gives the page the sample-code chrome. `sampleCode`
  on a Swift symbol comment has been unreliable in some DocC versions; when a
  standalone sample-code page is authored in the DocC catalog, mirror the
  metadata there and let the symbol comment stand as-is.
- **`@PageImage(purpose: card, source: "<PatternID>")`.** `source` is the
  basename (no extension) of the pattern's preview image, which ships from the
  DocC catalog's `Resources/Patterns/` directory. Basename = `PatternID`;
  keep them in lockstep so the gallery card resolves.
- **Prose description.** One or two sentences. Names the patches driving the
  pattern; matches what the Origami editor's canvas shows. Not a walkthrough.
- **Origami source URL.** When the pattern's `.origami` is hosted (a corpus
  release, a mirror), link it in a bullet under the prose. Skip if not hosted.
- **Translation date.** `YYYY-MM-DD`, when known. Skip if not known; do not
  fabricate a date.

## Public API surface

- **Pattern struct: `public`.** Always.
- **Any helper the pattern calls must also be `public`.** The pattern lives in
  the same module as the helpers today, but the DocC catalog and any downstream
  embedder see only the public surface. A translator who needs a helper that
  currently ships `internal` must promote it to `public` in the helper's own
  file (its own commit), not paper over it with a local re-implementation in
  the pattern file.
- **No new private helpers in a pattern file.** Pattern files hold one struct
  and its private computed properties. Reusable state or view logic is a helper
  in the module.

## Naming rules

- **Origami PascalCase, verbatim.** `Interaction_Touch` in Origami stays
  `Interaction_Touch` in Swift. Preserve the underscore separator. Preserve
  case exactly.
- **No marketing capitalization in identifiers.** `SwiftUI` is fine in prose
  and in framework references. A struct or file named `SwiftUiView` (marketing
  camel-case) is not. If the pattern's name contains a framework or brand,
  spell the identifier the way Swift APIs do (`SwiftUI` when it appears, never
  `SwiftUi`).
- **No trailing category suffixes on filenames.** `Interaction_Touch.swift`,
  not `Interaction_TouchPattern.swift` or `Interaction_TouchExample.swift`.
  Only the `View` suffix goes on the struct.

## Verification-host switch

The reference project's verification host is a one-screen app whose
`ContentView` switches on an environment variable to pick which pattern
renders. A translator adds one case per pattern as it lands.

Shape (naming and env-var name are the reference project's; a community port
mirrors the shape, not the identifiers):

```swift
struct ContentView: View {
    var body: some View {
        switch ProcessInfo.processInfo.environment["<PATTERN_SELECTOR_VAR>"] {
        case "touch":   Interaction_TouchView()
        // add cases as patterns land
        default:        <SomeDefaultPatternView>()
        }
    }
}
```

- **Slug.** Whatever the reference project's builder + verify workflows agree
  the slug is — no more, no less. The rule is symmetric with the workflow, not
  a category-stripping heuristic invented here. In the reference project,
  `builder.yml`'s "Resolve pattern name" step runs
  `sed -E 's/^Interaction_//' | tr '[:upper:]' '[:lower:]'`, which strips only
  the literal `Interaction_` prefix before lowercasing; `verify.yml`'s
  `PATTERNS` env pairs the same slug to the stem. So today:
  `Interaction_Touch` → `touch`, `Interaction_Drag` → `drag`, but
  `Layer_Frame` → `layer_frame` (underscore kept — the `Layer_` prefix is not
  stripped) and `Animation_ClassicAnimation` → `animation_classicanimation`.
  Read the current `builder.yml` before adding a case; a case labelled
  `interaction-touch` or `frame` (guessing a broader strip than the builder
  actually does) is unreachable and the host renders the default view instead.
  A community port that wants a broader rule (strip every category, or a
  hyphen-separated slug) changes builder + verify atomically in the same PR
  and updates this bullet.
- **One case per pattern.** Do not fold multiple patterns behind one slug. Each
  case renders exactly one pattern's view, with no host chrome around it.
- **Body is a single expression.** Same rule as the pattern's own body: the
  host renders the pattern and nothing else. No nav bar, no toolbar, no debug
  overlays. The screenshot the host produces is what the compare runs against.

## What NOT to add

- **No `print` / `debugPrint` / `os_log` in a pattern file.** Debug output has
  no place in a shipped translation. If you needed it during translation,
  strip it before commit.
- **No `fatalError` on a release path.** `fatalError` is fine only inside a
  branch that a type invariant makes unreachable, and only when the invariant
  is obvious from the surrounding code. A `fatalError` reachable by any input
  from the Origami graph is a bug; use the parser's flagging path (an
  `// unsupported: <type>, <reason>` comment at the call site) instead.
- **No color-hardcoded workarounds when the `.origami` has design tokens.**
  Origami's ColorKit/TypeKit ships semantic names (a color has a `name`, a
  `hex`, and a `colorUsages` list). The parser preserves those names in the
  IR. Emit code that references the named color from the source (a named
  constant, a semantic color lookup) rather than dropping a raw hex literal
  into the view body. If the parser has not yet decoded a token's name, add a
  `// TODO: parser-decoded token when available` comment beside the literal
  so the follow-up is visible.
- **No host chrome in the pattern's body.** `NavigationStack`, toolbars, tab
  bars, safe-area fillers, backgrounds that come from the host. None of that
  belongs in the pattern's body. The pattern renders its artboard.
- **No re-declaration of Swami helpers inside the pattern file.** If a helper
  is missing, ship the helper first (its own commit), then the pattern.

## Cross-checks before you commit

- Filename stem matches the `.origami` stem, verbatim.
- Struct name = `<filename stem>View`, `public`, with `public init() {}`.
- DocC header on the struct: title, `@Metadata { @PageKind(sampleCode);
  @PageImage(source: "<filename stem>") }`, prose, source URL if known,
  translation date if known.
- Every helper the pattern calls is `public` in the module today.
- Body is one expression. No host chrome. No debug output. No release-path
  `fatalError`.
- If the pattern is under a verification-host switch, one new case has been
  added; the case renders `<PatternID>View()` and nothing else.

## DocC catalog

The catalog is the human-facing surface: gallery pages, per-pattern sample-code
pages, mapping references. Pattern `.swift` files carry a symbol-comment header
(above); catalog `.md` files carry the gallery shape, resource bindings, and
the patch→SwiftUI mapping table. In a Swami-shaped module the catalog lives at
`<Module>.docc/`.

### Directives — the whole allowed set

Everything else stops and asks. In particular, no ad-hoc HTML, no custom card
grids by hand.

- **`@Metadata { ... }`** — page-level config wrapper. `@PageKind`, `@PageImage`,
  `@CallToAction` sit inside it.
- **`@PageKind(article)` / `@PageKind(sampleCode)`** — page classification.
  `sampleCode` gives the sample-code chrome (download slot, code-forward layout).
  For sample-code pages, prefer a **standalone `.md`** in the catalog — see the
  caveat under "DocC sample-code header" above; symbol comments carry the
  metadata, the standalone page carries the layout when the symbol version
  won't render.
- **`@PageImage(purpose: card, source: "<PatternID>")`** — gallery-card preview.
  `source` is the resource basename, no extension (see "Resources" below).
- **`@CallToAction(url: "<zip-url>", purpose: download, label: "Download")`** —
  download button on a pattern page, pointing at the Xcode-project zip
  published alongside the site.
- **`@Links(visualStyle: detailedGrid)`** — content-aware gallery cards. Each
  card pulls its preview from the linked page's own `@PageImage`. Do not
  hand-build the grid.
- **`@TabNavigator { @Tab("<Category>") { ... } }`** — category grouping on
  gallery pages. One tab per Origami sidebar category (Featured, Interaction,
  Layer, …).
- **`@Row` / `@Column`** — finer layout only when `@Links` doesn't fit, e.g. a
  single preview beside prose. Never for the main gallery grid.

### Catalog files and resources

- **Collection pages.** `<Module>.docc/<Collection>.md`. One article per Origami
  sidebar category (Featured, Animation, Interaction, Layer, …). These are the
  gallery pages that host `@TabNavigator` + `@Links`.
- **Standalone sample-code pages.** `<Module>.docc/Patterns/<PatternID>.md`.
  One file per pattern. Filename basename = pattern ID = image basename = doc
  link. Same `PatternID` the pattern's `.swift` file uses.
- **Preview images.** `<Module>.docc/Resources/Patterns/<PatternID>.png`.
  Basename = `PatternID`; keep the `.swift` file, the standalone catalog page,
  and the resource in lockstep so the gallery card resolves.
- **Framework symbol docs.** The `///` comments on public symbols in Swift
  source. DocC auto-generates the symbol pages; do not shadow them with a
  hand-authored article carrying the same title.

### Gallery article shape

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
        }
    }
    @Tab("Layer") {
        @Links(visualStyle: detailedGrid) {
            - <doc:Layer_Frame>
        }
    }
}
```

No per-card prose. `@Links` reads each linked page's `@PageImage` and title;
that is the card.

### Mapping table on the collection page

The collection page carries a **GFM table** mapping Origami patches to their
SwiftUI equivalents — one row per patch, symbol references in double backticks
so DocC auto-links, right-hand cells tagged `(native)` or `(helper)` so readers
know whether it's stock SwiftUI or a Swami helper. The catalog is the only
mapping reference — there is no separate mapping doc — so a patch that lands
without a row here is effectively undocumented for the human reader.

```markdown
| Origami patch                     | SwiftUI                                                                       |
|-----------------------------------|-------------------------------------------------------------------------------|
| `interaction.tap` — Tap           | ``onTapGesture(_:)`` (native)                                                 |
| `interaction.drag` — Drag         | ``drag(enable:momentum:bounds:position:translation:velocity:reset:)`` (helper) |
| `layer.oval` — Oval               | `Circle()` (native)                                                           |
```

When a helper lands, add its row here in the same commit. When a helper is
retired in favour of a native construct, update the row to `(native)` and drop
the helper. That's the "know to reach for it" record — the codebase enforces
correctness, the mapping table enforces *reachability* by a reader.

### Catalog: what NOT to do

- **No per-pattern prose articles.** Sample-code pages are image + code + a
  sentence or two of context. If it starts to read like a walkthrough, delete
  it — the render and the code are the walkthrough.
- **No `@Row`/`@Column` for the gallery.** `@Links` auto-cards from
  `@PageImage`. Rows and columns are for one-off layouts.
- **No hand-added binaries in `Resources/Patterns/`.** Those PNGs come from
  CI-composited renders. Don't drop a hand-cropped screenshot in and commit it
  — regenerate through the render pipeline so the image matches the code.
- **No mapping-table row without a landed patch.** Rows describe what the
  codegen actually emits today. A row for a patch the parser doesn't decode is
  a lie the reader will trip over.

## Where to read next

- **`skill/pattern-translation/SKILL.md`**. The judgment half. What each patch
  becomes in SwiftUI, how state, animation, and interpolation are staged. Read
  before deciding *what* to emit; read this skill for *how the file is shaped*
  and how it lands in the catalog.
- **`skill/unslop/SKILL.md`**. Style rules for the prose in the DocC header
  and in the catalog's collection pages.
