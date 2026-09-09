import SwiftUI
import Foundation
import Swami

// The pattern currently under verification. CI drives which one by setting SWAMI_PATTERN;
// the loop adds a `case "<slug>"` per pattern as they're translated. Keep the body a single
// expression so screenshots are 1:1 with the Origami artboard — no host chrome, no nav bar.
struct ContentView: View {
    private static let interactionDragSignature = "interaction-drag-r140-canvas-card-v4"

    var body: some View {
        switch ProcessInfo.processInfo.environment["SWAMI_PATTERN"] {
        case "touch", nil: TouchOrigamiExampleView()
        case "drag":       verifiedInteractionDragView()
        default:           TouchOrigamiExampleView()   // add cases as patterns land
        }
    }

    /// Keep stale-link detection on the selected Drag runtime path without terminating
    /// SwamiHost. A mismatch produces unmistakable capture evidence and an accessibility
    /// diagnostic; other patterns remain available for independent verification.
    @ViewBuilder
    private func verifiedInteractionDragView() -> some View {
        if Interaction_DragView.renderSignature == Self.interactionDragSignature {
            Interaction_DragView()
        } else {
            ZStack {
                Color.red.ignoresSafeArea()
                Text("Interaction Drag runtime-head mismatch")
                    .foregroundStyle(.white)
            }
            .accessibilityIdentifier("interaction-drag-runtime-head-mismatch")
        }
    }
}
