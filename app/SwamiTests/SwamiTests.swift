import SwiftUI
import Testing
@testable import Swami

struct SwamiTests {
    @Test func interactionDragMatchesRunnerGeometry() {
        #expect(Interaction_DragView.referenceSize == CGSize(width: 375, height: 667))
        #expect(Interaction_DragView.interactionAreaSize == CGSize(width: 315, height: 607))
        #expect(Interaction_DragView.interactionAreaCornerRadius == 20)
        #expect(Interaction_DragView.cardSize == 120)
        #expect(Interaction_DragView.cardCornerRadius == 15)
        #expect(Interaction_DragView.resetTolerance == 100)
        #expect(Interaction_DragView.rubberBandFriction == 0.15)
        #expect(Interaction_DragView.shouldReset(CGSize(width: 100, height: -100)))
        #expect(!Interaction_DragView.shouldReset(CGSize(width: 101, height: 0)))
        #expect(Interaction_DragView.dragBounds.min == CGSize(width: -97.5, height: -243.5))
        #expect(Interaction_DragView.dragBounds.max == CGSize(width: 97.5, height: 243.5))
    }

    @Test func dragDrivesBoundsMomentumResetAndFreshTouch() {
        let bounds = Interaction_DragView.dragBounds
        var state = DragState(start: .zero)

        state.change(
            translation: CGSize(width: 40, height: 10),
            bounds: bounds,
            rubberBandFriction: Interaction_DragView.rubberBandFriction
        )
        #expect(state.current == CGSize(width: 40, height: 10))
        #expect(state.translation == CGSize(width: 40, height: 10))

        let momentumTarget = state.end(
            predictedEndTranslation: CGSize(width: 200, height: 20),
            momentum: true,
            bounds: bounds
        )
        #expect(momentumTarget == CGSize(width: 97.5, height: 20))
        #expect(state.velocity == CGSize(width: 160, height: 10))
        state.settle(at: momentumTarget)
        #expect(state.current == momentumTarget)

        state.reset(to: .zero)
        #expect(state.current == .zero)
        #expect(state.translation == .zero)
        #expect(state.velocity == .zero)

        // A fresh touch starts at the reset position and cannot retain stale velocity.
        state.change(
            translation: CGSize(width: 250, height: 0),
            bounds: bounds,
            rubberBandFriction: Interaction_DragView.rubberBandFriction
        )
        #expect(state.velocity == .zero)
        #expect(state.current.width > bounds.max.width)
        #expect(state.current.width < 250)

        let boundedTarget = state.end(
            predictedEndTranslation: CGSize(width: 300, height: 0),
            momentum: false,
            bounds: bounds
        )
        #expect(boundedTarget == bounds.max)
        state.settle(at: boundedTarget)

        // A second pulse resets a later settled drag as completely as the first.
        state.reset(to: .zero)
        #expect(state.current == .zero)
        #expect(state.origin == .zero)
        #expect(!state.gestureIsActive)
    }
}
