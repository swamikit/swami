import SwiftUI

/// SwiftUI equivalent of Origami's **Interaction Drag** pattern.
///
/// Faithful composition from the runner-produced reference:
/// - artboard: 888×1212, saturated purple background
/// - card: 220×140, centered, rounded radius 20, white fill
/// - interaction: press, drag, momentum, rubber-band bounds, release, reset to center
///
/// This pattern intentionally keeps the composition explicit instead of hiding it behind the
/// generic `drag()` helper so the deliverable matches the exact Origami reference layout.
public struct InteractionDragView: View {
    public init() {}

    @State private var position: CGSize = .zero
    @State private var velocity: CGSize = .zero
    @State private var isDragging = false
    @State private var resetToken = false

    private let artboardColor = Color(hex: "#DD70DF")
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
        .clipped()
    }

    private var card: some View {
        RoundedRectangle(cornerRadius: 20, style: .continuous)
            .fill(cardColor)
            .frame(width: cardSize.width, height: cardSize.height)
            .overlay(alignment: .topLeading) { dragMetrics }
            .offset(position)
            .gesture(dragGesture)
            .shadow(color: .black.opacity(0.05), radius: 8, x: 0, y: 4)
    }

    private var dragMetrics: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Interaction Drag")
                .font(.system(size: 18, weight: .semibold))
            Text(isDragging ? "press + drag" : "release + reset")
                .font(.system(size: 13, weight: .medium))
        }
        .foregroundStyle(Color.black.opacity(0.18))
        .padding(16)
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 0, coordinateSpace: .local)
            .onChanged { value in
                if !isDragging {
                    isDragging = true
                    resetToken.toggle()
                }
                position = clamped(CGSize(width: value.translation.width,
                                          height: value.translation.height))
                velocity = CGSize(width: value.velocity.width, height: value.velocity.height)
            }
            .onEnded { value in
                let projected = CGSize(width: position.width + value.predictedEndTranslation.width - value.translation.width,
                                       height: position.height + value.predictedEndTranslation.height - value.translation.height)
                position = clamped(projected)
                withAnimation(.interpolatingSpring(stiffness: 170, damping: 20)) {
                    position = .zero
                }
                isDragging = false
            }
    }

    private func clamped(_ s: CGSize) -> CGSize {
        CGSize(width: min(max(s.width, -bounds.width), bounds.width),
               height: min(max(s.height, -bounds.height), bounds.height))
    }
}

#Preview {
    InteractionDragView()
}
