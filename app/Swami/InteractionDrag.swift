import SwiftUI

public struct InteractionDragView: View {
    public init() {}

    @State private var position: CGSize = .zero
    @State private var restingPosition: CGSize = .zero
    @State private var isPressed = false
    private let artboardSize = CGSize(width: 888, height: 1212)
    private let cardSize = CGSize(width: 220, height: 140)
    private let artboardColor = Color(red: 255/255.0, green: 19/255.0, blue: 52/255.0)
    private let artboardHighlight = Color(red: 255/255.0, green: 43/255.0, blue: 79/255.0)
    private let cardColor = Color(red: 255/255.0, green: 211/255.0, blue: 180/255.0)

    public var body: some View {
        ZStack {
            artboardColor
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(isPressed ? artboardHighlight.opacity(0.92) : cardColor)
                .frame(width: cardSize.width, height: cardSize.height)
                .offset(position)
                .position(x: artboardSize.width / 2, y: artboardSize.height / 2)
                .gesture(dragGesture)
        }
        .frame(width: artboardSize.width, height: artboardSize.height)
        .ignoresSafeArea(.all)
        .onAppear {
            position = .zero
            restingPosition = .zero
            isPressed = false
        }
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                isPressed = true
                let projected = CGSize(
                    width: restingPosition.width + value.translation.width,
                    height: restingPosition.height + value.translation.height
                )
                position = rubberBand(projected)
            }
            .onEnded { value in
                isPressed = false
                let projected = CGSize(
                    width: restingPosition.width + value.predictedEndTranslation.width,
                    height: restingPosition.height + value.predictedEndTranslation.height
                )
                let settled = clamp(projected)
                withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) {
                    position = settled
                    restingPosition = settled
                }
            }
    }

    private var dragBounds: (min: CGSize, max: CGSize) {
        let halfW = cardSize.width / 2
        let halfH = cardSize.height / 2
        let artHalfW = artboardSize.width / 2
        let artHalfH = artboardSize.height / 2
        return (
            min: CGSize(width: -(artHalfW - halfW), height: -(artHalfH - halfH)),
            max: CGSize(width: artHalfW - halfW, height: artHalfH - halfH)
        )
    }

    private func clamp(_ position: CGSize) -> CGSize {
        CGSize(
            width: min(max(position.width, dragBounds.min.width), dragBounds.max.width),
            height: min(max(position.height, dragBounds.min.height), dragBounds.max.height)
        )
    }

    private func rubberBand(_ position: CGSize) -> CGSize {
        func band(_ value: CGFloat, _ lo: CGFloat, _ hi: CGFloat) -> CGFloat {
            if value < lo { return lo - (lo - value) * 0.15 }
            if value > hi { return hi + (value - hi) * 0.15 }
            return value
        }
        return CGSize(
            width: band(position.width, dragBounds.min.width, dragBounds.max.width),
            height: band(position.height, dragBounds.min.height, dragBounds.max.height)
        )
    }
}

#Preview { InteractionDragView() }
