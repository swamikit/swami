import SwiftUI
import Testing
@testable import Swami

struct SwamiTests {
    @Test func dragKeepsDocumentedDefaultSourceCompatible() {
        _ = Color.clear.drag()
    }

    @Test func interactionDragPreservesReferenceCompositionAndLogicalBounds() {
        #expect(Interaction_DragView.renderSignature == "interaction-drag-r140-canvas-card-v5")
        #expect(Interaction_DragView.referenceSize == CGSize(width: 375, height: 667))
        #expect(Interaction_DragView.DragGeometry.logicalRegion == CGSize(width: 315, height: 607))
        #expect(Interaction_DragView.cardSize == 120)
        #expect(Interaction_DragView.cardCornerRadius == 15)
        #expect(Interaction_DragView.resetTolerance == 100)
        #expect(Interaction_DragView.rubberBandFriction == 0.15)
        #expect(Interaction_DragView.shouldReset(CGSize(width: 100, height: -100)))
        #expect(!Interaction_DragView.shouldReset(CGSize(width: 101, height: 0)))
        #expect(Interaction_DragView.DragGeometry.bounds.min == CGSize(width: -97.5, height: -243.5))
        #expect(Interaction_DragView.DragGeometry.bounds.max == CGSize(width: 97.5, height: 243.5))
    }

    @Test func freshGestureUsesConfiguredStartWithoutManualReset() {
        let start = CGSize(width: 12, height: -8)
        var state = DragState(start: start)

        state.change(
            translation: CGSize(width: 30, height: 20),
            start: start,
            bounds: nil,
            rubberBandFriction: Interaction_DragView.rubberBandFriction
        )
        let firstTarget = state.end(
            releaseTranslation: CGSize(width: 30, height: 20),
            predictedEndTranslation: CGSize(width: 90, height: 50),
            momentum: true,
            bounds: nil
        )
        state.settle(at: firstTarget)
        #expect(state.current == CGSize(width: 102, height: 42))

        // No reset occurs between gestures. The first change must nevertheless use
        // configured Start, not the prior settled endpoint (the rejected-head bug).
        state.change(
            translation: CGSize(width: 4, height: 6),
            start: start,
            bounds: nil,
            rubberBandFriction: Interaction_DragView.rubberBandFriction
        )
        #expect(state.origin == start)
        #expect(state.current == CGSize(width: 16, height: -2))
        #expect(state.translation == CGSize(width: 4, height: 6))
        #expect(state.velocity == .zero)
    }

    @Test func releaseUsesGestureEndTranslationInsteadOfPriorChangeSample() {
        var state = DragState(start: .zero)
        state.change(
            translation: CGSize(width: 20, height: 5),
            start: .zero,
            bounds: nil,
            rubberBandFriction: Interaction_DragView.rubberBandFriction
        )

        let target = state.end(
            releaseTranslation: CGSize(width: 35, height: 12),
            predictedEndTranslation: CGSize(width: 80, height: 30),
            momentum: true,
            bounds: nil
        )

        #expect(state.translation == CGSize(width: 35, height: 12))
        #expect(state.velocity == CGSize(width: 45, height: 18))
        #expect(target == CGSize(width: 80, height: 30))
    }

    @Test func dragDrivesBoundsMomentumResetAndFreshTouch() {
        let bounds = Interaction_DragView.DragGeometry.bounds
        var state = DragState(start: .zero)

        state.change(
            translation: CGSize(width: 40, height: 10),
            start: .zero,
            bounds: bounds,
            rubberBandFriction: Interaction_DragView.rubberBandFriction
        )
        #expect(state.current == CGSize(width: 40, height: 10))
        #expect(state.translation == CGSize(width: 40, height: 10))

        let momentumTarget = state.end(
            releaseTranslation: CGSize(width: 40, height: 10),
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
            start: .zero,
            bounds: bounds,
            rubberBandFriction: Interaction_DragView.rubberBandFriction
        )
        #expect(state.velocity == .zero)
        #expect(state.current.width > bounds.max.width)
        #expect(state.current.width < 250)

        let boundedTarget = state.end(
            releaseTranslation: CGSize(width: 250, height: 0),
            predictedEndTranslation: CGSize(width: 300, height: 0),
            momentum: false,
            bounds: bounds
        )
        #expect(boundedTarget == CGSize(width: bounds.max.width, height: 0))
        state.settle(at: boundedTarget)

        // A second pulse resets a later settled drag as completely as the first.
        state.reset(to: .zero)
        #expect(state.current == .zero)
        #expect(state.origin == .zero)
        #expect(!state.gestureIsActive)
    }
}
