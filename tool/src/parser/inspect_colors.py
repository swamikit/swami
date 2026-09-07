#!/usr/bin/env python3
"""Lightweight inspector: scan the placed region for color tokens.

Uses the same Graph class as origami_graph.py to walk FlatBuffers tables in the
placed subtree looking for known-shaped records:
- Color tokens: a table with a string `hex` field (8-char hex).
- Radius/cornerRadius fields on layer tables.

This fixes the earlier bug where inspect_colors.py iterated the full file byte
range rather than the placed region, causing reads past EOF.
"""
import sys, pathlib, json

# Use the same Graph class and parse logic as origami_graph.py
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from parser.origami_graph import Graph, read_graph_bytes, parse  # noqa: E402

# Color channel order helpers (Origami uses ColorKit = ARGB in hex).
def hex_to_argb(h):
    """Parse 8-char hex as ARGB, return (r, g, b, a) 0..1 tuple."""
    v = int(h, 16)
    return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF, (v >> 24) & 0xFF


def scan_for_colors(g, placed_root):
    """Scan tables in the placed region for hex-string fields matching 8-char hex.

    Unlike the earlier scan that iterated raw byte offsets (causing EOF reads),
    this walks the placed node tables from the parser's own list and also
    scans for adjacent table offsets using the vtable as the boundary signal.
    """
    results = []
    seen = set()

    # First: walk tables near the known placed node offsets (from the parser).
    # These are validated tables. Extract their decoded fields and look for hex.
    out = parse(sys.argv[1])
    for node in out.get("placed_nodes", []):
        t = node["table"]
        info = g.table(t)
        if not info:
            continue
        rec = g.decode(info)
        # Look for hex fields
        for k, v in rec.items():
            if isinstance(v, str) and len(v) == 8 and all(c in '0123456789ABCDEFabcdef' for c in v):
                if t not in seen:
                    seen.add(t)
                    r, gr, b, a = hex_to_argb(v)
                    results.append({
                        "table": t,
                        "type": node["type"],
                        "name": node.get("name"),
                        "hex": v,
                        "argb_interpretation": {
                            "r": r, "g": gr, "b": b, "a": a,
                            "css": f"rgba({r},{gr},{b},{a/255:.3f})"
                        },
                        "rrggbbaa_interpretation": {
                            "r": int(v[0:2], 16),
                            "g": int(v[2:4], 16),
                            "b": int(v[4:6], 16),
                            "a": int(v[6:8], 16),
                            "css": f"rgba({int(v[0:2],16)},{int(v[2:4],16)},{int(v[4:6],16)},{int(v[6:8],16)/255:.3f})"
                        }
                    })

    return results


def scan_for_radius(g, placed_root):
    """Scan the placed region for tables with radius or cornerRadius fields.

    Uses the vtable-based table detection to avoid EOF reads.
    """
    results = []
    seen = set()

    # Walk vtables in the placed region using the vtable sentinel:
    # A valid vtable has vs >= 4, even, and ts >= 8.
    N = g.N
    for t in range(placed_root, N - 16):
        info = g.table(t)
        if not info:
            continue
        rec = g.decode(info)
        has_radius = False
        radius_val = None
        for k, v in rec.items():
            if k in ('radius', 'cornerRadius') and isinstance(v, (int, float)):
                has_radius = True
                radius_val = v
        if has_radius and t not in seen:
            seen.add(t)
            results.append({"table": t, "radius": radius_val, "fields": {k: v for k, v in rec.items() if k != 'table'}})

    return results


def main():
    path = sys.argv[1]
    data = read_graph_bytes(path)
    g = Graph(data)
    tail = g.placed_root_offset()
    if tail is None:
        tail = 0
    print(f"placed_root = {tail}, file size = {g.N}")

    colors = scan_for_colors(g, tail)
    print(f"\nColor-like tables in placed region: {len(colors)}")
    for c in colors:
        print(f"  table={c['table']} type={c['type']} name={c.get('name')}")
        print(f"    hex = #{c['hex']}")
        print(f"    ARGB:      {c['argb_interpretation']['css']}")
        print(f"    RRGGBBAA: {c['rrggbbaa_interpretation']['css']}")

    radii = scan_for_radius(g, tail)
    print(f"\nRadius-like tables in placed region: {len(radii)}")
    for r in radii[:20]:
        print(f"  table={r['table']} radius={r['radius']}")

    if colors or radii:
        print(f"\nSummary (JSON):")
        print(json.dumps({"colors": colors, "radii": radii}, indent=2))


if __name__ == "__main__":
    main()
