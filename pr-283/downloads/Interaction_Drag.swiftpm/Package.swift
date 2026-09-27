// swift-tools-version: 5.9

// Swami sample — Interaction_Drag.
// App Playground package (.swiftpm). Open in Xcode 15+ (double-click, or File > Open)
// and press Run to launch this one Origami pattern as an iOS app.
//
// Single app target, one module: the pattern view and every vendored Swami helper
// compile together — the same single-module arrangement the Swami repo uses, so the
// pattern reaches helpers (RoundedTriangle, the .drag modifier, ...) with no import.
//
// `.iOSApplication` comes from AppleProductTypes, provided by Xcode's and Swift
// Playgrounds' SwiftPM. That is why this package builds/runs through Xcode (or Swift
// Playgrounds), not through a bare command-line `swift build`.
import PackageDescription
import AppleProductTypes

let package = Package(
    name: "Interaction_Drag",
    platforms: [
        .iOS("17.0")
    ],
    products: [
        .iOSApplication(
            name: "Interaction_Drag",
            targets: ["AppModule"],
            bundleIdentifier: "samatwork.samples.Interaction-Drag",
            displayVersion: "1.0",
            bundleVersion: "1",
            supportedDeviceFamilies: [
                .pad,
                .phone
            ],
            supportedInterfaceOrientations: [
                .portrait,
                .landscapeRight,
                .landscapeLeft,
                .portraitUpsideDown(.when(deviceFamilies: [.pad]))
            ]
        )
    ],
    targets: [
        .executableTarget(
            name: "AppModule",
            path: ".",
            exclude: [
                "README.md",
                "sample-manifest.json"
            ]
        )
    ]
)
