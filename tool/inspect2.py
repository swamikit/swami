#!/usr/bin/env python3
"""Walk the FlatBuffers tables and follow uoffset fields to find actual values."""
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
        if 0 < ln < 300 and t+4+ln <= self.N:
            s = self.d[t+4:t+4+ln]
            if all(32 <= b < 127 or b in (10,9) for b in s): return s.decode()
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

    def follow_uoffset(self, slot):
        """Follow a uoffset from a slot to get the target value."""
        if slot + 4 > self.N: return None
        v = self.u32(slot)
        return slot + v if 0 < v < self.N else None

    def read_at_offset(self, off, expected_type=None):
        """Read a value at offset, trying to interpret it."""
        if off is None or off < 0 or off > self.N: return None
        v = self.u32(off)
        # Check if it's a string
        s = self.astr(off)
        if s: return ('string', s)
        # Check if it's a nested table
        info = self.table(off)
        if info: return ('table', info)
        # Check if it's a float (IEEE 754 single)
        fval = struct.unpack('<f', self.d[off:off+4])[0]
        if abs(fval) > 0.01 and abs(fval) < 1e10:
            return ('float', fval)
        return ('u32', v)

    def dump_table_fields(self, table_offset, label=""):
        """Dump all fields of a table, following uoffsets."""
        info = self.table(table_offset)
        if not info:
            print(f"  No table at {table_offset}")
            return
        t, vt, vs, ts = info
        print(f"\n  Table {label} at offset {table_offset}:")
        for i in range((vs-4)//2):
            fo = self.u16(vt+4+i*2)
            if not fo or fo >= ts: continue
            slot = t + fo
            target = self.follow_uoffset(slot)
            val_raw = self.u32(slot)
            if target:
                val_info = self.read_at_offset(target)
                if val_info[0] == 'table':
                    print(f"    field[{i}]: slot@{slot} -> @{target} = NESTED TABLE")
                    self.dump_table_fields(target, f"nested[{i}]")
                elif val_info[0] == 'string':
                    print(f"    field[{i}]: slot@{slot} -> @{target} = '{val_info[1]}'")
                elif val_info[0] == 'float':
                    print(f"    field[{i}]: slot@{slot} -> @{target} = float({val_info[1]:.4f})")
                else:
                    # Check if it's an RGBA color
                    if val_info[1] > 0xFFFFFF:
                        r = (val_info[1] >> 0) & 0xFF
                        gg = (val_info[1] >> 8) & 0xFF
                        b = (val_info[1] >> 16) & 0xFF
                        a = (val_info[1] >> 24) & 0xFF
                        if a in (255, 0) or a > 128:
                            print(f"    field[{i}]: slot@{slot} -> @{target} = u32({val_info[1]}) = 0x{val_info[1]:08X} = RGBA({r},{gg},{b},{a})")
                            continue
                    print(f"    field[{i}]: slot@{slot} -> @{target} = u32({val_info[1]})")
            else:
                # Scalar
                if val_raw > 0xFFFFFF and val_raw <= 0xFFFFFFFF:
                    r = (val_raw >> 0) & 0xFF
                    gg = (val_raw >> 8) & 0xFF
                    b = (val_raw >> 16) & 0xFF
                    a = (val_raw >> 24) & 0xFF
                    if a in (255, 0) or a > 128:
                        print(f"    field[{i}]: slot@{slot} = u32({val_raw}) = RGBA({r},{gg},{b},{a}) [scalar]")
                        continue
                print(f"    field[{i}]: slot@{slot} = scalar u32({val_raw})")

g = Graph(read_graph_bytes('/tmp/Interaction_Drag.origami'))

# Dump key tables
for name, off in [
    ("Rectangle bg", 495000),
    ("Interaction layer", 502284),
    ("Rectangle card", 504168),
    ("Artboard 1", 529636),
]:
    g.dump_table_fields(off, name)
    print()

# Also look at the Drag and DragSettings patches for their port values
print("\n\n=== Drag and DragSettings ===")
for name, off in [
    ("DragSettings 'Drag Settings'", 518300),
    ("Drag 'Drag'", 519788),
]:
    g.dump_table_fields(off, name)
    print()

EOF
