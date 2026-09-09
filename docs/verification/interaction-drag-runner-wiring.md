# Interaction Drag runner wiring

This trace is the executable delivery path for `Interaction_Drag`. Run
`scripts/assert-interaction-drag-wiring.py` after changing any link in the path. The
`SwamiHost` target runs the assertion's product-scoped `--build-only` mode as its
first build phase. The default invocation also validates runner delivery semantics.

## Source to target

1. `app/Swami/Patterns/Interaction_Drag.swift` defines the committed
   `Interaction_DragView` and its revision-specific `sourceRevision`.
2. `app/Swami.xcodeproj/project.pbxproj` places `app/Swami` in a
   `PBXFileSystemSynchronizedRootGroup` owned by the `Swami` framework target. This
   gives `Interaction_Drag.swift` target membership without a hand-maintained source
   build-file entry.
3. The `SwamiHost` target depends on, links, and embeds the built `Swami.framework`.
   Its `ContentView` maps the exact runner slug `drag` to `Interaction_DragView`.
4. `ContentView` compares the pattern source marker and linked framework bundle
   revision with the host's committed expectation when the selected view appears. It
   reports the result to the runner log, but always returns `Interaction_DragView`.
   Runtime-head diagnosis therefore cannot alter, cover, or replace captured pixels.

## Registry to capture

1. `.github/patterns.txt` maps `drag` to `Interaction_Drag`. The verify job uses the
   stem to recognize the changed generated source and uses the slug at runtime.
2. The macOS job renders `Interaction_Drag.origami`, reads its native 750×1334 output,
   and selects the matching 375×667-point iPhone SE simulator.
3. Xcode builds `SwamiHost` and executes the product-scoped wiring assertion build
   phase. The full assertion separately recognizes the workflow's build, exact-app
   install, runtime selection, screenshot capture, and H.264 recording commands by
   semantics rather than indentation or exact generated text. The job finds the newly
   built `.app`, installs that path with `simctl install`, and reads its bundle identifier
   from that app's `Info.plist`.
4. Capture terminates any running instance and launches the installed bundle with
   `SIMCTL_CHILD_SWAMI_PATTERN=drag`. That selection logs the runtime-head check and
   always renders the pattern before `simctl io screenshot` writes
   `out/swami/drag.png`; build/install identity failures remain assertion failures rather
   than product UI.
5. The Drag-only Maestro flow relaunches with the same environment, performs two card
   swipes, and records `out/recordings/drag.mp4` with `simctl recordVideo --codec=h264`.
   A `SwamiHost`-only simultaneous gesture renders a small indicator at the injected
   touch location until release, making touch-down and the trajectory legible without
   adding cursor UI to `Interaction_DragView`. Publication rejects a missing or empty
   recording.

## Failure diagnosis

Revision-specific assertions on rejected head `bdade46` established that the runner
captured the intended source, host selection, newly built and installed app, and runtime
view. The matching screenshots therefore disproved the stale-runner hypothesis. Direct
review of that head's Origami reference identified the real product defect: Swami drew
a pale rounded interaction-area panel that is not a rendered layer in the reference.
The corrected view retains the panel's former 315×607-point dimensions only as the
logical input used to derive Drag bounds; its visible hierarchy is now just the canvas
and card.

The repeated `0.000714529` did not prove that three binaries were identical: the
revisions retained the same final rest-state pixels, and the workflow reported the
parenthesized normalized *distortion* emitted by ImageMagick's SSIM metric as though it
were similarity. This repository's workflow is a protected control plane, so product
changes do not alter its metric interpretation. SSIM remains catastrophic-sanity
information only. The source/build/runtime revision checks above independently make stale linkage
observable without introducing a diagnostic layer into the selected runtime, while the
screenshot triplet, recording, DocC, and Reviewer determine fidelity.

## Local static check

```sh
scripts/assert-interaction-drag-wiring.py
```

A successful check prints the exact signature expected by both the framework source and
host. The unit suite separately covers composition constants and verifies that a second
gesture starts from Drag's configured Start input without requiring an intervening reset.
