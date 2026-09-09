#!/usr/bin/env python3
"""Fail when Interaction Drag is disconnected from the runner capture path.

This is intentionally dependency-free so it can run on Linux and in an Xcode build
phase. Runtime freshness is completed by ContentView's render-signature precondition:
a stale linked Swami framework crashes before the runner can take a drag screenshot.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, text: str, reason: str) -> None:
    contents = (ROOT / path).read_text(encoding="utf-8")
    if text not in contents:
        raise AssertionError(f"{path}: {reason}; missing {text!r}")


def main() -> int:
    signature = "interaction-drag-r140-reset-start-v2"

    require(
        "app/Swami.xcodeproj/project.pbxproj",
        "PBXFileSystemSynchronizedRootGroup",
        "Swami sources are not under synchronized target membership",
    )
    require(
        "app/Swami.xcodeproj/project.pbxproj",
        "path = Swami;",
        "the synchronized Swami source root is absent",
    )
    require(
        "app/Swami/Patterns/Interaction_Drag.swift",
        f'public static let renderSignature = "{signature}"',
        "the revision-specific implementation marker is absent",
    )
    require(
        "app/SwamiHost/ContentView.swift",
        'case "drag":',
        "SWAMI_PATTERN=drag is not registered in SwamiHost",
    )
    require(
        "app/SwamiHost/ContentView.swift",
        f'Interaction_DragView.renderSignature == "{signature}"',
        "SwamiHost does not reject a stale linked framework",
    )
    require(
        ".github/patterns.txt",
        "drag:Interaction_Drag",
        "the runner pattern registry does not map drag to the committed source",
    )
    require(
        ".github/workflows/verify.yml",
        'SIMCTL_CHILD_SWAMI_PATTERN="$slug" xcrun simctl launch',
        "the screenshot launch does not pass the selected slug",
    )
    require(
        ".github/workflows/verify.yml",
        'screenshot "out/swami/${slug}.png"',
        "the launched simulator is not captured per selected slug",
    )
    require(
        ".github/workflows/verify.yml",
        'recordVideo --codec=h264 --force out/recordings/drag.mp4',
        "the drag flow does not request an H.264 recording",
    )

    print(f"Interaction Drag wiring OK: {signature}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"wiring assertion failed: {error}", file=sys.stderr)
        raise SystemExit(1)
