// swift-tools-version: 5.9
import PackageDescription

// Swami — SwiftUI-side corpus + headless visual-verification harness.
//
// - Open in Xcode: each pattern under Sources/Swami/ carries a #Preview, so the canvas
//   renders it (for interactive/human review).
// - Headless verify (the loop's scoring step): `swift test` renders each pattern to a
//   PNG via ImageRenderer — no simulator, no GUI. Set SNAPSHOT_OUT to choose the dir.
//     SNAPSHOT_OUT=/tmp/swami-snapshots swift test
//   Then diff those PNGs against the Origami renders.
let package = Package(
    name: "Swami",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [
        .library(name: "Swami", targets: ["Swami"])
    ],
    targets: [
        .target(name: "Swami"),
        .testTarget(name: "SwamiTests", dependencies: ["Swami"])
    ]
)
