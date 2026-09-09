#!/usr/bin/env python3
"""Validate Interaction Drag's source, host, and runner delivery path.

The Xcode build phase uses ``--build-only`` so harmless workflow formatting cannot
block every SwamiHost build. The default mode additionally checks the semantic runner
contract (registry, build/install/capture, runtime selection, and H.264 recording).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SIGNATURE = "interaction-drag-r140-canvas-card-v4"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require_pattern(path: str, pattern: str, reason: str) -> None:
    if re.search(pattern, read(path), flags=re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(f"{path}: {reason}")


def assert_build_wiring() -> None:
    project = "app/Swami.xcodeproj/project.pbxproj"
    require_pattern(
        project,
        r"PBXFileSystemSynchronizedRootGroup[\s\S]*?path\s*=\s*Swami\s*;",
        "Swami's synchronized source root is absent",
    )

    source_path = "app/Swami/Patterns/Interaction_Drag.swift"
    source = read(source_path)
    signature = re.search(
        r"public\s+static\s+let\s+renderSignature\s*=\s*\"([^\"]+)\"", source
    )
    if signature is None or signature.group(1) != SIGNATURE:
        raise AssertionError(f"{source_path}: revision-specific source marker is stale")
    host_path = "app/SwamiHost/ContentView.swift"
    require_pattern(
        host_path,
        r"interactionDragSignature\s*=\s*\"" + re.escape(SIGNATURE) + r"\"",
        "host runtime-head expectation is stale",
    )
    require_pattern(
        host_path,
        r"case\s+\"drag\"\s*:\s*verifiedInteractionDragView\s*\(\s*\)",
        "SWAMI_PATTERN=drag is not routed to the verified view",
    )
    require_pattern(
        host_path,
        r"Interaction_DragView\.renderSignature\s*==\s*Self\.interactionDragSignature"
        r"[\s\S]*?Interaction_DragView\s*\(\s*\)",
        "selected Drag runtime does not verify the linked implementation marker",
    )


def registry() -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, raw_line in enumerate(read(".github/patterns.txt").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            slug, stem = line.split(":", 1)
        except ValueError as error:
            raise AssertionError(f".github/patterns.txt:{number}: malformed entry") from error
        entries[slug.strip()] = stem.strip()
    return entries


def assert_runner_wiring() -> None:
    if registry().get("drag") != "Interaction_Drag":
        raise AssertionError(
            ".github/patterns.txt: drag must map to Interaction_Drag for changed-source selection"
        )

    # Match command meaning rather than generated YAML indentation or exact quoting.
    workflow_path = ".github/workflows/verify.yml"
    workflow = re.sub(r"[ \t\\\n]+", " ", read(workflow_path))
    contracts = (
        (r"xcodebuild\s+build\b[^\n]*?-project\s+[^ ]+[^\n]*?-scheme\s+[^ ]+", "build"),
        (r"xcrun\s+simctl\s+install\b[^\n]*?\$APP", "install the just-built app"),
        (
            r"SIMCTL_CHILD_SWAMI_PATTERN\s*=\s*[^ ]*slug[^ ]*\s+"
            r"xcrun\s+simctl\s+launch\b",
            "runtime pattern selection",
        ),
        (
            r"xcrun\s+simctl\s+io\b[^\n]*?screenshot\s+"
            r"[^\n]*?out/swami/[^ ]*slug[^ ]*\.png",
            "per-pattern screenshot capture",
        ),
        (
            r"xcrun\s+simctl\s+io\b[^\n]*?recordVideo\b[^\n]*?"
            r"--codec\s*=\s*h264\b[^\n]*?out/recordings/drag\.mp4",
            "H.264 Interaction Drag recording",
        ),
    )
    for pattern, description in contracts:
        if re.search(pattern, workflow, flags=re.MULTILINE) is None:
            raise AssertionError(f"{workflow_path}: missing semantic contract: {description}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="check product source membership and runtime host selection only",
    )
    arguments = parser.parse_args()

    assert_build_wiring()
    if not arguments.build_only:
        assert_runner_wiring()
    scope = "build wiring" if arguments.build_only else "build and runner wiring"
    print(f"Interaction Drag {scope} OK: {SIGNATURE}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"wiring assertion failed: {error}", file=sys.stderr)
        raise SystemExit(1)
