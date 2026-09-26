---
name: docc-authoring
description: Everything the DocC surface for a translated pattern needs. The reader-facing catalog page shape (preview → usage → downloads → behavior, for a human browsing the gallery), the emitted `.swift` file's shape (filename, struct, symbol-comment header, public API, verification-host switch), and the catalog conventions that tie them together (directive whitelist, gallery page shape, `Resources/Patterns/<PatternID>.png` basename contract, GFM patch→SwiftUI mapping table). Community-portable, sibling to `skill/pattern-translation`. Load whenever you're about to write a pattern's `.swift` file, a catalog page, or a mapping-table row.
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

**Who the catalog page is for.** A developer browsing a SwiftUI pattern gallery
— not the harness, not a future translator. They want to see the pattern, copy
the view into their project, and read one plain sentence about what it does.
Write every catalog page in that voice. The parser IR, the fidelity debts, the
"flag, don't fake" caveats, and the render-pipeline mechanics are real, but they
belong in the `.swift` source as code comments, never in the reader-facing page.
The consumer page shape below is the target; the `.swift`/workflow rules that
follow are the plumbing that makes it render.

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

- **Slug.** Whatever the builder and verify workflows agree it is — read the
  current convention and pattern registry before adding a case, don't invent a
  strip rule. In the reference project the builder strips only the literal
  `Interaction_` prefix then lowercases (`Interaction_Drag` → `drag`;
  `Layer_Frame` → `layer_frame`), and `.github/patterns.txt` pairs that slug to
  the stem. A guessed slug is unreachable and the host renders the default view.
- **One case per pattern.** Do not fold multiple patterns behind one slug. Each
  case renders exactly one pattern's view, with no host chrome around it.
- **Register the slug where the verify workflow reads it, in the same commit.**
  The switch case alone is unreachable: the reference project's `verify.yml`
  render + compare loops load only the `<slug>:<stem>` pairs from
  `.github/patterns.txt`, so a case with no matching registry entry never gets
  launched and the PR produces no evidence for the new pattern. Add the pair
  to `.github/patterns.txt` in the same commit that adds the switch case. This
  keeps routine pattern registration outside the protected workflow control
  plane. A community port that discovers
  patterns differently (glob, manifest file) still needs the equivalent
  registration on the workflow side, landed atomically with the case.
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
  added AND the matching `<slug>:<stem>` pair is registered where the verify
  workflow reads it (in the reference project, `.github/patterns.txt`). The
  case renders `<PatternID>View()` and
  nothing else. Both edits ship in the same commit — a case without the
  registration is unreachable; a registration without the case renders the
  default view.

## DocC catalog

The catalog is the human-facing surface: gallery pages, per-pattern sample-code
pages, mapping references. Pattern `.swift` files carry a symbol-comment header
(above); catalog `.md` files carry the reader-facing page, the gallery shape,
resource bindings, and the patch→SwiftUI mapping table. In a Swami-shaped module
the catalog lives at `<Module>.docc/`.

### The reader-facing page (consumer shape)

Each standalone pattern page (`<Module>.docc/Patterns/<PatternID>.md`) is what a
developer lands on from the gallery. Write it in this order, and stop there:

1. **Preview first** — the rendered pattern, so they see it before they read
   anything. The `@PageImage(purpose: card, …)` gives the header/card image;
   embed the same render inline with a Markdown image (`![alt](<PatternID>)`,
   basename only) under a `## Preview` heading so it leads the body.
2. **Usage** — a copy-pasteable SwiftUI snippet showing how a developer actually
   uses the view (`import <Module>` then `<PatternID>View()`), plus the helper
   call if they'd want the same behavior on their own layers.
3. **Downloads** — the Swift sample and, when hosted, the source pattern. Wire a
   real download to `@CallToAction` once the artifact has a stable URL; until
   then name what will be downloadable and leave the TODO in a `@Comment` (which
   doesn't render), not as visible apology.
4. **Behavior** — two or three plain bullets on what the gesture/interaction
   does, in a person's words ("drag it and it keeps moving, then springs back"),
   not the patch graph.

Template:

~~~markdown
# <Category> — <Pattern name>

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "<PatternID>")
}

<One human sentence: what this pattern is.>

## Preview

![<one-line description of the rendered interaction>](<PatternID>)

## Usage

```swift
import <Module>

struct ContentView: View {
    var body: some View {
        <PatternID>View()
    }
}
```

## Behavior

- <what the gesture does, in plain words>

## Downloads

- **Swift sample** — the source for `<PatternID>View`.
- **Origami source** — `<PatternID>.origami`, if hosted.

## See Also

- ``<PatternID>View``
- <doc:OrigamiMappings>
~~~

An optional `## Translation notes` may close the page with **one or two human
sentences** that point at the `.swift` source for the parser/fidelity detail.
That is the only place translation-machinery language is allowed on the page, and
it stays at the bottom, brief, and pointer-only.

**Keep off the reader-facing page:** the CI render pipeline (which workflow makes
the PNG), parser IR / node-and-edge counts, fidelity-debt disclaimers,
"flag, don't fake", and any `// TODO: parser-decoded token` prose. All of that
lives in the `.swift` file's comments where it travels with the code — the page
is for the person using the view.

### Directives — the whole allowed set

Everything else stops and asks. In particular, no ad-hoc HTML, no custom card
grids by hand. Two non-directive allowances: a **Markdown image**
(`![alt](<PatternID>)`) for the inline preview, and a **`@Comment { ... }`** block
for an authoring note or TODO that must not render on the page.

- **`@Metadata { ... }`** — page-level config wrapper. `@PageKind`, `@PageImage`,
  `@CallToAction` sit inside it.
- **`@Comment { ... }`** — authoring note that never renders. Use it to park a
  TODO (e.g. a download URL that has no home yet) in source without putting
  machinery prose on the reader's page.
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
  One file per pattern, written in the consumer shape above (preview → usage →
  downloads → behavior). Filename basename = pattern ID = image basename = doc
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

- **No per-pattern prose articles.** Sample-code pages are preview + usage +
  downloads + a couple of behavior bullets. If it starts to read like a
  walkthrough, delete it — the render and the code are the walkthrough.
- **No harness or machinery prose on the page.** No description of the CI render
  pipeline, no parser IR (node/edge counts), no fidelity-debt disclaimers, no
  "flag, don't fake", no `TODO: parser-decoded token`. That belongs in the
  `.swift` comments. A page that explains how the PNG is produced instead of
  showing the pattern has the wrong reader in mind.
- **No page without a usage snippet.** The point of a sample-code page is to be
  copied. If a developer can't paste `<PatternID>View()` out of it, it's not done.
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
