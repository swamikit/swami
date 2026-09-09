import SwiftUI
import Testing
@testable import Swami

struct SwamiTests {
    @Test func interactionDragMatchesRunnerGeometry() {
        #expect(Interaction_DragView.referenceSize == CGSize(width: 375, height: 667))
        #expect(Interaction_DragView.interactionAreaSize == CGSize(width: 315, height: 607))
        #expect(Interaction_DragView.interactionAreaCornerRadius == 20)
        #expect(Interaction_DragView.interactionAreaContourOpacity == 0.04)
        #expect(Interaction_DragView.cardSize == 120)
        #expect(Interaction_DragView.cardCornerRadius == 15)
        #expect(Interaction_DragView.cardContourOpacity == 0.01)
        #expect(Interaction_DragView.resetTolerance == 100)
        #expect(Interaction_DragView.shouldReset(CGSize(width: 100, height: -100)))
        #expect(!Interaction_DragView.shouldReset(CGSize(width: 101, height: 0)))

        let bounds = Interaction_DragView.dragBounds(in: CGSize(width: 375, height: 667))
        #expect(bounds.min == CGSize(width: -97.5, height: -243.5))
        #expect(bounds.max == CGSize(width: 97.5, height: 243.5))
    }
}
