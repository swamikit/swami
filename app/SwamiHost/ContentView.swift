import SwiftUI
import Foundation
import Swami

// The pattern currently under verification. CI drives which one by setting SWAMI_PATTERN;
// the loop adds a `case "<slug>"` per pattern as they're translated. Keep the body a single
// expression so screenshots are 1:1 with the Origami artboard — no host chrome, no nav bar.
struct ContentView: View {
    private static let interactionDragSignature = "interaction-drag-r140-canvas-card-v6"

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
                .modifier(InteractionEvidenceTouchIndicator())
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

/// Runner-only gesture evidence. This modifier lives in SwamiHost rather than the
/// translated pattern, so screenshots remain pixel-identical at rest while recordings
/// expose touch-down, the injected drag trajectory, and release.
private struct InteractionEvidenceTouchIndicator: ViewModifier {
    @GestureState private var location: CGPoint? = nil

    func body(content: Content) -> some View {
        ZStack {
            content

            if let location {
                Circle()
                    .fill(.white.opacity(0.85))
                    .overlay {
                        Circle().stroke(.black.opacity(0.65), lineWidth: 1)
                    }
                    .frame(width: 18, height: 18)
                    .position(location)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
        .simultaneousGesture(
            DragGesture(minimumDistance: 0, coordinateSpace: .global)
                .updating($location) { value, location, _ in
                    location = value.location
                }
        )
    }
}
