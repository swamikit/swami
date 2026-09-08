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
    @State private var translation: CGSize = .zero
    @State private var velocity: CGSize = .zero
    @State private var reset = false

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
                .position(x: artboardSize.width / 2, y: artboardSize.height / 2)
                .offset(position)
                .drag(enable: true, momentum: true, bounds: (.zero, dragBounds), position: $position, translation: $translation, velocity: $velocity, reset: reset)
        }
        .frame(width: artboardSize.width, height: artboardSize.height)
        .ignoresSafeArea(.all)
        .onAppear {
            position = .zero
            translation = .zero
            velocity = .zero
            reset = false
        }
        .onChange(of: position) { _, newValue in
            reset = (newValue == .zero)
        }
    }
}

#Preview {
    InteractionDragView()
}
