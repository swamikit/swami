import SwiftUI

/// SwiftUI equivalent of Origami's **Interaction** patch.
///
/// Naming (ADR-0010): helpers are named after the Origami *patch*, bare (no prefix) —
/// disambiguate with the module (`OrigamiPatterns.Interaction`) if it ever collides. This one
/// doesn't clash with anything in SwiftUI.
///
/// Exposes the Interaction patch's output ports as bindings/callbacks so downstream SwiftUI
/// composes off them, matching the graph:
/// - `down` — `true` while a finger is on the layer,
/// - `position` — the touch point, in the layer's coordinate space,
/// - `onTap` / `onDoubleTap` / `onLongPress` — discrete pulses.
///
/// Only the gesture for an output you actually request is attached — so a tap-only layer
/// carries only a tap recognizer (no stray drag), which keeps gesture arbitration clean.
public struct Interaction: ViewModifier {
    var down: Binding<Bool>?
    var position: Binding<CGPoint?>?
    var onTap: (() -> Void)?
    var onDoubleTap: (() -> Void)?
    var onLongPress: (() -> Void)?

    public func body(content: Content) -> some View {
        content
            .contentShape(Rectangle())
            .modifier(DragOutput(down: down, position: position))
            .modifier(TapOutput(position: position, action: onTap, count: 1))
            .modifier(TapOutput(position: position, action: onDoubleTap, count: 2))
            .modifier(LongPressOutput(action: onLongPress))
    }
}

private struct DragOutput: ViewModifier {
    var down: Binding<Bool>?
    var position: Binding<CGPoint?>?
    @ViewBuilder func body(content: Content) -> some View {
        if down != nil {   // "Down" is what needs a continuous drag recognizer
            content.gesture(
                DragGesture(minimumDistance: 0, coordinateSpace: .local)
                    .onChanged { v in down?.wrappedValue = true; position?.wrappedValue = v.location }
                    .onEnded { _ in down?.wrappedValue = false }
            )
        } else {
            content
        }
    }
}

private struct TapOutput: ViewModifier {
    var position: Binding<CGPoint?>?
    var action: (() -> Void)?
    var count: Int
    @ViewBuilder func body(content: Content) -> some View {
        if let action {
            content.gesture(
                SpatialTapGesture(count: count, coordinateSpace: .local)
                    .onEnded { v in position?.wrappedValue = v.location; action() }
            )
        } else {
            content
        }
    }
}

private struct LongPressOutput: ViewModifier {
    var action: (() -> Void)?
    @ViewBuilder func body(content: Content) -> some View {
        if let action {
            content.gesture(LongPressGesture(minimumDuration: 0.3).onEnded { _ in action() })
        } else {
            content
        }
    }
}

public extension View {
    /// Attach Origami-style **Interaction** outputs. Pass only the outputs you need; each maps
    /// to an Interaction output port, and only its gesture is attached.
    func interaction(
        down: Binding<Bool>? = nil,
        position: Binding<CGPoint?>? = nil,
        onTap: (() -> Void)? = nil,
        onDoubleTap: (() -> Void)? = nil,
        onLongPress: (() -> Void)? = nil
    ) -> some View {
        modifier(Interaction(
            down: down, position: position,
            onTap: onTap, onDoubleTap: onDoubleTap, onLongPress: onLongPress
        ))
    }
}
