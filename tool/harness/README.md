# harness — SwiftUI corpus & visual-verification

The SwiftUI side of the corpus. Each generated pattern lives in
`Sources/OrigamiPatterns/` with a `#Preview`.

## Two ways to verify

**Interactive (human):** open this package in Xcode → the canvas renders each pattern's
`#Preview`. Good for eyeballing interaction/feel.

**Headless (the loop's scoring step):** render every pattern to a PNG with no GUI/simulator:

```sh
cd harness
SNAPSHOT_OUT=/tmp/swami-snapshots swift test
```

Each render logs `SNAPSHOT <name> -> <path>`. Collect those PNGs and diff them against the
Origami renders (`../verify/`, and the Origami viewer captures). `swift test` builds for
the host (macOS) so no simulator is needed; `xcodebuild test -destination 'platform=iOS
Simulator,name=iPhone 15'` works too if you want the iOS toolchain.

Add a `test...` method in `Tests/OrigamiPatternsTests/SnapshotTests.swift` for each new
pattern as the parser/codegen covers more of the corpus.
