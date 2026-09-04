import SwiftUI
import Foundation
import Swami

// The pattern currently under verification. CI drives which one by setting SWAMI_PATTERN;
// the loop adds a `case "<slug>"` per pattern as they're translated. Keep the body a single
// expression so screenshots are 1:1 with the Origami artboard — no host chrome, no nav bar.
struct ContentView: View {
    var body: some View {
        switch ProcessInfo.processInfo.environment["SWAMI_PATTERN"] {
        case "touch", nil: TouchOrigamiExampleView()
        default:           TouchOrigamiExampleView()   // add cases as patterns land
        }
    }
}
