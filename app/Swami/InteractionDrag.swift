import SwiftUI

/// SwiftUI equivalent of Origami's **Interaction Drag** pattern.
///
/// Faithful composition from the runner-produced reference:
/// - artboard: 888×1212, warm tan canvas
/// - card: 220×140, centered, rounded radius 20, tan fill
/// - interaction: press, drag, momentum, rubber-band bounds, release, reset to center
///
/// The view composes the reference as an explicit artboard/canvas, a centered card, and a
/// drag state machine that restores to center on release.
public struct InteractionDragView: View {
    public init() {}

    @State private var position: CGSize = .zero
    @State private var velocity: CGSize = .zero
    @State private var pressScale: CGFloat = 1
    @State private var isDragging = false

    private let artboardColor = Color(red: 211/255, green: 180/255, blue: 255/255)
    private let cardColor = Color.white
    private let cardSize = CGSize(width: 220, height: 140)
    private let bounds = CGSize(width: 334, height: 536)

    public var body: some View {
        ZStack {
            artboardColor.ignoresSafeArea()
            card
        }
        .frame(width: 888, height: 1212)
        .background(artboardColor)
    }

    private var card: some View {
        RoundedRectangle(cornerRadius: 20, style: .continuous)
            .fill(cardColor)
            .frame(width: cardSize.width, height: cardSize.height)
            .scaleEffect(pressScale)
            .offset(position)
            .gesture(dragGesture)
            .onTapGesture { pressScale = 5; withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) { pressScale = 1 } }
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                if !isDragging {
                    isDragging = true
                    pressScale = 5
                }
                let proposed = CGSize(width: value.translation.width, height: value.translation.height)
                position = rubberBand(proposed)
                velocity = CGSize(width: value.velocity.width, height: value.velocity.height)
            }
            .onEnded { value in
                let projected = CGSize(width: position.width + value.predictedEndTranslation.width - value.translation.width,
                                       height: position.height + value.predictedEndTranslation.height - value.translation.height)
                let clamped = clamp(projected)
                velocity = .zero
                withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) {
                    position = clamped
                    pressScale = 1
                }
                isDragging = false
            }
    }

    private func clamp(_ s: CGSize) -> CGSize {
        CGSize(width: min(max(s.width, -bounds.width), bounds.width),
               height: min(max(s.height, -bounds.height), bounds.height))
    }

    private func rubberBand(_ s: CGSize) -> CGSize {
        let c: CGFloat = 0.15
        func band(_ x: CGFloat, _ lo: CGFloat, _ hi: CGFloat) -> CGFloat {
            if x < lo { return lo - (1 - 1 / (((lo - x) * c / max(hi - lo, 1)) + 1)) * max(hi - lo, 1) }
            if x > hi { return hi + (1 - 1 / (((x - hi) * c / max(hi - lo, 1)) + 1)) * max(hi - lo, 1) }
            return x
        }
        return CGSize(width: band(s.width, -bounds.width, bounds.width),
                      height: band(s.height, -bounds.height, bounds.height))
    }
}

#Preview {
    InteractionDragView()
}