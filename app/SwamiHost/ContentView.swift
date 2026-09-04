import SwiftUI
import Foundation
import Swami

// The pattern currently under verification. CI drives which one by setting SWAMI_PATTERN;
// the loop adds a `case "<slug>"` per pattern as they're translated. Keep the body a single
// expression so screenshots are 1:1 with the Origami artboard — no host chrome, no nav bar.
struct ContentView: View {
    var body: some View {
        Group {
            switch ProcessInfo.processInfo.environment["SWAMI_PATTERN"] {
            case "touch", nil: Interaction_Touch()
            default:           Interaction_Touch()   // add cases as patterns land
            }
        }
        // Strip every sim chrome we can from the SwiftUI side — Origami's artboard has none.
        // status_bar override on the sim (in CI) is a belt-and-suspenders second line.
        .ignoresSafeArea()
        .statusBarHidden()
        .persistentSystemOverlays(.hidden)
    }
}
