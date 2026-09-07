#!/usr/bin/env python3
"""Fail when a transformed DocC site would load blank at its hosting base."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit


BASE_URL = re.compile(r"\bbaseUrl\s*=\s*['\"]([^'\"]+)['\"]")
ASSET = re.compile(r"(?:src|href)=['\"]([^'\"]+)['\"]", re.IGNORECASE)
REDIRECT = re.compile(r"data-docc-redirect=['\"]([^'\"]+)['\"]")


def validate(site: Path, hosting_base: str, landing_path: str = "documentation/swami") -> list[str]:
    errors: list[str] = []
    if not hosting_base.startswith("/") or hosting_base.endswith("/"):
        errors.append("hosting base must start with '/' and omit the trailing slash")
        return errors
    index = site / "index.html"
    if not index.is_file():
        return ["site/index.html is missing"]
    entrypoint = index.read_text(encoding="utf-8", errors="replace")
    target = f"{hosting_base}/{landing_path.strip('/')}/"
    redirect = REDIRECT.search(entrypoint)
    if redirect is None or redirect.group(1) != target:
        errors.append(f"root entrypoint does not redirect to {target}")
    landing = site / landing_path.strip("/") / "index.html"
    if not landing.is_file():
        errors.append(f"landing page is missing: {landing_path.strip('/')}/index.html")
        return errors
    html = landing.read_text(encoding="utf-8", errors="replace")
    match = BASE_URL.search(html)
    if match is None:
        errors.append("index.html does not declare DocC baseUrl")
    elif match.group(1).rstrip("/") != hosting_base:
        errors.append(f"baseUrl is {match.group(1)!r}; expected {hosting_base!r}")

    local_assets = 0
    for raw in ASSET.findall(html):
        parsed = urlsplit(raw)
        if parsed.scheme or parsed.netloc or raw.startswith(("#", "data:")):
            continue
        path = parsed.path
        if not path or path == "/":
            continue
        if path.startswith("/"):
            prefix = hosting_base + "/"
            if not path.startswith(prefix):
                errors.append(f"absolute asset escapes hosting base: {path}")
                continue
            relative = path[len(prefix):]
        else:
            relative = path
        local_assets += 1
        if not (site / relative).is_file():
            errors.append(f"referenced asset is missing: {relative}")
    if local_assets == 0:
        errors.append("index.html references no local assets")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site", type=Path)
    parser.add_argument("--hosting-base", required=True)
    parser.add_argument("--landing-path", default="documentation/swami")
    args = parser.parse_args()
    errors = validate(args.site, args.hosting_base, args.landing_path)
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    print(f"DocC site resolves under {args.hosting_base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
