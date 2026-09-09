import SwiftUI
import Foundation
import Swami

// The pattern currently under verification. CI drives which one by setting SWAMI_PATTERN;
// the loop adds a `case "<slug>"` per pattern as they're translated. Keep the body a single
// expression so screenshots are 1:1 with the Origami artboard — no host chrome, no nav bar.
struct ContentView: View {
    private static let interactionDragRevision = "interaction-drag-r140-canvas-card-v7"

    var body: some View {
        switch ProcessInfo.processInfo.environment["SWAMI_PATTERN"] {
        case "touch", nil: TouchOrigamiExampleView()
        case "drag":       verifiedInteractionDragView()
        default:           TouchOrigamiExampleView()   // add cases as patterns land
        }
    }

    /// Validate the revision stored in the linked Swami.framework bundle. Unlike a
    /// source marker compiled into both targets, this proves which built framework was
    /// installed. The first Drag launch is the unmodified fidelity-screenshot path.
    @ViewBuilder
    private func verifiedInteractionDragView() -> some View {
        if Interaction_DragView.builtProductRevision == Self.interactionDragRevision {
            if InteractionEvidenceSession.showsTouchIndicator {
                Interaction_DragView()
                    .modifier(InteractionEvidenceTouchIndicator())
            } else {
                Interaction_DragView()
            }
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

/// The verify runner installs a fresh host, launches Drag once for its still capture,
/// then terminates and launches it again for the H.264 recording. Persisting that first
/// launch keeps evidence UI completely outside the fidelity-screenshot render path.
private enum InteractionEvidenceSession {
    private static let completedStillCaptureKey = "InteractionDragCompletedStillCaptureV7"

    static let showsTouchIndicator: Bool = {
        guard ProcessInfo.processInfo.environment["SWAMI_PATTERN"] == "drag" else {
            return false
        }
        let defaults = UserDefaults.standard
        if defaults.bool(forKey: completedStillCaptureKey) {
            return true
        }
        defaults.set(true, forKey: completedStillCaptureKey)
        return false
    }()
}

/// Capture-only gesture evidence. It is selected only for the runner's second Drag
/// launch, so the Swami screenshot and the translated pattern contain no cursor UI.
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
