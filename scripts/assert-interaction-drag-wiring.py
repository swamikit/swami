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
REVISION = "interaction-drag-r140-canvas-card-v7"


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

    if len(re.findall(r'INFOPLIST_FILE\s*=\s*"Swami-Info\.plist"\s*;', read(project))) != 2:
        raise AssertionError(
            f"{project}: Debug and Release must embed Swami's explicit framework plist"
        )
    require_pattern(
        "app/Swami-Info.plist",
        r"<key>SWAMIInteractionDragRevision</key>\s*<string>"
        + re.escape(REVISION)
        + r"</string>",
        "framework bundle revision is stale",
    )

    source_path = "app/Swami/Patterns/Interaction_Drag.swift"
    source = read(source_path)
    require_pattern(
        source_path,
        r'object\s*\(\s*forInfoDictionaryKey:\s*"SWAMIInteractionDragRevision"\s*\)',
        "runtime revision is not read from the built framework bundle",
    )

    body = re.search(
        r"public\s+var\s+body\s*:\s*some\s+View\s*\{([\s\S]*?)\n\s*static\s+func\s+shouldReset",
        source,
    )
    if body is None:
        raise AssertionError(f"{source_path}: cannot inspect the rendered composition")
    rendered = body.group(1)
    if len(re.findall(r"\bRoundedRectangle\s*\(", rendered)) != 1:
        raise AssertionError(
            f"{source_path}: rendered hierarchy must contain only the one rounded card"
        )
    for fact, reason in (
        (r"Self\.canvasColor", "full-screen canvas is absent"),
        (r"cornerRadius:\s*Self\.cardCornerRadius", "card radius is not source-bound"),
        (
            r"width:\s*Self\.cardSize\s*,\s*height:\s*Self\.cardSize",
            "card size is not source-bound",
        ),
        (
            r"bounds:\s*Self\.DragGeometry\.bounds",
            "logical bounds are not passed as Drag state",
        ),
    ):
        if re.search(fact, rendered) is None:
            raise AssertionError(f"{source_path}: {reason}")
    if re.search(r"\.frame\s*\([^)]*DragGeometry\.logicalRegion", rendered, re.DOTALL):
        raise AssertionError(f"{source_path}: logical region leaked into the rendered hierarchy")

    host_path = "app/SwamiHost/ContentView.swift"
    require_pattern(
        host_path,
        r"interactionDragRevision\s*=\s*\"" + re.escape(REVISION) + r"\"",
        "host runtime-head expectation is stale",
    )
    require_pattern(
        host_path,
        r"case\s+\"drag\"\s*:\s*verifiedInteractionDragView\s*\(\s*\)",
        "SWAMI_PATTERN=drag is not routed to the verified view",
    )
    require_pattern(
        host_path,
        r"Interaction_DragView\.builtProductRevision\s*==\s*Self\.interactionDragRevision"
        r"[\s\S]*?Interaction_DragView\s*\(\s*\)",
        "selected Drag runtime does not verify the linked framework bundle",
    )
    require_pattern(
        host_path,
        r"showsTouchIndicator[\s\S]*?InteractionEvidenceTouchIndicator"
        r"[\s\S]*?completedStillCaptureKey[\s\S]*?@GestureState"
        r"[\s\S]*?DragGesture\s*\(\s*minimumDistance:\s*0"
        r"[\s\S]*?\.updating\s*\(\s*\$location\s*\)",
        "runner-host recording does not expose touch-down, trajectory, and release",
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


def workflow_steps(workflow: str) -> list[str]:
    """Split explicit name/uses steps without assuming a fixed YAML indent."""
    starts: list[tuple[int, int]] = []
    for match in re.finditer(r"(?m)^(?P<indent>[ \t]*)-\s+(?:name|uses)\s*:", workflow):
        starts.append((match.start(), len(match.group("indent").expandtabs(8))))

    steps: list[str] = []
    for index, (start, indent) in enumerate(starts):
        end = len(workflow)
        for next_start, next_indent in starts[index + 1 :]:
            if next_indent <= indent:
                end = next_start
                break
        steps.append(workflow[start:end])
    return steps


def assert_runner_wiring() -> None:
    if registry().get("drag") != "Interaction_Drag":
        raise AssertionError(
            ".github/patterns.txt: drag must map to Interaction_Drag for changed-source selection"
        )

    workflow_path = ".github/workflows/verify.yml"
    workflow = read(workflow_path)

    # Require related capabilities to coexist in a single explicit workflow step,
    # without pinning quoting, variable names, indentation, or command wrappers.
    steps = workflow_steps(workflow)
    if not steps:
        raise AssertionError(f"{workflow_path}: no explicit name/uses workflow steps found")

    def require_step(capabilities: tuple[str, ...], reason: str) -> str:
        for step in steps:
            if all(re.search(item, step, flags=re.IGNORECASE) for item in capabilities):
                return step
        raise AssertionError(f"{workflow_path}: missing semantic contract: {reason}")

    require_step(
        (r"\bxcodebuild\b", r"\bbuild\b", r"\bSwamiHost\b|\$SCHEME"),
        "SwamiHost build",
    )
    install = require_step(
        (r"\bsimctl\s+install\b", r"build/Build/Products", r"CFBundleIdentifier"),
        "install and bundle lookup of the current build product",
    )
    if not re.search(r"\.app\b|\$APP\b", install):
        raise AssertionError(f"{workflow_path}: install step does not select a built app")

    require_step(
        (
            r"RUN_PATTERNS",
            r"slug=.*pair",
            r"SWAMI_PATTERN\s*=",
            r"\bsimctl\s+launch\b",
            r"\bsimctl\s+io\b[\s\S]*?\bscreenshot\b",
            r"out/swami/",
        ),
        "registry-selected host launch and screenshot capture",
    )
    recording = require_step(
        (
            r"changed_patterns[\s\S]*?Interaction_Drag",
            r"SWAMI_PATTERN\s*=",
            r"\bsimctl\s+launch\b",
            r"\brecordVideo\b",
            r"(?:--codec[=\s]+h264|h264[\s\S]*?recordVideo)",
            r"\.mp4\b",
            r"\bmaestro\b",
            r"\.ya?ml\b",
        ),
        "changed Interaction Drag launch, scripted gesture, and H.264 recording",
    )
    if not re.search(r"test\s+-s\s+[^\n]*\.mp4", recording):
        raise AssertionError(f"{workflow_path}: recording is not checked for non-empty output")


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
    print(f"Interaction Drag {scope} OK: {REVISION}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"wiring assertion failed: {error}", file=sys.stderr)
        raise SystemExit(1)
