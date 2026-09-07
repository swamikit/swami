#!/usr/bin/env python3
"""Give a transformed DocC archive a working, explicit landing redirect."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def prepare(site: Path, hosting_base: str, landing_path: str) -> str:
    target = f"{hosting_base.rstrip('/')}/{landing_path.strip('/')}/"
    landing = site / landing_path.strip("/") / "index.html"
    if not landing.is_file():
        raise FileNotFoundError(f"DocC landing page is missing: {landing}")
    encoded = json.dumps(target)
    document = "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        f'  <meta http-equiv="refresh" content="0; url={html.escape(target, quote=True)}">',
        f'  <link rel="canonical" href="{html.escape(target, quote=True)}">',
        "  <title>Swami Documentation</title>",
        "</head>",
        f'<body data-docc-redirect="{html.escape(target, quote=True)}">',
        f"  <script>window.location.replace({encoded});</script>",
        f'  <a href="{html.escape(target, quote=True)}">Open Swami documentation</a>',
        "</body>",
        "</html>",
        "",
    ])
    (site / "index.html").write_text(document, encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site", type=Path)
    parser.add_argument("--hosting-base", required=True)
    parser.add_argument("--landing-path", required=True)
    args = parser.parse_args()
    print(f"DocC entrypoint redirects to {prepare(args.site, args.hosting_base, args.landing_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
