#!/usr/bin/env python3
"""Fail closed when Swami's verification workflow loses required semantics."""

from pathlib import Path
import re


WORKFLOW = Path(".github/workflows/verify.yml")
REGISTRY = Path(".github/patterns.txt")


def require(source: str, fragment: str, label: str) -> None:
    if fragment not in source:
        raise SystemExit(f"verify contract missing {label}: {fragment}")


def main() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    required = {
        "pull-request trigger": "pull_request:",
        "manual full-run trigger": "workflow_dispatch:",
        "macOS runner": "runs-on: macos-15",
        "code-change condition": "needs.changes.outputs.code == 'true'",
        "manual-run condition": "github.event_name == 'workflow_dispatch'",
        "Origami reference render": "Render Origami references (drives sim dims)",
        "matching simulator": "Pick + boot a simulator",
        "Swami build": "Build SwamiHost (once)",
        "visual comparison": "Render SwamiHost + compare per pattern",
        "interaction recording": "Record changed interaction patterns",
        "Builder publication": "Publish canonical Builder delivery into the PR description",
        "current-head sanity": "Enforce current-head delivery sanity",
        "changed-pattern scope": "CHANGED_PATTERNS",
        "catastrophic sanity floor": "VISUAL_SANITY_FLOOR",
    }
    for label, fragment in required.items():
        require(source, fragment, label)

    code_filter = re.search(r"filters:\s*\|\s*\n\s+code:\s*\n(?P<body>(?:\s+-.*\n)+)", source)
    if not code_filter:
        raise SystemExit("verify contract missing code path filter")
    paths = code_filter.group("body")
    for required_path in ("'app/**'", "'tool/src/**'", "'**/*.origami'"):
        require(paths, required_path, "product evidence path")
    if "'.github/workflows/verify.yml'" in paths:
        raise SystemExit("control-plane workflow edits must not implicitly render the corpus")

    entries = [
        line.strip()
        for line in REGISTRY.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not entries or any(not re.fullmatch(r"[a-z0-9_]+:[A-Za-z0-9_]+", item) for item in entries):
        raise SystemExit("pattern registry contains an invalid entry")
    print(f"verify contract valid; {len(entries)} registered patterns remain explicitly scoped")


if __name__ == "__main__":
    main()
