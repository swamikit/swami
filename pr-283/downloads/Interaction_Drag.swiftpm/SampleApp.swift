import SwiftUI

// Downloadable Swami sample — Interaction_Drag.
//
// This is a self-contained, single-target App Playground: open the enclosing `.swiftpm`
// in Xcode 15+ and press Run to launch the pattern as an iOS app in the Simulator (or on
// a device). The one screen renders `Interaction_DragView` — the exact pattern view from the Swami
// gallery — and nothing else.
//
// The pattern view (`Interaction_Drag.swift`) and the Swami helper sources it uses are all in
// this one module, so no `import Swami` is needed and no external checkout is required.
@main
struct SampleApp: App {
    var body: some Scene {
        WindowGroup {
            Interaction_DragView()
        }
    }
}
