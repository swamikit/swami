import CoreGraphics
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

    @Test func touchUpWithoutBaselineCannotReusePreviousGestureVelocity() {
        #expect(Drag.releaseVelocity(
            previousTranslation: .zero,
            previousSampleTime: nil,
            finalTranslation: .zero,
            finalSampleTime: Date(timeIntervalSinceReferenceDate: 100),
            sampledVelocity: CGSize(width: 900, height: -450)
        ) == .zero)
    }

    @Test func duplicateTouchUpPreservesFinalRestSample() {
        let time = Date(timeIntervalSinceReferenceDate: 100)
        let restingTranslation = CGSize(width: 40, height: -20)
        let stoppedVelocity = Drag.releaseVelocity(
            previousTranslation: restingTranslation,
            previousSampleTime: time,
            finalTranslation: restingTranslation,
            finalSampleTime: time.addingTimeInterval(0.1),
            sampledVelocity: CGSize(width: 900, height: -450)
        )
        #expect(Drag.releaseVelocity(
            previousTranslation: restingTranslation,
            previousSampleTime: time.addingTimeInterval(0.1),
            finalTranslation: restingTranslation,
            finalSampleTime: time.addingTimeInterval(0.1),
            sampledVelocity: stoppedVelocity
        ) == .zero)
    }

    @Test func outOfOrderTouchUpKeepsLastValidSample() {
        let time = Date(timeIntervalSinceReferenceDate: 100)
        let lastTranslation = CGSize(width: 20, height: 30)
        let staleTouchUp = CGSize(width: 10, height: 40)
        let lastVelocity = CGSize(width: -120, height: 80)
        let finalTranslation = Drag.finalValidTranslation(
            previousTranslation: lastTranslation,
            previousSampleTime: time,
            touchUpTranslation: staleTouchUp,
            touchUpTime: time.addingTimeInterval(-0.1)
        )
        #expect(finalTranslation == lastTranslation)
        #expect(Drag.releaseVelocity(
            previousTranslation: lastTranslation,
            previousSampleTime: time,
            finalTranslation: finalTranslation,
            finalSampleTime: time.addingTimeInterval(-0.1),
            sampledVelocity: lastVelocity
        ) == lastVelocity)
    }

    @Test func newerTouchUpSuppliesReleasedPosition() {
        let time = Date(timeIntervalSinceReferenceDate: 100)
        let touchUp = CGSize(width: 30, height: 25)
        #expect(Drag.finalValidTranslation(
            previousTranslation: CGSize(width: 20, height: 30),
            previousSampleTime: time,
            touchUpTranslation: touchUp,
            touchUpTime: time.addingTimeInterval(0.05)
        ) == touchUp)
    }
}
