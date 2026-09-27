#!/usr/bin/env python3
"""Assemble downloadable Xcode samples ("App Playground" .swiftpm) for Swami patterns.

Given a pattern stem (or `--all`, driven by .github/patterns.txt), this gathers:

  * the pattern's own `.swift` (copied verbatim, so the download IS the gallery view),
  * the Swami helper sources it needs (vendored so the sample is self-contained),
  * a generated `@main` App entry, a templated `Package.swift`, a README, a manifest,

and writes a `<PatternID>.swiftpm` directory plus a `<PatternID>.zip` that opens in
Xcode 15+ and runs as an iOS app showing exactly that one pattern.

Why `.swiftpm` and not `.xcodeproj`: an App Playground is a directory of Swift files
plus a hand-writable `Package.swift`. There is no pbxproj (no UUID surgery), so it is
deterministic to emit in CI, it runs as a real app in Xcode/Swift Playgrounds, and with
the helper sources vendored it needs no Swami checkout to build.

stdlib only. Runs anywhere (Linux CI included); it does NOT compile the sample — that
needs Xcode/macOS. Use `--prune` for a minimal helper set; the default vendors every
helper (safe, deterministic, zero per-pattern maintenance).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

TOOLS_VERSION = "5.9"
DEPLOYMENT_IOS = "17.0"
BUNDLE_PREFIX = "samatwork.samples"
GENERATOR_VERSION = "1.0"

# ----------------------------------------------------------------------------- templates

PACKAGE_SWIFT = """\
// swift-tools-version: {tools_version}

// Swami sample — {pattern}.
// App Playground package (.swiftpm). Open in Xcode 15+ (double-click, or File > Open)
// and press Run to launch this one Origami pattern as an iOS app.
//
// `.iOSApplication` comes from AppleProductTypes, provided by Xcode's and Swift
// Playgrounds' SwiftPM. That is why this package builds/runs through Xcode (or Swift
// Playgrounds), not through a bare command-line `swift build`.
import PackageDescription
import AppleProductTypes

let package = Package(
    name: "{pattern}",
    platforms: [
        .iOS("{deployment}")
    ],
    products: [
        .iOSApplication(
            name: "{pattern}",
            targets: ["AppModule"],
            bundleIdentifier: "{bundle_id}",
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
        // The app: the @main entry (SampleApp.swift) plus the pattern view,
        // copied verbatim from the Swami repo.
        .executableTarget(
            name: "AppModule",
            dependencies: ["Swami"],
            path: "App"
        ),
        // The vendored slice of the Swami helper library the pattern imports.
        // Copied verbatim so `import Swami` in the pattern resolves with no edits.
        .target(
            name: "Swami",
            path: "Swami"
        )
    ]
)
"""

APP_SWIFT = """\
import SwiftUI

// Downloadable Swami sample — {pattern}.
//
// This is a self-contained App Playground: open the enclosing `.swiftpm` in Xcode 15+
// and press Run to launch the pattern as an iOS app in the Simulator (or on a device).
// The one screen renders `{view}` — the exact pattern view from the Swami gallery — and
// nothing else.
//
// The pattern view lives in `{pattern}.swift` (copied verbatim from the repo) and reaches
// its behaviour through `import Swami`, whose sources are vendored under `../Swami/`. No
// external package or checkout is required.
@main
struct SampleApp: App {{
    var body: some Scene {{
        WindowGroup {{
            {view}()
        }}
    }}
}}
"""

README_MD = """\
# {pattern} (Swami sample)

A runnable Xcode sample for one Swami pattern.

## Run it

1. Unzip.
2. Double-click **`{pattern}.swiftpm`** (or Xcode > File > Open...). Requires **Xcode 15+**.
3. Pick an iOS Simulator (or your device) and press **Run** (Cmd-R).

You can also open the `.swiftpm` in **Swift Playgrounds** on iPad. If it will not open
there, flatten to a single target: move `Swami/*.swift` into `App/`, delete the `Swami`
target from `Package.swift`, set the `AppModule` `path` to `"."`, and remove the
`import Swami` line from `{pattern}.swift`.

## What's inside

- `Package.swift` — App Playground manifest (`.iOSApplication` product).
- `App/SampleApp.swift` — `@main`; hosts the pattern view and nothing else.
- `App/{pattern}.swift` — the pattern view, copied verbatim from Swami.
- `Swami/*.swift` — the Swami helper sources the pattern imports (vendored).

`App/{pattern}.swift` is byte-for-byte the file from the Swami repo, so what you run is
exactly the gallery pattern. Because the helper sources are vendored under `Swami/`, the
sample builds with no extra checkout or package dependency.

## Learn more

Swami pattern gallery: https://swamikit.github.io/swami/documentation/swami/
"""

# ----------------------------------------------------------------------------- helpers


def die(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"package_sample: error: {msg}", file=sys.stderr)
    raise SystemExit(2)


def read_patterns_txt(repo: Path) -> list[tuple[str, str]]:
    """Parse .github/patterns.txt -> [(slug, stem), ...], skipping comments/blanks."""
    path = repo / ".github" / "patterns.txt"
    if not path.exists():
        die(f"{path} not found")
    pairs: list[tuple[str, str]] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            die(f"malformed patterns.txt line (want slug:Stem): {raw!r}")
        slug, stem = line.split(":", 1)
        pairs.append((slug.strip(), stem.strip()))
    return pairs


def top_level_helpers(repo: Path) -> list[Path]:
    """Reusable Swami helper sources: app/Swami/*.swift, excluding @main entries."""
    swami = repo / "app" / "Swami"
    out: list[Path] = []
    for p in sorted(swami.glob("*.swift")):
        text = p.read_text()
        if re.search(r"^\s*@main\b", text, re.MULTILINE):
            continue  # never vendor an app entry point
        out.append(p)
    return out


def strip_noncode(text: str) -> str:
    """Drop comments, string literals, and import lines so symbol scans see only code.

    A small state machine, not a full Swift lexer, but enough to stop identifiers that
    live in doc comments (`/// # Interaction - Drag`) or in the module name (`import
    Swami`) from being mistaken for real code references.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        two = text[i:i + 2]
        if two == "//":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if two == "/*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if text[i:i + 3] == '"""':
            j = text.find('"""', i + 3)
            i = n if j == -1 else j + 3
            out.append(" ")
            continue
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            out.append(" ")
            continue
        out.append(c)
        i += 1
    code = "".join(out)
    # Import lines name modules, not the helper types they might share a name with.
    code = re.sub(r"^\s*import\s+.*$", "", code, flags=re.MULTILINE)
    return code


def _exported_symbols(text: str) -> set[str]:
    """Identifiers a helper file exposes: top-level type names + View-extension methods."""
    text = strip_noncode(text)
    syms: set[str] = set()
    for m in re.finditer(
        r"\b(?:struct|class|enum|protocol|actor)\s+([A-Za-z_][A-Za-z0-9_]*)", text
    ):
        syms.add(m.group(1))
    # `public extension View { func drag(...) }` and `func interaction(...)` etc.
    for block in re.finditer(r"extension\s+View\s*\{(.*?)\n\}", text, re.DOTALL):
        for fm in re.finditer(r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", block.group(1)):
            syms.add(fm.group(1))
    return syms


def prune_helpers(pattern_text: str, helpers: list[Path]) -> list[Path]:
    """Best-effort minimal set: keep a helper if its symbols are referenced, transitively.

    Correct for Swami's flat, self-contained helpers. If it ever under-includes, the
    Xcode build fails loudly in CI -> fall back to the default (vendor all).
    """
    index = {p: _exported_symbols(p.read_text()) for p in helpers}

    def referenced(text: str, syms: set[str]) -> bool:
        text = strip_noncode(text)
        for s in syms:
            if re.search(rf"\.{re.escape(s)}\s*\(", text):  # .drag( / .interaction(
                return True
            if re.search(rf"\b{re.escape(s)}\b", text):  # RoundedTriangle, Drag, ...
                return True
        return False

    kept: dict[Path, str] = {}
    frontier = [(p, syms) for p, syms in index.items() if referenced(pattern_text, syms)]
    while frontier:
        p, _ = frontier.pop()
        if p in kept:
            continue
        kept[p] = p.read_text()
        for q, syms in index.items():
            if q not in kept and referenced(kept[p], syms):
                frontier.append((q, syms))
    return sorted(kept, key=lambda p: p.name)


def git_sha(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def sanitize_bundle(stem: str) -> str:
    ident = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-")
    return f"{BUNDLE_PREFIX}.{ident}"


# ----------------------------------------------------------------------------- assembly


def assemble(repo: Path, stem: str, out_dir: Path, vendor_all: bool, make_zip: bool,
             sha: str | None) -> Path | None:
    pattern_src = repo / "app" / "Swami" / "Patterns" / f"{stem}.swift"
    if not pattern_src.exists():
        print(f"package_sample: skip {stem}: no {pattern_src.relative_to(repo)}",
              file=sys.stderr)
        return None

    view = f"{stem}View"
    pattern_text = pattern_src.read_text()
    if view not in pattern_text:
        die(f"{pattern_src.name}: expected view type {view} not found")

    helpers_all = top_level_helpers(repo)
    helpers = helpers_all if vendor_all else prune_helpers(pattern_text, helpers_all)
    if not helpers:
        # A pattern that touches no helper still needs the Swami target to exist;
        # vendor the smallest real helper set rather than emit an empty module.
        helpers = helpers_all

    pkg_dir = out_dir / f"{stem}.swiftpm"
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    (pkg_dir / "App").mkdir(parents=True)
    (pkg_dir / "Swami").mkdir(parents=True)

    # Pattern view — verbatim.
    shutil.copyfile(pattern_src, pkg_dir / "App" / f"{stem}.swift")
    # Helpers — verbatim.
    for h in helpers:
        shutil.copyfile(h, pkg_dir / "Swami" / h.name)

    # Generated files.
    (pkg_dir / "Package.swift").write_text(PACKAGE_SWIFT.format(
        tools_version=TOOLS_VERSION, pattern=stem, deployment=DEPLOYMENT_IOS,
        bundle_id=sanitize_bundle(stem)))
    (pkg_dir / "App" / "SampleApp.swift").write_text(APP_SWIFT.format(
        pattern=stem, view=view))
    (pkg_dir / "README.md").write_text(README_MD.format(pattern=stem))
    (pkg_dir / "sample-manifest.json").write_text(json.dumps({
        "patternID": stem,
        "view": view,
        "generator": "package_sample.py",
        "generatorVersion": GENERATOR_VERSION,
        "toolsVersion": TOOLS_VERSION,
        "deploymentTarget": f"iOS {DEPLOYMENT_IOS}",
        "vendorMode": "all" if vendor_all else "prune",
        "vendoredHelpers": [h.name for h in helpers],
        "sourceCommit": sha,
    }, indent=2) + "\n")

    # Static sanity checks (no compiler available in generic CI).
    problems = static_check(pkg_dir, stem, view)
    if problems:
        die(f"{stem}: static check failed:\n  " + "\n  ".join(problems))

    zip_path = None
    if make_zip:
        zip_path = out_dir / f"{stem}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(pkg_dir.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(out_dir))
    print(f"package_sample: built {pkg_dir.name}"
          + (f" -> {zip_path.name} ({zip_path.stat().st_size} B)" if zip_path else "")
          + f"  helpers={[h.name for h in helpers]}")
    return zip_path


def static_check(pkg_dir: Path, stem: str, view: str) -> list[str]:
    """Toolchain-free correctness gate: entry, imports, and referenced symbols resolve."""
    problems: list[str] = []
    app = (pkg_dir / "App").glob("*.swift")
    app_texts = {p.name: p.read_text() for p in app}
    swami_texts = {p.name: p.read_text() for p in (pkg_dir / "Swami").glob("*.swift")}

    joined_app = "\n".join(app_texts.values())

    if "@main" not in joined_app:
        problems.append("no @main in App/")
    if view + "()" not in joined_app:
        problems.append(f"SampleApp does not instantiate {view}()")

    # If the pattern imports Swami, the vendored Swami target must be non-empty.
    if re.search(r"^\s*import\s+Swami\b", app_texts.get(f"{stem}.swift", ""),
                 re.MULTILINE) and not swami_texts:
        problems.append("pattern imports Swami but no helper sources vendored")

    # Every Swami-qualified / patch-modifier symbol the pattern uses must be defined
    # somewhere in the vendored sources. Check the View-extension methods it calls.
    provided_methods: set[str] = set()
    for t in swami_texts.values():
        provided_methods |= _exported_symbols(t)
    for m in re.finditer(r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", app_texts.get(f"{stem}.swift", "")):
        name = m.group(1)
        # Only worry about names that look like Swami patch modifiers we know of.
        if name in ("drag", "interaction") and name not in provided_methods:
            problems.append(f"pattern calls .{name}(...) but no vendored helper defines it")
    return problems


# ----------------------------------------------------------------------------- cli


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Assemble downloadable Swami .swiftpm samples.")
    ap.add_argument("--repo", type=Path, default=Path.cwd(),
                    help="Swami repo root (default: cwd).")
    ap.add_argument("--out", type=Path, required=True, help="Output directory.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pattern", help="Single pattern stem, e.g. Interaction_Drag.")
    g.add_argument("--all", action="store_true", help="Build every stem in patterns.txt.")
    ap.add_argument("--prune", action="store_true",
                    help="Vendor only the helpers the pattern references (default: vendor all).")
    ap.add_argument("--no-zip", action="store_true", help="Emit the .swiftpm dir only.")
    args = ap.parse_args(argv)

    repo = args.repo.resolve()
    if not (repo / "app" / "Swami").is_dir():
        die(f"{repo} does not look like the Swami repo (no app/Swami)")
    args.out.mkdir(parents=True, exist_ok=True)

    sha = git_sha(repo)
    vendor_all = not args.prune
    make_zip = not args.no_zip

    if args.all:
        built = skipped = 0
        for _slug, stem in read_patterns_txt(repo):
            if assemble(repo, stem, args.out, vendor_all, make_zip, sha) is None:
                skipped += 1
            else:
                built += 1
        print(f"package_sample: built {built}, skipped {skipped} (no .swift) "
              f"from patterns.txt")
    else:
        assemble(repo, args.pattern, args.out, vendor_all, make_zip, sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
