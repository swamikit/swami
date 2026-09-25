//
//  SwamiTests.swift
//  SwamiTests
//
//  Created by Samuel Alake on 9/3/26.
//

import Testing
@testable import Swami

struct SwamiTests {

    @Test func example() async throws {
        // Write your test here and use APIs like `#expect(...)` to check expected conditions.
    }

    // Interaction_Pinch: the origami.PopSwitch flip decision snaps to the nearer state.
    // Midpoint between base (1) and magnified (2) is 1.5.
    @Test func pinchPopSwitchSnapsToNearerState() {
        #expect(Interaction_PinchView.popSwitchOn(projectedScale: 1.0, base: 1, magnified: 2) == false)
        #expect(Interaction_PinchView.popSwitchOn(projectedScale: 1.49, base: 1, magnified: 2) == false)
        #expect(Interaction_PinchView.popSwitchOn(projectedScale: 1.5, base: 1, magnified: 2) == true)
        #expect(Interaction_PinchView.popSwitchOn(projectedScale: 2.0, base: 1, magnified: 2) == true)
    }

    // Interaction_Pinch: the public pattern view instantiates (verification-host wiring).
    @Test func pinchViewInstantiates() {
        _ = Interaction_PinchView()
    }

}
