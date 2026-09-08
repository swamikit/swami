import SwiftUI

public struct InteractionDragView: View {
    public init() {}

    @State private var position: CGSize = .zero
    private let artboardColor = Color(red: 255/255, green: 43/255, blue: 79/255)
    private let cardColor = Color(red: 255/255, green: 211/255, blue: 180/255)
    private let cardSize = CGSize(width: 220, height: 140)
    private let artboardSize = CGSize(width: 888, height: 1212)

    public var body: some View {
        ZStack {
            artboardColor
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(cardColor)
                .frame(width: cardSize.width, height: cardSize.height)
                .position(x: artboardSize.width / 2, y: artboardSize.height / 2)
                .offset(position)
                .drag(momentum: true, bounds: dragBounds, position: $position, reset: position == .zero)
        }
        .frame(width: artboardSize.width, height: artboardSize.height)
        .ignoresSafeArea(.all)
        .onAppear { position = .zero }
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
}

#Preview { InteractionDragView() }
