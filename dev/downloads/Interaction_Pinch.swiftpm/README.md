# Interaction_Pinch (Swami sample)

A runnable Xcode sample for one Swami pattern.

## Run it

1. Unzip.
2. Double-click **`Interaction_Pinch.swiftpm`** (or Xcode > File > Open...). Requires **Xcode 15+**.
3. Pick an iOS Simulator (or your device) and press **Run** (Cmd-R).

This is a standard **single-target App Playground**, so it also opens directly in
**Swift Playgrounds on iPad** — no restructuring needed.

## What's inside

One app target (one module); everything compiles together:

- `Package.swift` — App Playground manifest (`.iOSApplication` product).
- `SampleApp.swift` — `@main`; hosts the pattern view and nothing else.
- `Interaction_Pinch.swift` — the pattern view, from the Swami repo.
- `Drag.swift` — vendored Swami helper source.
- `Interaction.swift` — vendored Swami helper source.
- `RoundedTriangle.swift` — vendored Swami helper source.
- `Swami.swift` — vendored Swami helper source.
- `TouchOrigamiExample.swift` — vendored Swami helper source.

## One edit from the repo source

Swami ships patterns and helpers in a single module, so a pattern refers to helpers
(e.g. `RoundedTriangle`, the `.drag` modifier) with no import. This sample is also a
single module. The only change from the repo file is that a leading `import Swami` line
(present in some patterns, absent in others) is removed — with no separate `Swami`
module here it would fail to build with "no such module 'Swami'". Everything else is
byte-for-byte the repo source. See `sample-manifest.json` for which files were touched.

## Learn more

Swami pattern gallery: https://swamikit.github.io/swami/documentation/swami/
