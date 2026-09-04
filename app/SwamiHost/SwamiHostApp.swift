import SwiftUI

// Preview-host app for the swami verify gate (ADR-0006 / CLAUDE.md verify gate).
// A one-screen iOS app that renders a generated pattern view so XcodeBuildMCP can
// build_run_sim + screenshot it against the Origami render. Not shipped — verification only.
@main
struct SwamiHostApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}
