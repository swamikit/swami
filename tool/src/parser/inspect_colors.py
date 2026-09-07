#!/usr/bin/env python3
"""Enhanced color inspector: scan the placed region for color tokens and patterns.

Uses the same Graph class as origami_graph.py to walk FlatBuffers tables in the
placed subtree looking for known-shaped records. This version improves on the
earlier scan by:
- Looking for solid colors (alpha=255) which are likely layer fills
- Tracking color frequency to identify dominant colors
- Correlating color positions with table structures

Color channel order: Origami uses ColorKit which stores colors as uint32.
The channel order depends on the platform:
- iOS: ABGR in the uint32 (matches iOS CGColor)
- macOS: same representation in memory

For hex strings in the file, ColorKit typically stores as RGBA in hex notation.
"""
import sys, pathlib, json, struct
from collections import Counter

# Use the same Graph class and parse logic as origami_graph.py
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from parser.origami_graph import Graph, read_graph_bytes, parse  # noqa: E402


def scan_solid_colors(g, tail, threshold=200):
    """Scan for solid colors (alpha >= threshold) in the placed region.
    
    Returns colors sorted by frequency (most common first).
    """
    data = g.d
    colors = Counter()
    
    for i in range(tail, len(data) - 4, 4):
        try:
            v = struct.unpack_from('<I', data, i)[0]
            r = (v >> 16) & 0xFF
            g_val = (v >> 8) & 0xFF
            b = v & 0xFF
            a = (v >> 24) & 0xFF
            
            # Solid color: high alpha
            if a >= threshold and a <= 255:
                if 10 < r < 250 and 10 < g_val < 250 and 10 < b < 250:
                    colors[(r, g_val, b, a)] += 1
        except:
            pass
    
    return colors


def scan_translucent_colors(g, tail, min_alpha=5, max_alpha=100):
    """Scan for translucent colors (semi-transparent backgrounds) in the placed region."""
    data = g.d
    colors = []
    
    for i in range(tail, len(data) - 4, 4):
        try:
            v = struct.unpack_from('<I', data, i)[0]
            r = (v >> 16) & 0xFF
            g_val = (v >> 8) & 0xFF
            b = v & 0xFF
            a = (v >> 24) & 0xFF
            
            if min_alpha <= a <= max_alpha:
                if 10 < r < 250 and 10 < g_val < 250 and 10 < b < 250:
                    colors.append({
                        'pos': i,
                        'hex': f'{v:08X}',
                        'rgba': (r, g_val, b, a),
                        'alpha_ratio': a / 255.0
                    })
        except:
            pass
    
    return colors


def analyze_dragsettings_colors(g, out):
    """Extract color information from DragSettings tables."""
    data = g.d
    results = []
    
    for node in out.get('placed_nodes', []):
        if 'DragSettings' in node.get('type', ''):
            t = node['table']
            # Look at raw bytes near this table
            for offset in range(0, 100, 4):
                pos = t + offset
                if pos + 4 <= len(data):
                    v = struct.unpack_from('<I', data, pos)[0]
                    r = (v >> 16) & 0xFF
                    g_val = (v >> 8) & 0xFF
                    b = v & 0xFF
                    a = (v >> 24) & 0xFF
                    
                    if a >= 200 and a <= 255:  # Solid colors
                        if 100 < r < 255 and 100 < g_val < 255 and 100 < b < 255:
                            results.append({
                                'table': t,
                                'offset': offset,
                                'pos': pos,
                                'hex': f'{v:08X}',
                                'rgba': (r, g_val, b, a),
                                'type': 'solid_tan' if (r > 200 and g_val > 150 and b < 200) else 'other'
                            })
    
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: inspect_colors.py <origami_file>")
        sys.exit(1)
    
    path = sys.argv[1]
    data = read_graph_bytes(path)
    g = Graph(data)
    
    # Parse to get placed_root_offset
    out = parse(path)
    tail = out.get('placed_root_offset', 0) or 0
    
    print(f"File: {path}")
    print(f"File size: {g.N}")
    print(f"Placed root offset: {tail}")
    print()
    
    # Scan for solid colors
    print("=== Solid colors (alpha >= 200) ===")
    solid_colors = scan_solid_colors(g, tail)
    for (r, g_val, b, a), count in solid_colors.most_common(20):
        print(f"  rgba({r},{g_val},{b},{a}) count={count}")
    
    print()
    print("=== Translucent colors (5 <= alpha <= 100) ===")
    translucent = scan_translucent_colors(g, tail)
    for c in translucent[:10]:
        print(f"  pos={c['pos']}: rgba({c['rgba'][0]},{c['rgba'][1]},{c['rgba'][2]},{c['rgba'][3]}) alpha={c['alpha_ratio']:.2f}")
    
    print()
    print("=== DragSettings color analysis ===")
    dragsettings_colors = analyze_dragsettings_colors(g, out)
    for c in dragsettings_colors:
        print(f"  table={c['table']} offset={c['offset']} hex={c['hex']} rgba={c['rgba']} type={c['type']}")
    
    # Summary JSON
    summary = {
        'file': path,
        'placed_root_offset': tail,
        'solid_colors': [{'rgba': list(k), 'count': v} for k, v in solid_colors.most_common(10)],
        'dragsettings_colors': dragsettings_colors,
        'translucent_sample': translucent[:5]
    }
    print()
    print("JSON Summary:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
