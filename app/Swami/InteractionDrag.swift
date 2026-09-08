import SwiftUI

/// SwiftUI equivalent of Origami's **Interaction Drag** pattern.
///
/// Faithful composition from the runner-produced reference:
/// - artboard: 888×1212, full-bleed warm purple canvas with no chrome
/// - card: 220×140, centered, rounded radius 20, white fill
/// - interaction: press, drag, momentum, rubber-band bounds, release, reset to center
///
/// The view composes the reference as an explicit artboard/canvas, a centered card, and a
/// drag state machine that restores to center on release.
public struct InteractionDragView: View {
    public init() {}

    @State private var position: CGSize = .zero
    @State private var dragAnchor: CGSize = .zero
    @State private var pressScale: CGFloat = 1
    @State private var isPressed = false

    private let artboardColor = Color(red: 211/255, green: 180/255, blue: 255/255)
    private let cardColor = Color.white
    private let cardSize = CGSize(width: 220, height: 140)
    private let artboardSize = CGSize(width: 888, height: 1212)
    private let dragBounds = CGSize(width: 334, height: 536)

    public var body: some View {
        ZStack {
            artboardColor.ignoresSafeArea()
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(cardColor)
                .frame(width: cardSize.width, height: cardSize.height)
                .scaleEffect(pressScale)
                .position(x: artboardSize.width / 2 + position.width, y: artboardSize.height / 2 + position.height)
                .gesture(dragGesture)
        }
        .frame(width: artboardSize.width, height: artboardSize.height)
        .background(artboardColor)
        .ignoresSafeArea(.all)
        .onAppear {
            position = .zero
            dragAnchor = .zero
        }
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                if !isPressed {
                    isPressed = true
                    pressScale = 5
                    dragAnchor = position
                }
                let proposed = CGSize(
                    width: dragAnchor.width + value.translation.width,
                    height: dragAnchor.height + value.translation.height
                )
                position = rubberBand(proposed)
            }
            .onEnded { value in
                let projected = CGSize(
                    width: dragAnchor.width + value.predictedEndTranslation.width,
                    height: dragAnchor.height + value.predictedEndTranslation.height
                )
                withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) {
                    position = clamp(projected)
                    pressScale = 1
                }
                dragAnchor = position
                isPressed = false
            }
    }

    private func clamp(_ s: CGSize) -> CGSize {
        CGSize(
            width: min(max(s.width, -dragBounds.width), dragBounds.width),
            height: min(max(s.height, -dragBounds.height), dragBounds.height)
        )
    }

    private func rubberBand(_ s: CGSize) -> CGSize {
        let c: CGFloat = 0.15
        func band(_ x: CGFloat, _ lo: CGFloat, _ hi: CGFloat) -> CGFloat {
            if x < lo { return lo - (1 - 1 / (((lo - x) * c / max(hi - lo, 1)) + 1)) * max(hi - lo, 1) }
            if x > hi { return hi + (1 - 1 / (((x - hi) * c / max(hi - lo, 1)) + 1)) * max(hi - lo, 1) }
            return x
        }
        return CGSize(
            width: band(s.width, -dragBounds.width, dragBounds.width),
            height: band(s.height, -dragBounds.height, dragBounds.height)
        )
    }
}

#Preview {
    InteractionDragView()
}
