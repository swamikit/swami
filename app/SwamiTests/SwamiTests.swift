import Foundation
import Testing
@testable import Swami

struct DragTests {
    @Test func touchUpAtRestDoesNotReuseEarlierMomentum() {
        let previousTime = Date(timeIntervalSinceReferenceDate: 100)
        let velocity = Drag.releaseVelocity(
            previousTranslation: CGSize(width: 40, height: -20),
            previousSampleTime: previousTime,
            finalTranslation: CGSize(width: 40, height: -20),
            finalSampleTime: previousTime.addingTimeInterval(0.1),
            sampledVelocity: CGSize(width: 900, height: -450)
        )

        #expect(velocity == .zero)
    }

    @Test func touchUpUsesNewerEndpointSample() {
        let previousTime = Date(timeIntervalSinceReferenceDate: 100)
        let velocity = Drag.releaseVelocity(
            previousTranslation: CGSize(width: 20, height: 30),
            previousSampleTime: previousTime,
            finalTranslation: CGSize(width: 30, height: 25),
            finalSampleTime: previousTime.addingTimeInterval(0.05),
            sampledVelocity: CGSize(width: 1, height: 1)
        )

        #expect(abs(velocity.width - 200) < 0.0001)
        #expect(abs(velocity.height + 100) < 0.0001)
    }

    @Test func touchUpWithoutNewTimingUsesFinalChangedSample() {
        let sampleTime = Date(timeIntervalSinceReferenceDate: 100)
        let sampledVelocity = CGSize(width: 120, height: -80)
        let velocity = Drag.releaseVelocity(
            previousTranslation: CGSize(width: 20, height: 30),
            previousSampleTime: sampleTime,
            finalTranslation: CGSize(width: 30, height: 25),
            finalSampleTime: sampleTime,
            sampledVelocity: sampledVelocity
        )

        #expect(velocity == sampledVelocity)
    }
}
