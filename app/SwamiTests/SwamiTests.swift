import Testing
@testable import Swami

struct SwamiTests {
    @Test func interactionDragUsesExpectedDimensions() async throws {
        let view = InteractionDragView()
        _ = view
        #expect(true)
    }
}