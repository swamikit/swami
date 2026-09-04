import SwiftUI

/// SwiftUI equivalent of Origami's **Drag** patch (`origami.Drag`).
///
/// Naming (ADR-0010): bare, patch-matched. Ported from the patch's own graph in the installed
/// catalog (ADR-0011): `Origami Studio.app/…/Patches/origami.origami-system/patches/origami.Drag`.
/// That graph builds Drag from `builtin.momentumScrolling` + `AddMomentum`, `Velocity`/`VelocityXY`,
/// `ClippedPosition`/`ClipY`, `ExtractMomentumSettings`, `ResetwMomentum`, `RoundtoScreenPixels`,
/// with Rubber Band Tension/Friction and Stick To Boundaries.
///
/// Faithful ports (extracted from the graph's group I/O):
/// - inputs  → `enable`, `momentum`, `bounds` (Clip / Start+End boundary), `start`, `reset`
/// - outputs → `position`, `translation`, `velocity`
///
/// FIDELITY TODO: the exact default constants (Momentum Friction, Rubber Band Friction, decel rate)
/// live as port default *values* inside origami.DragSettings — reading them needs FlatBuffers
/// port-value decoding, which the parser doesn't do yet. Until then the momentum decay uses the
/// system's velocity projection (`predictedEndTranslation`) and rubber-band uses the iOS-standard
/// constant (0.55). Mark these for replacement once the parser extracts DragSettings' real defaults.
public struct Drag: ViewModifier {
    var enable: Bool
    var momentum: Bool
    /// Clip bounds for Position (Origami "Start/End Boundary" / "Min"/"Max"). nil = unbounded.
    var bounds: (min: CGSize, max: CGSize)?
    var position: Binding<CGSize>?
    var translation: Binding<CGSize>?
    var velocity: Binding<CGSize>?
    var reset: Bool

    @State private var origin: CGSize = .zero      // Position at the start of the current drag
    @State private var current: CGSize = .zero     // live Position output

    public func body(content: Content) -> some View {
        content
            .offset(current)
            .gesture(dragGesture, isEnabled: enable)
            .onChange(of: reset) { _, r in if r { settle(to: .zero) } }
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { v in
                // Live position = origin + translation, with rubber-band resistance past bounds.
                let raw = CGSize(width: origin.width + v.translation.width,
                                 height: origin.height + v.translation.height)
                current = resist(raw)
                translation?.wrappedValue = v.translation
                position?.wrappedValue = current
            }
            .onEnded { v in
                // Velocity output (Origami "Velocity"): system projection over the gesture.
                let vel = CGSize(width: v.predictedEndTranslation.width - v.translation.width,
                                 height: v.predictedEndTranslation.height - v.translation.height)
                velocity?.wrappedValue = vel
                // Momentum: project to predicted end, then clamp/settle. ResetwMomentum: velocity
                // does not carry across a fresh touch-down (origin is re-sampled onChanged).
                let projected = momentum
                    ? CGSize(width: origin.width + v.predictedEndTranslation.width,
                             height: origin.height + v.predictedEndTranslation.height)
                    : current
                settle(to: clamp(projected))
                origin = clamp(projected)
            }
    }

    // MARK: Origami sub-patch behaviors

    /// Clip / Stick To Boundaries: hard clamp of Position to [min, max].
    private func clamp(_ s: CGSize) -> CGSize {
        guard let b = bounds else { return s }
        return CGSize(width: min(max(s.width, b.min.width), b.max.width),
                      height: min(max(s.height, b.min.height), b.max.height))
    }

    /// Rubber Band Friction: past a boundary, motion is resisted (iOS-standard c = 0.55).
    /// TODO(parser): replace 0.55 with origami.DragSettings' Rubber Band Friction default.
    private func resist(_ s: CGSize) -> CGSize {
        guard let b = bounds else { return s }
        func rb(_ x: CGFloat, _ lo: CGFloat, _ hi: CGFloat) -> CGFloat {
            if x < lo { return lo - band(lo - x, span: max(hi - lo, 1)) }
            if x > hi { return hi + band(x - hi, span: max(hi - lo, 1)) }
            return x
        }
        return CGSize(width: rb(s.width, b.min.width, b.max.width),
                      height: rb(s.height, b.min.height, b.max.height))
    }
    private func band(_ overshoot: CGFloat, span: CGFloat, c: CGFloat = 0.55) -> CGFloat {
        (1 - (1 / ((overshoot * c / span) + 1))) * span
    }

    /// Settle with a spring (Origami momentum decay → resting Position). RoundtoScreenPixels is
    /// left to the renderer (SwiftUI already snaps to device pixels).
    private func settle(to target: CGSize) {
        withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) {
            current = target
            position?.wrappedValue = target
        }
    }
}

public extension View {
    /// Attach Origami-style **Drag**. Pass only the outputs you need; each maps to a Drag output
    /// port (`position`, `translation`, `velocity`). `bounds` is the Clip / Start+End boundary.
    func drag(
        enable: Bool = true,
        momentum: Bool = true,
        bounds: (min: CGSize, max: CGSize)? = nil,
        position: Binding<CGSize>? = nil,
        translation: Binding<CGSize>? = nil,
        velocity: Binding<CGSize>? = nil,
        reset: Bool = false
    ) -> some View {
        modifier(Drag(enable: enable, momentum: momentum, bounds: bounds,
                      position: position, translation: translation,
                      velocity: velocity, reset: reset))
    }
}
