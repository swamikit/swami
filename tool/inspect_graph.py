#!/usr/bin/env python3
"""Inspect the Interaction_Drag.origami FlatBuffers graph for layer values."""
import zipfile, struct, re, pathlib

TYPE_RE = re.compile(rb'(builtin|origami|ios)\.[A-Za-z][A-Za-z0-9.]*')

def read_graph_bytes(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith("graph"))
            return z.read(name)
    return pathlib.Path(path).read_bytes()

class Graph:
    def __init__(self, data):
        self.d = data; self.N = len(data)
        assert data[4:8] == b"ORGM"
    def u16(self, p): return struct.unpack_from('<H', self.d, p)[0]
    def u32(self, p): return struct.unpack_from('<I', self.d, p)[0]
    def i32(self, p): return struct.unpack_from('<i', self.d, p)[0]
    def root(self): return self.u32(0)

    def astr(self, t):
        if t < 0 or t+4 > self.N: return None
        ln = self.u32(t)
        if 0 < ln < 200 and t+4+ln <= self.N:
            s = self.d[t+4:t+4+ln]
            if all(32 <= b < 127 for b in s): return s.decode()
        return None

    def table(self, t):
        if t < 0 or t+4 > self.N: return None
        vt = t - self.i32(t)
        if vt < 0 or vt+4 > self.N: return None
        vs = self.u16(vt)
        if vs < 4 or vs % 2 or vt+vs > self.N: return None
        ts = self.u16(vt+2)
        if ts < 8 or ts > 8000 or t+ts > self.N: return None
        return (t, vt, vs, ts)

    def owner_table_of(self, sobj, back=8000):
        for t in range(max(0, sobj-back), sobj):
            info = self.table(t)
            if not info: continue
            _, vt, vs, ts = info
            for i in range((vs-4)//2):
                fo = self.u16(vt+4+i*2)
                if fo and fo < ts and t+fo+4 <= self.N and t+fo+self.u32(t+fo) == sobj:
                    return info
        return None

    def decode(self, info):
        t, vt, vs, ts = info
        rec = {}
        for i in range((vs-4)//2):
            fo = self.u16(vt+4+i*2)
            if fo and fo < ts and t+fo+4 <= self.N:
                slot = t+fo; v = self.u32(slot)
                s = self.astr(slot+v) if 0 < v < self.N else None
                rec[str(i)] = s if s is not None else v
        return rec

    def field_uoffset_target(self, tinfo, field_idx):
        t, vt, vs, ts = tinfo
        slot_in_vt = 4 + field_idx*2
        if slot_in_vt + 2 > vs: return None
        fo = self.u16(vt + slot_in_vt)
        if not fo or fo + 4 > ts: return None
        slot = t + fo
        if slot + 4 > self.N: return None
        return slot + self.u32(slot)

    def vector_entries(self, vec_off):
        if vec_off < 0 or vec_off + 4 > self.N: return None
        cnt = self.u32(vec_off)
        if cnt > 200000 or vec_off + 4 + cnt*4 > self.N: return None
        out = []
        for i in range(cnt):
            ep = vec_off + 4 + i*4
            out.append(ep + self.u32(ep))
        return out

    def placed_root_offset(self):
        rinfo = self.table(self.root())
        if not rinfo: return None
        vec_off = self.field_uoffset_target(rinfo, 14)
        if vec_off is None: return None
        entries = self.vector_entries(vec_off)
        if not entries: return None
        return entries[0]

g = Graph(read_graph_bytes('/tmp/Interaction_Drag.origami'))
tail = g.placed_root_offset()
print(f"placed_root_offset: {tail}")

# Key layer tables
key_tables = {
    'Rectangle (bg frame)': 495000,
    'Interaction layer': 502284,
    'Rectangle (drag card)': 504168,
    'Artboard 1': 529636,
    'Radius layer': 521500,
}

for name, offset in key_tables.items():
    info = g.table(offset)
    if info:
        rec = g.decode(info)
        print(f"\n{name} (table={offset}):")
        for k, v in rec.items():
            print(f"  field[{k}] = {v!r}")
    else:
        print(f"\n{name}: no table at {offset}")

# Look at DragSettings named "Drag Settings"
for tname, toff in [("Drag Settings", 518300), ("DragSettings unnamed", 518344)]:
    info = g.table(toff)
    if info:
        print(f"\n{tname} (table={toff}):")
        print(g.decode(info))

# Look at Drag named "Drag"
info = g.table(519788)
if info:
    print(f"\nDrag (table=519788):")
    print(g.decode(info))

# Scan u32s near layer tables
print("\n\n=== u32 scan near layer tables ===")
for name, base in [("Rectangle bg", 495000), ("Rectangle card", 504168), ("Artboard", 529636)]:
    print(f"\n{name} (from {base-16} to {base+256}):")
    for i in range(-4, 64):
        off = base + i*4
        if 0 <= off < g.N:
            val = g.u32(off)
            i32val = g.i32(off)
            if val != 0:
                if 1000 < val < 0x10000000:
                    print(f"  +{i*4:4d}: u32={val:10d}  /100={val/100.0:.2f}  /1000={val/1000.0:.3f}")
                elif val >= 0x10000000:
                    if abs(i32val) > 100:
                        print(f"  +{i*4:4d}: i32={i32val:12d}  /100={i32val/100.0:.2f}")

# Find RGBA values
print("\n\n=== Potential RGBA u32s ===")
for off in range(495000, 495300, 4):
    val = g.u32(off)
    if val > 0xFFFFFF:
        r = (val >> 0) & 0xFF
        gg = (val >> 8) & 0xFF
        b = (val >> 16) & 0xFF
        a = (val >> 24) & 0xFF
        print(f"  {off}: 0x{val:08X} = RGBA({r},{gg},{b},{a})")

for off in range(504168, 504468, 4):
    val = g.u32(off)
    if val > 0xFFFFFF:
        r = (val >> 0) & 0xFF
        gg = (val >> 8) & 0xFF
        b = (val >> 16) & 0xFF
        a = (val >> 24) & 0xFF
        print(f"  {off}: 0x{val:08X} = RGBA({r},{gg},{b},{a})")

for off in range(529636, 529936, 4):
    val = g.u32(off)
    if val > 0xFFFFFF:
        r = (val >> 0) & 0xFF
        gg = (val >> 8) & 0xFF
        b = (val >> 16) & 0xFF
        a = (val >> 24) & 0xFF
        print(f"  {off}: 0x{val:08X} = RGBA({r},{gg},{b},{a})")

# Float scan
print("\n\n=== Float scan near layer tables ===")
for name, base in [("Rectangle bg", 495000), ("Rectangle card", 504168), ("Artboard", 529636)]:
    print(f"\n{name} (from {base} to {base+400}):")
    for off in range(base, min(base+400, g.N-4), 4):
        val_bytes = g.d[off:off+4]
        fval = struct.unpack('<f', val_bytes)[0]
        if 0.1 <= abs(fval) <= 10000:
            if abs(fval - round(fval*100)/100) < 0.001:
                print(f"  @{off}: float={fval:.2f}")

EOF
