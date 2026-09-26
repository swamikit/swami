//
//  SwamiTests.swift
//  SwamiTests
//
//  Created by Samuel Alake on 9/3/26.
//

import Testing
import SwiftUI
@testable import Swami

struct SwamiTests {

    @Test func example() async throws {
        // Write your test here and use APIs like `#expect(...)` to check expected conditions.
    }

    // Interaction_Pinch: the origami.PopSwitch flip logic. Pinch out past the
    // threshold pops in; pinch in past its reciprocal pops out; in between, the
    // switch holds its remembered state (Pop Switch = memory).
    @Test func pinchPopSwitchFlips() {
        let t: CGFloat = 1.25
        // Pinch out past the threshold pops in, whatever the prior state.
        #expect(Interaction_PinchView.popped(after: 1.5, current: false, threshold: t) == true)
        #expect(Interaction_PinchView.popped(after: 1.25, current: false, threshold: t) == true)
        // Pinch in past the reciprocal pops out.
        #expect(Interaction_PinchView.popped(after: 0.5, current: true, threshold: t) == false)
        // In the dead band the switch holds its remembered state.
        #expect(Interaction_PinchView.popped(after: 1.0, current: true, threshold: t) == true)
        #expect(Interaction_PinchView.popped(after: 1.0, current: false, threshold: t) == false)
    }

    // Interaction_Pinch is instantiable from outside the module — the host and the
    // DocC catalog both need the public surface.
    @Test func pinchViewIsPublic() {
        _ = Interaction_PinchView()
    }

}
