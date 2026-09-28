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
        // Pinch in at or past the reciprocal threshold pops out.
        #expect(Interaction_PinchView.popped(after: 0.5, current: true, threshold: t) == false)
        #expect(Interaction_PinchView.popped(after: 1 / t, current: true, threshold: t) == false)
        // In the dead band the switch holds its remembered state.
        #expect(Interaction_PinchView.popped(after: 1.0, current: true, threshold: t) == true)
        #expect(Interaction_PinchView.popped(after: 1.0, current: false, threshold: t) == false)
    }

    // Interaction_Pinch is instantiable from outside the module — the host and the
    // DocC catalog both need the public surface.
    @Test func pinchViewIsPublic() {
        _ = Interaction_PinchView()
    }

    // Interaction_Pinch's shape (builtin.layer.shape) is a rounded triangle, not a
    // rectangle. The path must be non-empty, closed, and stay within its bounding
    // rect — a triangle apex-up fills the top-center and both bottom corners.
    @Test func roundedTriangleFillsItsRect() {
        let rect = CGRect(x: 0, y: 0, width: 80, height: 74)
        let path = RoundedTriangle(cornerRadius: 14).path(in: rect)
        #expect(!path.isEmpty)
        // The path stays inside the frame it is asked to fill.
        #expect(rect.insetBy(dx: -0.5, dy: -0.5).contains(path.boundingRect))
        // Apex-up: the top center is filled, and so is the bottom edge.
        #expect(path.contains(CGPoint(x: rect.midX, y: rect.minY + 10)))
        #expect(path.contains(CGPoint(x: rect.midX, y: rect.maxY - 2)))
        // The top corners are empty and the triangle narrows toward the apex —
        // this is a triangle, not a rectangle.
        #expect(!path.contains(CGPoint(x: rect.minX + 2, y: rect.minY + 2)))
        #expect(!path.contains(CGPoint(x: rect.maxX - 2, y: rect.minY + 2)))
        #expect(!path.contains(CGPoint(x: rect.midX - 25, y: rect.minY + 18)))
    }

    // A zero corner radius still yields a valid closed triangle.
    @Test func roundedTriangleZeroRadiusIsValid() {
        let path = RoundedTriangle(cornerRadius: 0).path(in: CGRect(x: 0, y: 0, width: 100, height: 100))
        #expect(!path.isEmpty)
    }

    // Interaction_Swipe is instantiable from outside the module — the host and the DocC
    // catalog both need the public surface.
    @Test func swipeViewIsPublic() {
        _ = Interaction_SwipeView()
    }

    // Interaction_Swipe: the swipe is horizontal-only paging. The origami.Drag bounds
    // must pin the vertical extent to 0 (a swipe never drifts up/down) and let the row
    // travel left by one page width per extra page, resting page 0 at offset 0.
    @Test func swipeBoundsAreHorizontalOnly() {
        let width: CGFloat = 393
        let bounds = Interaction_SwipeView.horizontalSwipeBounds(pageWidth: width, pageCount: 2)
        // Vertical travel is pinned to zero — swipe stays on the horizontal axis.
        #expect(bounds.min.height == 0)
        #expect(bounds.max.height == 0)
        // Page 0 rests at offset 0; the row can travel left by one page width.
        #expect(bounds.max.width == 0)
        #expect(bounds.min.width == -width)
    }

    // Three pages travel two page widths; a single page has no travel at all.
    @Test func swipeBoundsScaleWithPageCount() {
        let width: CGFloat = 100
        #expect(Interaction_SwipeView.horizontalSwipeBounds(pageWidth: width, pageCount: 3).min.width == -200)
        #expect(Interaction_SwipeView.horizontalSwipeBounds(pageWidth: width, pageCount: 1).min.width == 0)
    }

}
