import XCTest
import SwiftUI
import ImageIO
@testable import Swami

// Headless snapshot verification. Renders each pattern's SwiftUI view to a PNG via
// ImageRenderer (cross-platform, no simulator) so the output can be diffed against the
// Origami render. This is the loop's scoring step — runnable by `swift test`.
//
//   SNAPSHOT_OUT=/path/to/out swift test
//
// Each render prints `SNAPSHOT <name> -> <path>` so a driver (Claude Code / CI) can
// collect the images.
@MainActor
final class SnapshotTests: XCTestCase {

    private func snapshot(_ view: some View, width: CGFloat, height: CGFloat, name: String) throws {
        let renderer = ImageRenderer(content: view.frame(width: width, height: height))
        renderer.scale = 2
        guard let cg = renderer.cgImage else {
            return XCTFail("ImageRenderer produced no image for \(name)")
        }
        let dir = ProcessInfo.processInfo.environment["SNAPSHOT_OUT"]
            .map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.temporaryDirectory.appendingPathComponent("swami-snapshots")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("\(name).png")
        guard let dest = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil) else {
            return XCTFail("could not create PNG destination for \(name)")
        }
        CGImageDestinationAddImage(dest, cg, nil)
        guard CGImageDestinationFinalize(dest) else {
            return XCTFail("could not write PNG for \(name)")
        }
        print("SNAPSHOT \(name) -> \(url.path)")
    }

    // iPhone 17 Pro logical size (matches the Origami artboard device).
    func testTouchOrigamiExample() throws {
        try snapshot(TouchOrigamiExampleView(), width: 402, height: 874, name: "TouchOrigamiExample")
    }

    // Add one test per pattern as the parser/codegen covers more of the corpus.
}
