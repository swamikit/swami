---
name: docc-authoring
description: Everything the DocC surface for a translated pattern needs. The reader-facing catalog page shape (preview → the patch → how it's built → downloads → behavior, for a human browsing the gallery), the emitted `.swift` file's shape (filename, struct, doc-hidden symbol comment, public API, verification-host switch), and the catalog conventions that tie them together (directive whitelist, gallery page shape, `Resources/Patterns/<PatternID>.png` basename contract, GFM patch→SwiftUI mapping table). The page centers the Origami patch and how the view is written — never the `<PatternID>View()` symbol. Community-portable, sibling to `skill/pattern-translation`. Load whenever you're about to write a pattern's `.swift` file, a catalog page, or a mapping-table row.
metadata:
  type: procedural
---

# DocC authoring: pattern file + catalog surface

Sibling to `skill/pattern-translation`. That skill decides *what* the SwiftUI
looks like (patch-to-construct mapping, ISAT staging, native-first). This skill
decides *what reaches the reader*: the pattern file on disk (filename, struct,
doc-hidden symbol comment, public API, verification-host switch) and the DocC
catalog that renders it (directives, gallery shape, resource naming, patch→SwiftUI
mapping table).

Repo-specific details (env var names, workflow filenames, `sed`/`tr` slug
derivation) are marked as the reference project's — community ports mirror the
shape, not the identifiers. No PR flow, no issue numbers.

**The one principle: the patch is the product, the pattern-view is a worked
example.** A reader comes to the gallery to learn a behavior they can reuse — the
Origami patch and the SwiftUI it maps to (`origami.Drag` → ``View/drag(...)``; a
`origami.PopSwitch` pinch → `@State` + a spring). The `<PatternID>View` struct is
*not* that — it's one arrangement of the patch on a demo layer, interesting only as
a demonstration of how the patch is written. So the catalog page centers the patch
and shows how the view is built; it does **not** promote `<PatternID>View()` as an
API, and the struct is **hidden from the generated docs** so it never shows up as a
second, symbol-shaped copy of the same example. The full source is a download away
for anyone who wants to read the whole thing.

**Who the catalog page is for.** A developer browsing a SwiftUI pattern gallery —
not the harness, not a future translator. They want to see the pattern, understand
the patch behind it, and reach for that patch on their own layers. Write every
catalog page in that voice. The parser IR, the fidelity debts, the "flag, don't
fake" caveats, and the render-pipeline mechanics are real, but they belong in the
`.swift` source as code comments, never in the reader-facing page. The consumer
page shape below is the target; the `.swift`/workflow rules that follow are the
plumbing that makes it render.

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
@_documentation(visibility: internal)
public struct <PatternID>View: View {
    public init() {}
    public var body: some View {
        // single expression; the artboard's layer tree, translated
    }
}
```

- **`PatternID`** = the Origami source stem, verbatim. `Interaction_Touch.origami`
  produces `public struct Interaction_TouchView`. Keep the underscore. The 1:1
  mapping from Origami's filename to the Swift type is deliberate; the pattern's
  `.swift` file and its catalog page share the stem so a reader can find one from
  the other.
- **`View` suffix.** Every pattern struct ends in `View`. `Interaction_TouchView`,
  not `Interaction_Touch`. The suffix disambiguates from Swami helpers that
  share a patch name (`Interaction` the helper vs. `Interaction_TouchView` the
  pattern).
- **`public`.** The struct and its `init()` are public — the verification host is
  a separate target that `import`s the module and instantiates the view across the
  module boundary, so a non-public view can't be screenshot by the pixel gate.
- **`@_documentation(visibility: internal)`.** The view is public for the host but
  hidden from the generated docs. This is what keeps the gallery clean: without it,
  DocC emits a full symbol page for `<PatternID>View` (its `init()`, `var body`, an
  auto "Default Implementations" block) that duplicates the standalone pattern page
  and buries the patch under codebase surface. The reader-facing artifact is the
  standalone `.md` page; the symbol is not. (Longer term these example views move
  out of the shipped library entirely, into a downloadable example/host target —
  hiding them from docs is the same rendered outcome with none of the build risk.)
- **Single-expression body.** The body renders the Origami artboard and nothing
  else. No `NavigationStack`, no `NavigationView`, no toolbar, no debug HUD, no
  safe-area filler. The verification screenshot must be pixel-comparable to the
  Origami artboard; host chrome would break the compare.

## Symbol comment on the struct

The `///` comment on the pattern struct is a **note for someone reading the
source**, not a rendered DocC page — the struct is hidden from the docs, so the
reader-facing page is the standalone `.md` (below), which owns the title,
`@PageImage`, and `@CallToAction`. Keep the symbol comment short and factual:

```swift
/// <Category> — <Pattern name>: a worked example of <the patch(es) that drive it>.
///
/// - Origami source: <URL to the .origami file in the corpus, if hosted>
/// - Translated: <YYYY-MM-DD>, when known
```

- **Name the patch, not a walkthrough.** One or two sentences: what the pattern is
  and which Origami patch(es) drive it. This is the same fact the page's "The patch"
  section leads with.
- **Do not put `@Metadata`/`@PageKind`/`@PageImage` in the symbol comment.** Those
  render nothing on a doc-hidden symbol; page metadata lives on the standalone `.md`.
- **Origami source URL.** When the pattern's `.origami` is hosted, link it. Skip if
  not hosted.
- **Translation date.** `YYYY-MM-DD`, when known. Skip if not known; do not
  fabricate a date.

## Public API surface

- **Pattern struct: `public` + `@_documentation(visibility: internal)`.** Public so
  the host can instantiate it, hidden so it is not documented. Always both.
- **The documented API is the patch modifier methods.** What the catalog promotes and
  what a reader reaches for is the ``View`` patch extensions — ``View/drag(…)``,
  ``View/interaction(…)`` — not the `ViewModifier` structs behind them. Those structs stay
  `public` (the methods apply them internally) but carry `@_documentation(visibility:
  internal)`, so DocC never renders their `ViewModifier` conformance surface. See "the
  documented patch is the modifier method, not the `ViewModifier` behind it" below.
- **Any helper the pattern calls must be `public`.** A translator who needs a helper
  that currently ships `internal` promotes it to `public` in the helper's own file
  (its own commit), not with a local re-implementation in the pattern file.
- **No new private helpers in a pattern file.** Pattern files hold one struct and
  its private computed properties. Reusable state or view logic is a helper in the
  module.

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
- Struct name = `<filename stem>View`, `public`, with `public init() {}`, carrying
  `@_documentation(visibility: internal)`.
- Symbol comment on the struct: one factual line naming the patch, source URL if
  known, translation date if known. No `@Metadata` in the symbol comment.
- Every helper the pattern calls is `public` in the module today.
- Body is one expression. No host chrome. No debug output. No release-path
  `fatalError`.
- Standalone catalog page exists at `<Module>.docc/Patterns/<PatternID>.md`, in the
  consumer shape below, and centers the patch (no `<PatternID>View()` usage snippet,
  no `` ``<PatternID>View`` `` in See Also).
- If the pattern is under a verification-host switch, one new case has been
  added AND the matching `<slug>:<stem>` pair is registered where the verify
  workflow reads it (in the reference project, `.github/patterns.txt`). The
  case renders `<PatternID>View()` and
  nothing else. Both edits ship in the same commit — a case without the
  registration is unreachable; a registration without the case renders the
  default view.

## DocC catalog

The catalog is the human-facing surface: gallery pages, per-pattern sample-code
pages, mapping references. Pattern `.swift` files carry a short doc-hidden symbol
comment (above); catalog `.md` files carry the reader-facing page, the gallery
shape, resource bindings, and the patch→SwiftUI mapping table. In a Swami-shaped
module the catalog lives at `<Module>.docc/`.

### The reader-facing page (consumer shape)

Each standalone pattern page (`<Module>.docc/Patterns/<PatternID>.md`) is what a
developer lands on from the gallery. Write it in this order, and stop there:

1. **Preview first** — the rendered pattern, so they see it before they read
   anything. The `@PageImage(purpose: card, …)` gives the header/card image;
   embed the same render inline with a Markdown image (`![alt](<PatternID>)`,
   basename only) under a `## Preview` heading so it leads the body.
2. **The patch** — the reusable point of the page. Name the Origami patch and the
   SwiftUI it maps to; link the patch symbol when there is a helper
   (``View/drag(...)``) or the mapping row in <doc:OrigamiMappings> when it lands
   on native SwiftUI. Then a **short snippet showing the patch applied** — a few
   lines centered on the modifier/gesture, not the whole file, not
   `<PatternID>View()`. This is "the patches I use to get to that configuration."
3. **How it's built** — one or two sentences on how the view arranges the patch
   (the state it feeds, the layout, the animation), then point at the full source
   in Downloads. Do **not** paste `<PatternID>View()` as usage — the view is a
   demonstration of the patch, not the thing to promote. If the whole build is
   already clear from the patch snippet, this section can be a single sentence.
4. **Behavior** — two or three plain bullets on what the gesture/interaction
   does, in a person's words ("drag it and it keeps moving, then springs back"),
   not the patch graph.
5. **Downloads** — two links, both already public for every corpus pattern, no
   TODO:
   - **Swift sample** — the pattern's own `.swift` in this repo:
     `https://github.com/swamikit/swami/blob/development/app/Swami/Patterns/<PatternID>.swift`
     — the full source; read it to see how the patch composes into a view, paste
     it to run it.
   - **Origami source** — `https://origami.design/public/origami_files/patterns/<PatternID>.origami`
     — the original prototype, and the exact file `verify.yml` fetches to render
     the reference. Opens in Origami Studio.

   Wire the Origami source as the page's `@CallToAction(purpose: download)` and
   list both under a `## Downloads` heading. Never leave a downloads TODO — the
   `.origami` link is the **same public endpoint `verify.yml` downloads for the
   pixel compare** (`curl -sL … origami.design/public/origami_files/patterns/<PatternID>.origami`,
   `verify.yml`), so if the gate can render a pattern its `.origami` URL resolves;
   the `.swift` ships in this repo.

Template:

~~~markdown
# <Category> — <Pattern name>

@Metadata {
    @PageKind(sampleCode)
    @PageImage(purpose: card, source: "<PatternID>")
    @CallToAction(url: "https://origami.design/public/origami_files/patterns/<PatternID>.origami", purpose: download, label: "Open in Origami")
}

<One human sentence: what this pattern is.>

## Preview

![<one-line description of the rendered interaction>](<PatternID>)

## The patch

<Which Origami patch drives it and what it becomes in SwiftUI — link ``View/…`` for a
helper, or <doc:OrigamiMappings> for native. One or two sentences: this is the reusable
part.>

```swift
<a few lines: the patch applied — the modifier or gesture, with the @State it writes to.
Not the whole view, not <PatternID>View().>
```

## How it's built

<One or two sentences on how the view arranges the patch; the full source is in Downloads.>

## Behavior

- <what the gesture does, in plain words>

## Downloads

- **Swift sample** — [`<PatternID>.swift`](https://github.com/swamikit/swami/blob/development/app/Swami/Patterns/<PatternID>.swift) — the full source. Read it to see how the patch composes into a view; paste it to run it.
- **Origami source** — [`<PatternID>.origami`](https://origami.design/public/origami_files/patterns/<PatternID>.origami) — the original prototype (opens in Origami Studio).

## See Also

- ``View/<patch method>`` — the patch this pattern uses   <!-- or <doc:OrigamiMappings> when native -->
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
- **`@Comment { ... }`** — authoring note that never renders. Use it to park an
  authoring TODO in source without putting machinery prose on the reader's page.
  (Downloads are not a TODO — both URLs above are public for every pattern.)
- **`@PageKind(article)` / `@PageKind(sampleCode)`** — page classification.
  `sampleCode` gives the sample-code chrome (download slot, code-forward layout).
  Sample-code pages are **standalone `.md`** in the catalog — the pattern view
  struct is hidden from the docs, so the standalone page is the only rendered
  surface for the pattern.
- **`@PageImage(purpose: card, source: "<PatternID>")`** — gallery-card preview.
  `source` is the resource basename, no extension (see "Resources" below).
- **`@CallToAction(url: "https://origami.design/public/origami_files/patterns/<PatternID>.origami", purpose: download, label: "Open in Origami")`** —
  download button on a pattern page, pointing at the public Origami source file
  (the same artifact `verify.yml` fetches for the compare).
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
  One file per pattern, written in the consumer shape above (preview → the patch →
  how it's built → behavior → downloads). Filename basename = pattern ID = image
  basename = doc link. Same `PatternID` the pattern's `.swift` file uses.
- **Preview images.** `<Module>.docc/Resources/Patterns/<PatternID>.png`.
  Basename = `PatternID`; keep the `.swift` file, the standalone catalog page,
  and the resource in lockstep so the gallery card resolves.
- **The documented patch is the modifier method, not the `ViewModifier` behind it — and
  it's featured through a per-patch article.** A patch helper is usually a
  `public struct <Patch>: ViewModifier` plus a `public extension View { func <patch>(...) }`
  entry point. Hide the struct with `@_documentation(visibility: internal)` — otherwise DocC
  renders its `ViewModifier` conformance (`animation` / `concat` / `transaction` under
  "Default Implementations"), which is SwiftUI's surface, not this patch's API. The method's
  `///` is the canonical reference — a reader-voice overview (what it does, not how it's
  built), the parameters as a `- term <name>:` list, and a short example. It renders under
  **Extended Modules → SwiftUICore → View**, because DocC files anything you add to an
  external type there. **DocC will not let you curate that method into a top-level "Patches"
  group** — it silently drops it and the group renders empty. So feature each patch with a
  short **article** at `<Module>.docc/Patches/<Patch>.md` (`# Drag`, `# Interaction`): what
  the patch is, one call, a link to the canonical `` ``View/<patch>(…)`` `` for the full
  signature, and — when a pattern uses it — a `## Topics → ### Used in` link to that pattern.
  Give the article a filename that can't collide with the hidden struct's name
  (`DragPatch.md`, not `Drag.md`); the `# Drag` heading is what the reader sees. The landing
  "Patches" group lists those articles, not the methods. The pattern view structs are hidden
  the same way — never add an "Examples" topic group, never link `` ``<PatternID>View`` ``.

### Landing page shape

The module landing page (`<Module>.docc/<Module>.md`) leads with a one-line framing
that puts the patches first, a `@Links` gallery grid, then a `## Topics` split into:

- **Patterns** — the standalone pattern pages (`<doc:Interaction_Drag>`, …).
- **Patches** — the per-patch article pages (`<doc:DragPatch>`, `<doc:InteractionPatch>`,
  …), each featuring one patch in reader voice and linking its canonical modifier. This is
  the reusable API; the group is named "Patches", not "Helpers" or "Examples". (DocC can't
  curate the `View` extension methods directly into this group — see above — so the articles
  stand in; the methods stay under Extended Modules, linked from each article. The
  `ViewModifier` structs behind them stay hidden.)
- **Reference** — `<doc:OrigamiMappings>` and any other reference article.

No "Examples" group (the view structs are hidden), and no internal/dev-process
articles in the published catalog (contributor docs like the build discipline live
in the repo's `docs/`, not in `<Module>.docc/`).

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

- **No per-pattern prose articles.** Sample-code pages are preview + the patch +
  how it's built + behavior + downloads. If it starts to read like a walkthrough,
  delete it — the render and the code are the walkthrough.
- **No promoting the view symbol.** Don't paste `<PatternID>View()` as a usage
  snippet, don't link `` ``<PatternID>View`` `` from a page, don't add an "Examples"
  topic group. The page centers the patch; the view is a download. (The struct is
  `@_documentation(visibility: internal)` for exactly this reason.)
- **No harness or machinery prose on the page.** No description of the CI render
  pipeline, no parser IR (node/edge counts), no fidelity-debt disclaimers, no
  "flag, don't fake", no `TODO: parser-decoded token`. That belongs in the
  `.swift` comments. A page that explains how the PNG is produced instead of
  showing the pattern has the wrong reader in mind.
- **No page without a patch snippet.** The point of a sample-code page is to teach
  the patch. If a reader can't see the modifier/gesture applied, it's not done.
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
- **`skill/unslop/SKILL.md`**. Style rules for the prose in the symbol comment
  and in the catalog's collection pages.
