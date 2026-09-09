# Interaction Drag runner wiring

This trace is the executable delivery path for `Interaction_Drag`. Run
`scripts/assert-interaction-drag-wiring.py` after changing any link in the path. The
`SwamiHost` target also runs that assertion as its first build phase on the macOS
runner.

## Source to target

1. `app/Swami/Patterns/Interaction_Drag.swift` defines the committed
   `Interaction_DragView` and its revision-specific `renderSignature`.
2. `app/Swami.xcodeproj/project.pbxproj` places `app/Swami` in a
   `PBXFileSystemSynchronizedRootGroup` owned by the `Swami` framework target. This
   gives `Interaction_Drag.swift` target membership without a hand-maintained source
   build-file entry.
3. The `SwamiHost` target depends on, links, and embeds the built `Swami.framework`.
   Its `ContentView` maps the exact runner slug `drag` to `Interaction_DragView`.
4. Before returning that view, `ContentView` compares the linked framework's public
   render signature with the host's committed expectation. A stale framework therefore
   traps during launch; it cannot silently produce evidence for an older implementation.
   The same signature is exposed as the view's accessibility value without changing
   pixels.

## Registry to capture

1. `.github/patterns.txt` maps `drag` to `Interaction_Drag`. The verify job uses the
   stem to recognize the changed generated source and uses the slug at runtime.
2. The macOS job renders `Interaction_Drag.origami`, reads its native 750×1334 output,
   and selects the matching 375×667-point iPhone SE simulator.
3. Xcode builds `SwamiHost` and executes the wiring assertion build phase. The job then
   finds the newly built `.app`, installs that exact path with `simctl install`, and
   reads its bundle identifier from that app's `Info.plist`.
4. Capture terminates any running instance and launches the installed bundle with
   `SIMCTL_CHILD_SWAMI_PATTERN=drag`. That selection must pass the runtime render
   signature assertion before `simctl io screenshot` writes `out/swami/drag.png`.
5. The Drag-only Maestro flow relaunches with the same environment, performs two card
   swipes, and records `out/recordings/drag.mp4` with `simctl recordVideo --codec=h264`.
   Publication rejects a missing or empty recording.

## Failure diagnosis

The screenshots attached to rejected head `977ba62` show that its Swami and Origami
renders are visually the same composition. The red outlines in the third attachment
are ImageMagick's difference visualization, not an Origami layer. Consequently that
third image must not be read as the reference hierarchy.

The repeated `0.000714529` did not prove that three binaries were identical: the
revisions retained the same final rest-state pixels, and the workflow reported the
parenthesized normalized *distortion* emitted by ImageMagick's SSIM metric as though it
were similarity. Near zero is expected for nearly identical images in that field. This
repository's workflow is a protected control plane, so product changes do not alter its
metric interpretation. The source/build/runtime signature checks above independently
make stale linkage an executable failure while preserving faithful pixels.

## Local static check

```sh
scripts/assert-interaction-drag-wiring.py
```

A successful check prints the exact signature expected by both the framework source and
host. The unit suite separately covers composition constants and verifies that a second
gesture starts from Drag's configured Start input without requiring an intervening reset.
