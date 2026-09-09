import SwiftUI
import Foundation
import Swami

// The pattern currently under verification. CI drives which one by setting SWAMI_PATTERN;
// the loop adds a `case "<slug>"` per pattern as they're translated. Keep the body a single
// expression so screenshots are 1:1 with the Origami artboard — no host chrome, no nav bar.
struct ContentView: View {
    var body: some View {
        switch ProcessInfo.processInfo.environment["SWAMI_PATTERN"] {
        case "touch", nil: TouchOrigamiExampleView()
        case "drag":       verifiedInteractionDragView()
        default:           TouchOrigamiExampleView()   // add cases as patterns land
        }
    }

    /// A stale framework now fails at launch instead of silently publishing a screenshot
    /// from an older Interaction Drag implementation. The runner's `drag` selection must
    /// traverse this assertion before `simctl io screenshot` can capture the app.
    private func verifiedInteractionDragView() -> some View {
        precondition(
            Interaction_DragView.renderSignature == "interaction-drag-r140-reset-start-v2",
            "SwamiHost linked a stale Interaction Drag implementation"
        )
        return Interaction_DragView()
    }
}
