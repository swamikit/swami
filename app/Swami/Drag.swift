import SwiftUI

/// Testable state graph behind ``Drag``.
struct DragState: Equatable {
    /// The configured rest position. A completed gesture never mutates it.
    private(set) var start: CGSize
    private(set) var origin: CGSize
    private(set) var current: CGSize
    private(set) var translation: CGSize = .zero
    private(set) var velocity: CGSize = .zero
    private(set) var gestureIsActive = false

    init(start: CGSize) {
        self.start = start
        origin = start
        current = start
    }

    mutating func change(
        translation newTranslation: CGSize,
        start configuredStart: CGSize,
        bounds: (min: CGSize, max: CGSize)?,
        rubberBandFriction: CGFloat
    ) {
        if !gestureIsActive {
            gestureIsActive = true
            // Origami Drag starts every interaction from its current Start input. Do
            // not promote the previous momentum endpoint into the next gesture's origin.
            start = configuredStart
            origin = configuredStart
            current = configuredStart
            translation = .zero
            velocity = .zero
        }
        translation = newTranslation
        let raw = CGSize(
            width: origin.width + newTranslation.width,
            height: origin.height + newTranslation.height
        )
        current = Self.resist(raw, bounds: bounds, friction: rubberBandFriction)
    }

    mutating func end(
        releaseTranslation: CGSize,
        predictedEndTranslation: CGSize,
        momentum: Bool,
        bounds: (min: CGSize, max: CGSize)?,
        rubberBandFriction: CGFloat
    ) -> (releasedPosition: CGSize, target: CGSize) {
        // The end payload is the authoritative final sample. Derive release position,
        // translation, and velocity together instead of replaying a change event.
        let releasedRaw = CGSize(
            width: origin.width + releaseTranslation.width,
            height: origin.height + releaseTranslation.height
        )
        current = Self.resist(
            releasedRaw,
            bounds: bounds,
            friction: rubberBandFriction
        )
        translation = releaseTranslation
        velocity = CGSize(
            width: predictedEndTranslation.width - releaseTranslation.width,
            height: predictedEndTranslation.height - releaseTranslation.height
        )
        gestureIsActive = false

        let projected = momentum
            ? CGSize(
                width: origin.width + predictedEndTranslation.width,
                height: origin.height + predictedEndTranslation.height
            )
            : current
        return (current, Self.clamp(projected, bounds: bounds))
    }

    mutating func settle(at target: CGSize) {
        current = target
    }

    mutating func reset(to start: CGSize) {
        self.start = start
        origin = start
        current = start
        translation = .zero
        velocity = .zero
        gestureIsActive = false
    }

    private static func clamp(
        _ value: CGSize,
        bounds: (min: CGSize, max: CGSize)?
    ) -> CGSize {
        guard let bounds else { return value }
        return CGSize(
            width: min(max(value.width, bounds.min.width), bounds.max.width),
            height: min(max(value.height, bounds.min.height), bounds.max.height)
        )
    }

    private static func resist(
        _ value: CGSize,
        bounds: (min: CGSize, max: CGSize)?,
        friction: CGFloat
    ) -> CGSize {
        guard let bounds else { return value }
        func band(_ overshoot: CGFloat, span: CGFloat) -> CGFloat {
            (1 - (1 / ((overshoot * friction / span) + 1))) * span
        }
        func component(_ value: CGFloat, lower: CGFloat, upper: CGFloat) -> CGFloat {
            let span = max(upper - lower, 1)
            if value < lower { return lower - band(lower - value, span: span) }
            if value > upper { return upper + band(value - upper, span: span) }
            return value
        }
        return CGSize(
            width: component(value.width, lower: bounds.min.width, upper: bounds.max.width),
            height: component(value.height, lower: bounds.min.height, upper: bounds.max.height)
        )
    }
}

/// SwiftUI equivalent of Origami's **Drag** patch (`origami.Drag`).
///
/// Faithful ports: inputs `enable`, `momentum`, `bounds`, `start`, `reset`;
/// outputs `position`, `translation`, `velocity`. Reset policy remains in the
/// consumer graph. `resetCount` is a monotonic pulse input: every changed value
/// performs one reset, including consecutive pulses for which a Boolean input would
/// remain `true`. The count need not start at zero and wrapping is permitted.
///
/// Rubber-band friction defaults to Origami Drag's documented `0.15`. Consumers
/// can override the input when a placed graph supplies a different value.
public struct Drag: ViewModifier {
    var enable: Bool
    var momentum: Bool
    var bounds: (min: CGSize, max: CGSize)?
    var start: CGSize
    var rubberBandFriction: CGFloat
    var position: Binding<CGSize>?
    var translation: Binding<CGSize>?
    var velocity: Binding<CGSize>?
    var reset: Bool
    var resetCount: UInt
    var onRelease: ((CGSize) -> Void)?

    @State private var state: DragState

    init(
        enable: Bool,
        momentum: Bool,
        bounds: (min: CGSize, max: CGSize)?,
        start: CGSize,
        rubberBandFriction: CGFloat,
        position: Binding<CGSize>?,
        translation: Binding<CGSize>?,
        velocity: Binding<CGSize>?,
        reset: Bool,
        resetCount: UInt,
        onRelease: ((CGSize) -> Void)?
    ) {
        self.enable = enable
        self.momentum = momentum
        self.bounds = bounds
        self.start = start
        self.rubberBandFriction = rubberBandFriction
        self.position = position
        self.translation = translation
        self.velocity = velocity
        self.reset = reset
        self.resetCount = resetCount
        self.onRelease = onRelease
        _state = State(initialValue: DragState(start: start))
    }

    public func body(content: Content) -> some View {
        content
            .offset(state.current)
            .gesture(dragGesture, isEnabled: enable)
            .onChange(of: reset) { _, requested in
                if requested { performReset() }
            }
            .onChange(of: resetCount) { previous, current in
                if Self.isNewResetPulse(previous: previous, current: current) {
                    performReset()
                }
            }
    }

    /// Kept as a pure predicate so repeated pulse semantics are covered without
    /// coupling tests to SwiftUI's view-update scheduler.
    static func isNewResetPulse(previous: UInt, current: UInt) -> Bool {
        previous != current
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                state.change(
                    translation: value.translation,
                    start: start,
                    bounds: bounds,
                    rubberBandFriction: rubberBandFriction
                )
                translation?.wrappedValue = state.translation
                velocity?.wrappedValue = state.velocity
                position?.wrappedValue = state.current
            }
            .onEnded { value in
                let release = state.end(
                    releaseTranslation: value.translation,
                    predictedEndTranslation: value.predictedEndTranslation,
                    momentum: momentum,
                    bounds: bounds,
                    rubberBandFriction: rubberBandFriction
                )
                translation?.wrappedValue = state.translation
                velocity?.wrappedValue = state.velocity
                position?.wrappedValue = release.releasedPosition
                onRelease?(release.releasedPosition)
                withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) {
                    state.settle(at: release.target)
                    position?.wrappedValue = release.target
                }
            }
    }

    private func performReset() {
        withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) {
            state.reset(to: start)
            position?.wrappedValue = state.current
            translation?.wrappedValue = state.translation
            velocity?.wrappedValue = state.velocity
        }
    }
}

public extension View {
    func drag(
        enable: Bool = true,
        momentum: Bool = true,
        bounds: (min: CGSize, max: CGSize)? = nil,
        start: CGSize = .zero,
        rubberBandFriction: CGFloat = 0.15,
        position: Binding<CGSize>? = nil,
        translation: Binding<CGSize>? = nil,
        velocity: Binding<CGSize>? = nil,
        reset: Bool = false,
        resetCount: UInt = 0,
        onRelease: ((CGSize) -> Void)? = nil
    ) -> some View {
        modifier(Drag(
            enable: enable,
            momentum: momentum,
            bounds: bounds,
            start: start,
            rubberBandFriction: rubberBandFriction,
            position: position,
            translation: translation,
            velocity: velocity,
            reset: reset,
            resetCount: resetCount,
            onRelease: onRelease
        ))
    }
}
