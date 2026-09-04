// DRAFT / UNVERIFIED — swami (Origami → SwiftUI). Pattern: Interaction_Drag.
//
// STATUS: structural draft only. NOT derived from the document's exact placed graph and NOT
// drive-verified. The parser's tail heuristic over-includes origami.Drag's embedded component
// internals on this 534 KB file (157 "placed" nodes incl. AddMomentum/ClipY/Velocity/…), so exact
// geometry, colors, bounds, and layer count were NOT read from the graph. See NEEDS-VERIFY.md.
//
// What this demonstrates: the drag() helper (origami.Drag) — a draggable card with momentum and
// rubber-band bounds — wired the way the codegen will wire it once the parser isolates the real
// placed graph. Treat the numbers below as placeholders, not oracle values.
import SwiftUI
import Swami

struct InteractionDragDraftView: View {
    // Drag outputs (origami.Drag ports): Position / Translation / Velocity.
    @State private var position: CGSize = .zero
    @State private var translation: CGSize = .zero
    @State private var velocity: CGSize = .zero

    // PLACEHOLDER geometry — must be replaced with graph-read values (NEEDS-VERIFY).
    private let card = CGSize(width: 220, height: 140)

    var body: some View {
        GeometryReader { geo in
            // Clip bounds (origami.Drag "Clip" / Start+End boundary): keep the card on screen.
            let bx = max((geo.size.width  - card.width)  / 2, 0)
            let by = max((geo.size.height - card.height) / 2, 0)
            let bounds = (min: CGSize(width: -bx, height: -by),
                          max: CGSize(width:  bx, height:  by))

            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(Color.accentColor)               // PLACEHOLDER fill (graph color TBD)
                .frame(width: card.width, height: card.height)
                .drag(momentum: true,
                      bounds: bounds,
                      position: $position,
                      translation: $translation,
                      velocity: $velocity)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        }
        .ignoresSafeArea()
    }
}

#Preview { InteractionDragDraftView() }
