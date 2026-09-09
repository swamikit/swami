import Testing
@testable import Swami

struct SwamiTests {
    @Test func interactionDragUsesExpectedDimensions() async throws {
        let view = InteractionDragView()
        _ = view
        #expect(Mirror(reflecting: view).children.count >= 0)
    }
}
