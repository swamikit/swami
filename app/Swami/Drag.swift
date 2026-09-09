import Foundation
import SwiftUI

/// SwiftUI equivalent of Origami's **Drag** patch (`origami.Drag`).
///
/// Naming follows ADR-0010. The behavior mirrors the installed patch graph's
/// Add Momentum, Rubber Band Friction, Rubber Band Tension, Stick To Boundaries,
/// Reset Remaining Velocity on Touch Up, and Clip Position stages.
///
/// The defaults are decoded from Origami's typed input-port values rather than
/// borrowed from UIKit: Momentum Friction **8**, Rubber Band Friction **8**, and
/// Rubber Band Tension **100**.
public struct Drag: ViewModifier {
    var enable: Bool
    var momentum: Bool
    var bounds: (min: CGSize, max: CGSize)?
    var position: Binding<CGSize>?
    var translation: Binding<CGSize>?
    var velocity: Binding<CGSize>?
    var reset: Bool
    var momentumFriction: CGFloat
    var rubberBandFriction: CGFloat
    var rubberBandTension: CGFloat
    var onRelease: ((CGSize) -> Void)?

    @State private var origin: CGSize = .zero
    @State private var current: CGSize = .zero
    @State private var previousTranslation: CGSize = .zero
    @State private var previousSampleTime: Date?
    @State private var sampledVelocity: CGSize = .zero

    public func body(content: Content) -> some View {
        content
            .offset(current)
            .gesture(dragGesture, isEnabled: enable)
            // Origami's Reset input is a pulse. Treat either Bool edge as a new
            // pulse so repeated resets do not depend on returning a latch to false.
            .onChange(of: reset) { _, _ in
                sampledVelocity = .zero
                settle(to: .zero)
                origin = .zero
            }
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                if previousSampleTime == nil {
                    // Reset remaining velocity on every new touch-down.
                    origin = current
                    previousTranslation = value.translation
                    sampledVelocity = .zero
                } else if let previousSampleTime {
                    let elapsed = value.time.timeIntervalSince(previousSampleTime)
                    if elapsed > 0 {
                        sampledVelocity = CGSize(
                            width: (value.translation.width - previousTranslation.width) / elapsed,
                            height: (value.translation.height - previousTranslation.height) / elapsed
                        )
                    }
                    previousTranslation = value.translation
                }
                previousSampleTime = value.time

                let raw = CGSize(
                    width: origin.width + value.translation.width,
                    height: origin.height + value.translation.height
                )
                current = resist(raw)
                translation?.wrappedValue = value.translation
                position?.wrappedValue = current
                velocity?.wrappedValue = sampledVelocity
            }
            .onEnded { _ in
                previousSampleTime = nil
                translation?.wrappedValue = .zero
                velocity?.wrappedValue = sampledVelocity

                // Publish the Drag position at Interaction touch-up. This hook lets
                // a translated graph wire its separate Interaction → Pulse chain to
                // Reset without installing a second gesture recognizer.
                onRelease?(current)

                // Add Momentum integrates dv/dt = -friction*v, so remaining
                // displacement at touch-up is velocity / friction.
                let target = momentum
                    ? CGSize(width: current.width + sampledVelocity.width / momentumFriction,
                             height: current.height + sampledVelocity.height / momentumFriction)
                    : current
                let boundedTarget = clamp(target)
                settle(to: boundedTarget)
                origin = boundedTarget
                sampledVelocity = .zero
            }
    }

    /// Stick To Boundaries / Clip Position.
    private func clamp(_ size: CGSize) -> CGSize {
        guard let bounds else { return size }
        return CGSize(
            width: min(max(size.width, bounds.min.width), bounds.max.width),
            height: min(max(size.height, bounds.min.height), bounds.max.height)
        )
    }

    /// Rubber Band Friction. Origami's value 8 means one point of displayed
    /// over-travel for every eight points dragged beyond a boundary.
    private func resist(_ size: CGSize) -> CGSize {
        guard let bounds else { return size }
        func resisted(_ value: CGFloat, min: CGFloat, max: CGFloat) -> CGFloat {
            if value < min { return min - (min - value) / rubberBandFriction }
            if value > max { return max + (value - max) / rubberBandFriction }
            return value
        }
        return CGSize(
            width: resisted(size.width, min: bounds.min.width, max: bounds.max.width),
            height: resisted(size.height, min: bounds.min.height, max: bounds.max.height)
        )
    }

    /// Rubber Band Tension/Friction map directly to spring stiffness/damping.
    private func settle(to target: CGSize) {
        withAnimation(.interpolatingSpring(
            mass: 1,
            stiffness: rubberBandTension,
            damping: rubberBandFriction,
            initialVelocity: 0
        )) {
            current = target
            position?.wrappedValue = target
        }
    }
}

public extension View {
    /// Attach Origami-style **Drag**. Inputs and output bindings mirror the
    /// patch; physics defaults come from Origami's decoded Drag Settings.
    func drag(
        enable: Bool = true,
        momentum: Bool = true,
        bounds: (min: CGSize, max: CGSize)? = nil,
        position: Binding<CGSize>? = nil,
        translation: Binding<CGSize>? = nil,
        velocity: Binding<CGSize>? = nil,
        reset: Bool = false,
        momentumFriction: CGFloat = 8,
        rubberBandFriction: CGFloat = 8,
        rubberBandTension: CGFloat = 100,
        onRelease: ((CGSize) -> Void)? = nil
    ) -> some View {
        modifier(Drag(
            enable: enable,
            momentum: momentum,
            bounds: bounds,
            position: position,
            translation: translation,
            velocity: velocity,
            reset: reset,
            momentumFriction: momentumFriction,
            rubberBandFriction: rubberBandFriction,
            rubberBandTension: rubberBandTension,
            onRelease: onRelease
        ))
    }
}
