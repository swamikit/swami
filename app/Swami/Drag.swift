import SwiftUI

/// SwiftUI equivalent of Origami's **Drag** patch (`origami.Drag`).
///
/// Naming follows ADR-0010. The helper is based on the patch graph in Origami's
/// installed catalog: interaction supplies translation, projected translation supplies
/// momentum, the configured boundaries clip position, and out-of-range input receives
/// rubber-band resistance before release.
///
/// Faithful ports (from the patch's group I/O):
/// - inputs → `enable`, `momentum`, `bounds`, `start`, `reset`
/// - outputs → `position`, `translation`, `velocity`
///
/// Reset policy remains outside this helper: graph composition pulses the faithful
/// `reset` input, just as a patch connected to Drag's Reset port does in Origami. The
/// `resetCount` adapter gives every pulse a distinct identity when the graph can fire
/// repeatedly; the Boolean input remains available for direct level-to-pulse wiring.
/// Rubber-band friction uses Origami's documented default of `0.15`. Momentum uses
/// SwiftUI's gesture projection rather than an iOS scroll default; this preserves the
/// gesture's measured direction and magnitude before the bounded spring settles it.
public struct Drag: ViewModifier {
    var enable: Bool
    var momentum: Bool
    /// Clip bounds for Position (Origami “Start/End Boundary” / “Min”/“Max”). nil = unbounded.
    var bounds: (min: CGSize, max: CGSize)?
    /// Initial position and the destination of an explicit `reset` pulse.
    /// Runtime changes do not move an active or settled drag.
    var start: CGSize
    var position: Binding<CGSize>?
    var translation: Binding<CGSize>?
    var velocity: Binding<CGSize>?
    var reset: Bool
    /// Monotonic pulse identity for graph branches that can fire more than once.
    var resetCount: UInt

    @State private var origin: CGSize = .zero
    @State private var current: CGSize = .zero
    @State private var gestureIsActive = false

    public func body(content: Content) -> some View {
        content
            .offset(current)
            .gesture(dragGesture, isEnabled: enable)
            .onAppear {
                origin = start
                current = start
                position?.wrappedValue = start
            }
            .onChange(of: reset) { _, requested in
                if requested {
                    performReset()
                }
            }
            .onChange(of: resetCount) { _, _ in
                performReset()
            }
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                if !gestureIsActive {
                    gestureIsActive = true
                    // Each touch begins from the visible settled position. This is
                    // required after reset and prevents stale momentum or origin state
                    // from leaking into a later gesture.
                    origin = current
                    translation?.wrappedValue = .zero
                    velocity?.wrappedValue = .zero
                }
                let raw = CGSize(
                    width: origin.width + value.translation.width,
                    height: origin.height + value.translation.height
                )
                current = resist(raw)
                translation?.wrappedValue = value.translation
                position?.wrappedValue = current
            }
            .onEnded { value in
                gestureIsActive = false
                let measuredVelocity = CGSize(
                    width: value.predictedEndTranslation.width - value.translation.width,
                    height: value.predictedEndTranslation.height - value.translation.height
                )
                velocity?.wrappedValue = measuredVelocity

                let projected = momentum
                    ? CGSize(
                        width: origin.width + value.predictedEndTranslation.width,
                        height: origin.height + value.predictedEndTranslation.height
                    )
                    : current
                settle(to: clamp(projected))
            }
    }

    private func clamp(_ value: CGSize) -> CGSize {
        guard let bounds else { return value }
        return CGSize(
            width: min(max(value.width, bounds.min.width), bounds.max.width),
            height: min(max(value.height, bounds.min.height), bounds.max.height)
        )
    }

    private func resist(_ value: CGSize) -> CGSize {
        guard let bounds else { return value }
        func rubberBand(_ component: CGFloat, _ lower: CGFloat, _ upper: CGFloat) -> CGFloat {
            if component < lower {
                return lower - band(lower - component, span: max(upper - lower, 1))
            }
            if component > upper {
                return upper + band(component - upper, span: max(upper - lower, 1))
            }
            return component
        }
        return CGSize(
            width: rubberBand(value.width, bounds.min.width, bounds.max.width),
            height: rubberBand(value.height, bounds.min.height, bounds.max.height)
        )
    }

    private func band(_ overshoot: CGFloat, span: CGFloat, friction: CGFloat = 0.15) -> CGFloat {
        (1 - (1 / ((overshoot * friction / span) + 1))) * span
    }

    private func performReset() {
        translation?.wrappedValue = .zero
        velocity?.wrappedValue = .zero
        settle(to: start)
    }

    private func settle(to target: CGSize) {
        origin = target
        withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) {
            current = target
            position?.wrappedValue = target
        }
    }
}

public extension View {
    func drag(
        enable: Bool = true,
        momentum: Bool = true,
        bounds: (min: CGSize, max: CGSize)? = nil,
        start: CGSize = .zero,
        position: Binding<CGSize>? = nil,
        translation: Binding<CGSize>? = nil,
        velocity: Binding<CGSize>? = nil,
        reset: Bool = false,
        resetCount: UInt = 0
    ) -> some View {
        modifier(Drag(
            enable: enable,
            momentum: momentum,
            bounds: bounds,
            start: start,
            position: position,
            translation: translation,
            velocity: velocity,
            reset: reset,
            resetCount: resetCount
        ))
    }
}
