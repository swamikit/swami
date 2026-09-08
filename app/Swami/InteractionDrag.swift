import SwiftUI

public struct InteractionDragView: View {
    public init() {}

    @State private var position: CGSize = .zero
    @State private var restingPosition: CGSize = .zero
    @GestureState private var isDragging = false

    private let artboardSize = CGSize(width: 888, height: 1212)
    private let cardSize = CGSize(width: 220, height: 140)
    private let artboardColor = Color(red: 255/255.0, green: 43/255.0, blue: 79/255.0)
    private let cardColor = Color(red: 255/255.0, green: 211/255.0, blue: 180/255.0)

    public var body: some View {
        ZStack {
            artboardColor
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(cardColor)
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
        }
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .updating($isDragging) { _, state, _ in state = true }
            .onChanged { value in
                if !isDragging {
                    restingPosition = position
                }
                let translation = value.translation
                let projected = CGSize(
                    width: restingPosition.width + translation.width,
                    height: restingPosition.height + translation.height
                )
                position = clamp(projected)
            }
            .onEnded { value in
                let translation = value.predictedEndTranslation
                let projected = CGSize(
                    width: restingPosition.width + translation.width,
                    height: restingPosition.height + translation.height
                )
                withAnimation(.interpolatingSpring(stiffness: 180, damping: 22)) {
                    position = clamp(projected)
                    restingPosition = position
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
}

#Preview { InteractionDragView() }
