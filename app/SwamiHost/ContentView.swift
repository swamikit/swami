import SwiftUI
import Swami

struct ContentView: View {
    var body: some View {
        switch ProcessInfo.processInfo.environment["SWAMI_PATTERN"] {
        case "drag", "interaction-drag", "interaction_drag": Interaction_DragView()
        case "touch", nil: TouchOrigamiExampleView()
        default: TouchOrigamiExampleView()
        }
    }
}
