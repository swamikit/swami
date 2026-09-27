#!/usr/bin/env python3
"""Assemble downloadable Xcode samples ("App Playground" .swiftpm) for Swami patterns.

Given a pattern stem (or `--all`, driven by .github/patterns.txt), this gathers:

  * the pattern's own `.swift`,
  * the Swami helper sources it needs (vendored so the sample is self-contained),
  * a generated `@main` App entry, a templated `Package.swift`, a README, a manifest,

and writes a `<PatternID>.swiftpm` directory plus a `<PatternID>.zip` that opens in
Xcode 15+ (and Swift Playgrounds on iPad) and runs as an iOS app showing exactly that
one pattern.

SINGLE-TARGET, ONE MODULE. In the Swami repo, patterns AND helpers all live in the one
`Swami` framework module, so a pattern references a helper (e.g. `RoundedTriangle`, the
`.drag` modifier) with NO import. To reproduce that reality — and to compile both the
import-Swami patterns (Interaction_Drag) and the no-import ones (Interaction_Pinch) —
the sample is a single `.executableTarget`: SampleApp.swift + the pattern view + every
vendored helper `.swift`, all in one module. The ONE deterministic edit to a copied
source is stripping any `^import Swami$` line (no separate Swami module exists here, so
that import would error "no such module 'Swami'"); everything else is verbatim.

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
GENERATOR_VERSION = "2.0"  # 2.x = single-target layout

IMPORT_SWAMI = re.compile(r"^\s*import\s+Swami\s*$")

# ----------------------------------------------------------------------------- templates

PACKAGE_SWIFT = """\
// swift-tools-version: {tools_version}

// Swami sample — {pattern}.
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
"""

APP_SWIFT = """\
import SwiftUI

// Downloadable Swami sample — {pattern}.
//
// This is a self-contained, single-target App Playground: open the enclosing `.swiftpm`
// in Xcode 15+ and press Run to launch the pattern as an iOS app in the Simulator (or on
// a device). The one screen renders `{view}` — the exact pattern view from the Swami
// gallery — and nothing else.
//
// The pattern view (`{pattern}.swift`) and the Swami helper sources it uses are all in
// this one module, so no `import Swami` is needed and no external checkout is required.
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

This is a standard **single-target App Playground**, so it also opens directly in
**Swift Playgrounds on iPad** — no restructuring needed.

## What's inside

One app target (one module); everything compiles together:

- `Package.swift` — App Playground manifest (`.iOSApplication` product).
- `SampleApp.swift` — `@main`; hosts the pattern view and nothing else.
- `{pattern}.swift` — the pattern view, from the Swami repo.
{helpers}

## One edit from the repo source

Swami ships patterns and helpers in a single module, so a pattern refers to helpers
(e.g. `RoundedTriangle`, the `.drag` modifier) with no import. This sample is also a
single module. The only change from the repo file is that a leading `import Swami` line
(present in some patterns, absent in others) is removed — with no separate `Swami`
module here it would fail to build with "no such module 'Swami'". Everything else is
byte-for-byte the repo source. See `sample-manifest.json` for which files were touched.

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
        if re.search(r"^\s*@main\b", p.read_text(), re.MULTILINE):
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
    code = re.sub(r"^\s*import\s+.*$", "", code, flags=re.MULTILINE)
    return code


def helper_symbols(text: str) -> tuple[set[str], set[str], set[tuple[str, str]]]:
    """What a helper file exposes, as (types, members, inits).

    - types:   struct/class/enum/protocol/actor/typealias names   -> used as `\\bName\\b`
    - members: func/var names declared inside any `extension`      -> used as `.name`
    - inits:   (ExtendedType, firstLabel) from `extension T { init(l: ...) }`
               (e.g. Color.init(hex:))                             -> used as `T(l:`
    """
    code = strip_noncode(text)
    types = set(re.findall(
        r"\b(?:struct|class|enum|protocol|actor|typealias)\s+([A-Za-z_][A-Za-z0-9_]*)",
        code))
    members: set[str] = set()
    inits: set[tuple[str, str]] = set()
    # Match each `extension T ... { ... }` body up to its column-0 closing brace.
    for m in re.finditer(r"extension\s+([A-Za-z_][A-Za-z0-9_]*)[^\{]*\{(.*?)\n\}",
                         code, re.DOTALL):
        target, body = m.group(1), m.group(2)
        members |= set(re.findall(r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*[<(]", body))
        # Computed properties only (`var name: T {`); excludes stored/local vars.
        members |= set(re.findall(
            r"\bvar\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*[^={\n]+\{", body))
        inits |= {(target, lbl) for lbl in
                  re.findall(r"\binit\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", body)}
    return types, members, inits


def provided_tokens(texts: list[str]) -> set[tuple]:
    """The set of reference tokens the given sources DEFINE."""
    toks: set[tuple] = set()
    for t in texts:
        types, members, inits = helper_symbols(t)
        toks |= {("type", x) for x in types}
        toks |= {("member", x) for x in members}
        toks |= {("init", a, b) for (a, b) in inits}
    return toks


def used_tokens(code: str, universe: set[tuple]) -> set[tuple]:
    """Which of `universe`'s tokens the given code actually references."""
    code = strip_noncode(code)
    hit: set[tuple] = set()
    for tok in universe:
        if tok[0] == "type" and re.search(rf"\b{re.escape(tok[1])}\b", code):
            hit.add(tok)
        elif tok[0] == "member" and re.search(rf"\.{re.escape(tok[1])}\b", code):
            hit.add(tok)
        elif tok[0] == "init" and re.search(
                rf"\b{re.escape(tok[1])}\s*\(\s*{re.escape(tok[2])}\s*:", code):
            hit.add(tok)
    return hit


def prune_helpers(pattern_text: str, helpers: list[Path]) -> list[Path]:
    """Minimal set: keep a helper if any token it provides is used by the pattern or by
    an already-kept helper (transitive fixpoint).

    Reliable for Swami's flat, self-contained helpers. If it ever under-includes, the
    strengthened static_check below fails the ASSEMBLY (not the Xcode build), so the CI
    error is clear; the safe fallback is the default (vendor all).
    """
    texts = {p: p.read_text() for p in helpers}
    provides = {p: provided_tokens([texts[p]]) for p in helpers}
    kept: list[Path] = []
    corpus = [pattern_text]
    while True:
        combined = "\n".join(corpus)
        added = False
        for p in helpers:
            if p in kept:
                continue
            if used_tokens(combined, provides[p]):
                kept.append(p)
                corpus.append(texts[p])
                added = True
        if not added:
            break
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


def copy_stripping_swami_import(src: Path, dst: Path) -> bool:
    """Copy src -> dst, dropping any `import Swami` line. Returns True if a line was cut."""
    lines = src.read_text().splitlines(keepends=True)
    kept = [ln for ln in lines if not IMPORT_SWAMI.match(ln.rstrip("\r\n"))]
    dst.write_text("".join(kept))
    return len(kept) != len(lines)


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
        helpers = helpers_all  # never emit an empty helper set

    pkg_dir = out_dir / f"{stem}.swiftpm"
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir(parents=True)

    # Single module: pattern view + helpers + @main all at the package root.
    transformed: list[str] = []
    if copy_stripping_swami_import(pattern_src, pkg_dir / f"{stem}.swift"):
        transformed.append(f"{stem}.swift")
    for h in helpers:
        if copy_stripping_swami_import(h, pkg_dir / h.name):
            transformed.append(h.name)

    helper_bullets = "\n".join(
        f"- `{h.name}` — vendored Swami helper source." for h in helpers)
    (pkg_dir / "Package.swift").write_text(PACKAGE_SWIFT.format(
        tools_version=TOOLS_VERSION, pattern=stem, deployment=DEPLOYMENT_IOS,
        bundle_id=sanitize_bundle(stem)))
    (pkg_dir / "SampleApp.swift").write_text(APP_SWIFT.format(pattern=stem, view=view))
    (pkg_dir / "README.md").write_text(README_MD.format(pattern=stem, helpers=helper_bullets))
    (pkg_dir / "sample-manifest.json").write_text(json.dumps({
        "patternID": stem,
        "view": view,
        "generator": "package_sample.py",
        "generatorVersion": GENERATOR_VERSION,
        "layout": "single-target",
        "toolsVersion": TOOLS_VERSION,
        "deploymentTarget": f"iOS {DEPLOYMENT_IOS}",
        "vendorMode": "all" if vendor_all else "prune",
        "vendoredHelpers": [h.name for h in helpers],
        "transform": r"removed lines matching ^\s*import\s+Swami\s*$",
        "transformedFiles": transformed,
        "sourceCommit": sha,
    }, indent=2) + "\n")

    problems = static_check(pkg_dir, stem, view, helpers_all)
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


def static_check(pkg_dir: Path, stem: str, view: str,
                 repo_helpers: list[Path]) -> list[str]:
    """Toolchain-free correctness gate for the single-target sample."""
    problems: list[str] = []
    srcs = {p.name: p.read_text() for p in pkg_dir.glob("*.swift")}
    pattern_name = f"{stem}.swift"
    pattern_text = srcs.get(pattern_name, "")
    joined = "\n".join(srcs.values())

    # (0) structural: exactly one @main, and SampleApp instantiates the pattern view.
    if "SampleApp.swift" not in srcs:
        problems.append("SampleApp.swift missing")
    if not pattern_text:
        problems.append(f"{pattern_name} missing")
    main_count = len(re.findall(r"^\s*@main\b", joined, re.MULTILINE))
    if main_count != 1:
        problems.append(f"expected exactly one @main, found {main_count}")
    if f"{view}()" not in srcs.get("SampleApp.swift", ""):
        problems.append(f"SampleApp does not instantiate {view}()")

    # (a) no leftover `import Swami` anywhere (single module has no such module).
    for name, text in srcs.items():
        if any(IMPORT_SWAMI.match(ln) for ln in text.splitlines()):
            problems.append(f"{name}: leftover `import Swami` (single-target has no Swami module)")

    # (b) every Swami helper symbol referenced (types, members, inits) is vendored.
    #     Scan the pattern AND the vendored helpers, so a vendored helper that needs an
    #     un-vendored one is caught here, not by Xcode.
    universe = provided_tokens([p.read_text() for p in repo_helpers])
    vendored = provided_tokens([t for n, t in srcs.items()
                                if n not in (pattern_name, "SampleApp.swift")])
    consumer = pattern_text + "\n" + "\n".join(
        t for n, t in srcs.items() if n not in (pattern_name, "SampleApp.swift"))
    missing = used_tokens(consumer, universe) - vendored
    for tok in sorted(missing):
        label = tok[1] if tok[0] != "init" else f"{tok[1]}(init:{tok[2]})"
        problems.append(f"references Swami {tok[0]} `{label}` but no vendored source defines it")
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
