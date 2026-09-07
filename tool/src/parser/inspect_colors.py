#!/usr/bin/env python3
"""Lightweight inspector: scan the placed region for color tokens.

Walks FlatBuffers tables in the placed subtree looking for known-shaped records:
- Color tokens: a table with both a string `name` and an 8-char ASCII `hex`
  field. Origami's ColorKit stores colors as a struct that the parser does not
  decode yet (a parser TODO) — we use this script only to gather evidence
  for the fidelity debts the issue asks us to resolve.
"""
import zipfile, struct, sys, json

def read_graph_bytes(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith("graph"))
            return z.read(name)
    return open(path, 'rb').read()

def decode_table(g, t):
    if t + 16 > len(g): return None
    try:
        vt = t - struct.unpack_from('<i', g, t)[0]
        if vt < 0 or vt + 8 > len(g): return None
        vs = struct.unpack_from('<H', g, vt)[0]
        ts = struct.unpack_from('<H', g, vt + 2)[0]
        if vs < 4 or vs % 2 or vt + vs > len(g): return None
        if ts < 8 or ts > 2000 or t + ts > len(g): return None
    except Exception:
        return None
    rec = {'table': t}
    for i in range((vs - 4) // 2):
        fo = struct.unpack_from('<H', g, vt + 4 + i * 2)[0]
        if fo and fo < ts and t + fo + 4 <= len(g):
            slot = t + fo
            v = struct.unpack_from('<I', g, slot)[0]
            if 0 < v < len(g) - 4:
                ln = struct.unpack_from('<I', g, slot + v)[0]
                if 1 < ln < 200 and slot + v + 4 + ln <= len(g):
                    s = g[slot + v + 4:slot + v + 4 + ln]
                    if all(32 <= b < 127 for b in s):
                        rec[str(i)] = s.decode()
    return rec

def find_color_tables(g, placed_root):
    out = []
    for t in range(placed_root, len(g) - 32):
        rec = decode_table(g, t)
        if rec is None: continue
        if 'hex' in rec and isinstance(rec.get('hex'), str) and len(rec['hex']) == 8 and all(c in '0123456789ABCDEFabcdef' for c in rec['hex']):
            out.append(rec)
    return out

def find_radius_tables(g, placed_root):
    out = []
    for t in range(placed_root, len(g) - 32):
        rec = decode_table(g, t)
        if rec is None: continue
        if any(k in rec for k in ('radius', 'cornerRadius')):
            out.append(rec)
    return out

def main():
    path = sys.argv[1]
    data = read_graph_bytes(path)
    g = data
    N = len(g)
    assert g[4:8] == b'ORGM', "not an ORGM FlatBuffers document"
    root = struct.unpack_from('<I', g, 0)[0]
    vt0 = root - struct.unpack_from('<i', g, root)[0]
    vs0 = struct.unpack_from('<H', g, vt0)[0]
    if 14*2 + 4 < vs0:
        fo = struct.unpack_from('<H', g, vt0 + 4 + 14*2)[0]
        slot = root + fo
        vec = slot + struct.unpack_from('<I', g, slot)[0]
        cnt = struct.unpack_from('<I', g, vec)[0]
        offsets = [vec + 4 + i*4 + struct.unpack_from('<I', g, vec + 4 + i*4)[0] for i in range(cnt)]
        offsets.sort(reverse=True)
        placed_root = offsets[0]
        print(f"placed_root = {placed_root}, file size = {N}")
    else:
        placed_root = 0
        print(f"(no field-14 vector; scanning whole file, size = {N})")

    colors = find_color_tables(g, placed_root)
    print(f"\nColor-like tables in placed region: {len(colors)}")
    for c in colors[:30]:
        print(f"  table={c['table']} {c}")

    print(f"\nRadius-like tables in placed region:")
    radii = find_radius_tables(g, placed_root)
    for r in radii[:30]:
        print(f"  table={r['table']} {r}")

if __name__ == "__main__":
    main()
