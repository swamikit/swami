#!/usr/bin/env python3
"""Ad-hoc deep decode of the Interaction_Drag placed graph (analysis tool)."""
import sys, struct, zipfile, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / 'src'))
from parser.origami_graph import Graph, read_graph_bytes  # noqa: E402

data = read_graph_bytes('/tmp/Interaction_Drag.origami')
g = Graph(data)
tail = g.placed_root_offset()
N = len(data)


def f32(p):
    return struct.unpack_from('<f', data, p)[0]


def classify(t):
    """Dump one table: field index -> interpretations."""
    info = g.table(t)
    if not info:
        return None
    tab, vt, vs, ts = info
    fields = []
    n = (vs - 4) // 2
    for i in range(n):
        fo = g.u16(vt + 4 + i * 2)
        if not fo or fo >= ts:
            continue
        slot = t + fo
        if slot + 4 > N:
            continue
        v = g.u32(slot)
        entry = {'i': i, 'off': slot, 'u32': v}
        s = g.astr(slot + v) if 0 < v < N else None
        if s is not None:
            entry['str'] = s
        entry['f32'] = round(f32(slot), 6)
        entry['i32'] = g.i32(slot)
        tgt = slot + v
        if 0 < v < 0x200000 and tgt + 4 <= N:
            tinfo = g.table(tgt)
            if tinfo:
                entry['table'] = tgt
            else:
                cnt = g.u32(tgt)
                if 0 < cnt < 4096 and tgt + 4 + cnt * 4 <= N:
                    entry['vec'] = (tgt, cnt)
        fields.append(entry)
    return fields


def enum_tables_in_range(lo, hi):
    out = []
    t = lo
    while t < hi - 8:
        info = g.table(t)
        if info:
            tab, vt, vs, ts = info
            if vt >= lo and vt + vs <= hi and ts >= 8:
                out.append(t)
                t = tab + ts
                continue
        t += 4
    return out


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'dump'
    if which == 'dump':
        # Dump specific tables of interest
        for t in [int(x) for x in sys.argv[2:]]:
            print('=' * 70)
            print(f'table {t}')
            for f in (classify(t) or []):
                print('  ', f)
    elif which == 'scan':
        # scan for tables whose decoded fields include a given float value
        target = float(sys.argv[2])
        lo, hi = int(sys.argv[3]), int(sys.argv[4])
        for t in enum_tables_in_range(lo, hi):
            for f in (classify(t) or []):
                if abs(f['f32'] - target) < 1e-6:
                    print(f'table {t} field{f["i"]} f32={f["f32"]} u32={f["u32"]} off={f["off"]}')
