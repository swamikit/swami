#!/usr/bin/env python3
"""
origami_graph — schema-less FlatBuffers reader for the .origami graph document.

`.origami` is a zip; the graph doc is `<name>.diamond/graph`, FlatBuffers, file_identifier
"ORGM", no shipped schema. The document embeds Origami's whole component *library*; the
*placed* graph is a small subset. Separating them is the core challenge (see CLAUDE.md).

Iteration 2: enumerates the PLACED graph by locating the current-document node via the
FlatBuffers root reference, not a byte offset. The document root table's field 14 is a
vector of component definitions — entries[1:] are the embedded library, and entries[0]
(the highest-offset entry, "latest serialized" in FlatBuffers order) is the current
document. Its subtree lives at file offsets > entries[0] and contains the placed graph.

This replaces the earlier hardcoded `tail=360000` heuristic, which worked for the ~465 KB
Touch document but captured the embedded Drag/EdgeSwipe/etc. component internals as false
"placed" nodes on any larger file (Interaction_Drag.origami is 534 KB — the tail cut
falls INSIDE the embedded Drag definition).

The reader also decodes the inline value-union payloads needed by Interaction Drag:
number defaults (including Drag Settings' Momentum Friction) and RGBA color payloads.
The color payload is four little-endian Float64 channels in red/green/blue/alpha order;
the corpus' named Purple token (`#DD70DF`) is the channel-order oracle.

Remaining general parser work is connection/edge decoding and walking the entry[0]
subtree structurally instead of using its byte offset as a boundary.
"""
import zipfile, struct, re, json, sys, pathlib

TYPE_RE = re.compile(rb'(builtin|origami|ios)\.[A-Za-z][A-Za-z0-9.]*')

# Root vtable field carrying the document's component/library vector. Entry [0] of that
# vector is the current document; entries [1..] are the embedded component library.
# See CLAUDE.md "Root field 14 (EdgeSwipe, Velocity, StickyBoundaries, …) is the LIBRARY".
ROOT_COMPONENTS_FIELD = 14

def read_graph_bytes(path):
    """Read graph FlatBuffers from either a `.origami` zip or a raw catalog `graph` file.

    `.origami` documents are zips (graph at `<name>.diamond/graph`). The installed catalog
    (ADR-0011) stores each patch's `graph` **uncompressed** on disk, so accept raw ORGM bytes
    too — this is how the skill reads `Resources/Patches/.../<id>.diamond/graph` live.
    """
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith("graph"))
            return z.read(name)
    data = pathlib.Path(path).read_bytes()
    if data[4:8] != b"ORGM":
        raise ValueError(f"{path}: not a .origami zip nor a raw ORGM graph")
    return data

class Graph:
    def __init__(self, data):
        self.d = data; self.N = len(data)
        assert data[4:8] == b"ORGM", "not an ORGM FlatBuffers document"
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
        """Find a table one of whose fields points to the string object at `sobj`."""
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
                slot = t+fo; v = self.u32(slot); s = self.astr(slot+v) if 0 < v < self.N else None
                rec[str(i)] = s if s is not None else v
        return rec

    def field_offset(self, tinfo, field_idx):
        """Return a field's offset within its table, or None when it is absent."""
        _, vt, vs, ts = tinfo
        slot_in_vt = 4 + field_idx*2
        if slot_in_vt + 2 > vs: return None
        fo = self.u16(vt + slot_in_vt)
        return fo if fo and fo < ts else None

    def field_uoffset_target(self, tinfo, field_idx):
        """Return the byte offset a uoffset field points at, or None if the field is absent."""
        t, _, _, ts = tinfo
        fo = self.field_offset(tinfo, field_idx)
        if fo is None or fo + 4 > ts: return None
        slot = t + fo
        if slot + 4 > self.N: return None
        target = slot + self.u32(slot)
        return target if 0 <= target < self.N else None

    def field_u32(self, tinfo, field_idx):
        """Read a present 32-bit scalar field without treating it as a uoffset."""
        t, _, _, ts = tinfo
        fo = self.field_offset(tinfo, field_idx)
        if fo is None or fo + 4 > ts or t + fo + 4 > self.N: return None
        return self.u32(t + fo)

    def field_u8(self, tinfo, field_idx):
        """Read a present byte discriminator without assuming its table offset."""
        t, _, _, ts = tinfo
        fo = self.field_offset(tinfo, field_idx)
        if fo is None or fo + 1 > ts or t + fo + 1 > self.N: return None
        return self.d[t + fo]

    def field_inline_float64s(self, tinfo, field_idx, count):
        """Read an inline Float64 struct from a field's structural span.

        FlatBuffers may move a field when optional neighbors differ between schema
        versions. The vtable supplies its actual offset; the next populated field (or
        table end) supplies its available span. This deliberately does not pin either
        value to offsets observed in one corpus document.
        """
        t, _, vs, ts = tinfo
        start = self.field_offset(tinfo, field_idx)
        if start is None: return None
        following = [
            offset for idx in range((vs - 4) // 2)
            if idx != field_idx
            and (offset := self.field_offset(tinfo, idx)) is not None
            and offset > start
        ]
        end = min(following, default=ts)
        width = count * 8
        if end - start < width or t + start + width > self.N: return None
        return struct.unpack_from('<' + ('d' * count), self.d, t + start)

    def decode_value(self, value_off, expected_tag=None):
        """Decode a typed Origami value-union payload.

        `expected_tag` comes from the union owner (a port record or value wrapper).
        Origami repeats that tag in payload field 17. Requiring the two tags to agree
        is the structural type boundary: a table is never classified from a convenient
        vtable/byte pattern alone.

        Once authenticated, a Number is the payload shape whose complete field set is
        exactly {1, 17}: no field-0 subtype discriminator, one inline Float64 in
        field 1, and the repeated union tag in field 17. A Color's complete field set
        is exactly {0, 4, 17}: subtype byte 3 in field 0, an inline four-Float64 RGBA
        struct in field 4, and the tag in field 17. Any additional or missing field
        fails the per-variant shape proof and the table is not decoded — a table is
        never classified from a convenient vtable/byte pattern alone. Vtable offsets
        and field spans are read structurally; they are not corpus constants.
        """
        info = self.table(value_off)
        if not info or expected_tag is None: return None
        payload_tag = self.field_u32(info, 17)
        if payload_tag is None or payload_tag != expected_tag: return None

        present = self.present_fields(info)
        subtype = self.field_u8(info, 0)

        # Number variant: full field set {1, 17}, discriminator absent, and the
        # Float64 field's structural span must cover a complete Float64.
        number = self.field_inline_float64s(info, 1, 1)
        if present == {1, 17} and number is not None:
            value = number[0]
            if value == value and abs(value) != float('inf'):
                return {"type": "number", "value": value}

        # Color variant: full field set {0, 4, 17}, discriminator byte present and
        # equal to 3, and the RGBA field's span must cover four complete Float64s.
        channels = self.field_inline_float64s(info, 4, 4)
        if present == {0, 4, 17} and subtype == 3 and channels is not None:
            if all(c == c and 0.0 <= c <= 1.0 for c in channels):
                return {"type": "color", "space": "sRGB", "channels": "RGBA",
                        "red": channels[0], "green": channels[1],
                        "blue": channels[2], "alpha": channels[3]}
        return None

    def present_fields(self, info):
        """Indices of the fields a table's vtable actually populates."""
        _, vt, vs, _ = info
        return {i for i in range((vs - 4) // 2)
                if self.field_offset(info, i) is not None}

    def decode_port_value(self, port_info):
        """Decode field 4 using the value-union tag carried by port field 0."""
        value_off = self.field_uoffset_target(port_info, 4)
        tag = self.field_u32(port_info, 0)
        return self.decode_value(value_off, tag) if value_off is not None else None

    def node_port_defaults(self, node_table):
        """Decode named port defaults from a placed node's field-5 port vector."""
        node = self.table(node_table)
        if not node: return {}
        vec = self.field_uoffset_target(node, 5)
        entries = self.vector_entries(vec) if vec is not None else None
        if entries is None: return {}
        defaults = {}
        for port_off in entries:
            port = self.table(port_off)
            if not port: continue
            name_off = self.field_uoffset_target(port, 2)
            name = self.astr(name_off) if name_off is not None else None
            value = self.decode_port_value(port)
            if name and value is not None:
                defaults[name] = value
        return defaults

    def named_port_defaults(self, start=0, end=None):
        """Decode scalar defaults from serialized port records in a byte range."""
        defaults = {}
        for off in range(max(0, start), min(end or self.N, self.N)):
            port = self.table(off)
            # Port records in this format have a 16-byte vtable and 40-byte table.
            if not port or port[2:4] != (16, 40): continue
            name_off = self.field_uoffset_target(port, 2)
            name = self.astr(name_off) if name_off is not None else None
            value = self.decode_port_value(port)
            if name and value is not None:
                defaults[name] = value
        return defaults

    def typed_value_payloads(self, start=0):
        """Yield payload offsets and values reached through typed value wrappers.

        Wrapper tables carry the tag in field 0 and the payload uoffset in field 1.
        Restricting discovery to that relationship avoids probing every byte offset as
        though it might be a value table.
        """
        for off in range(max(0, start), self.N):
            wrapper = self.table(off)
            if not wrapper or wrapper[2:4] != (8, 16): continue
            tag = self.field_u32(wrapper, 0)
            payload = self.field_uoffset_target(wrapper, 1)
            if tag is None or payload is None: continue
            value = self.decode_value(payload, tag)
            if value is not None:
                yield payload, value

    def color_values(self, start=0):
        """Return unique typed RGBA payloads at or above `start`, in serialized order."""
        seen, colors = set(), []
        for _, value in self.typed_value_payloads(start):
            if value["type"] != "color": continue
            key = tuple(value[k] for k in ("red", "green", "blue", "alpha"))
            if key not in seen:
                seen.add(key); colors.append(value)
        return colors

    def vector_entries(self, vec_off):
        """Given a vector's byte offset (count-prefix start), return absolute offsets of
        each entry as a table (i.e. each 4-byte slot's position PLUS the uoffset stored
        there). Returns None if the vector looks malformed.
        """
        if vec_off < 0 or vec_off + 4 > self.N: return None
        cnt = self.u32(vec_off)
        if cnt > 200000 or vec_off + 4 + cnt*4 > self.N: return None
        out = []
        for i in range(cnt):
            ep = vec_off + 4 + i*4
            out.append(ep + self.u32(ep))
        return out

    def placed_root_offset(self):
        """Locate the current-document node = entries[0] of the root's field-14 vector.

        FlatBuffers writes objects in reverse (nested first, root last), so entries in
        the components vector appear in *descending* byte order. Entry index 0 is the
        highest-offset entry — the "current document" whose subtree carries the placed
        graph. Everything below it in the vector is the embedded library.

        Returns the byte offset of that entry table, or None if we can't safely locate it
        (schema mismatch, empty vector, etc.). Callers should fall back to a heuristic.
        """
        rinfo = self.table(self.root())
        if not rinfo: return None
        vec_off = self.field_uoffset_target(rinfo, ROOT_COMPONENTS_FIELD)
        if vec_off is None: return None
        entries = self.vector_entries(vec_off)
        if not entries: return None
        # entries[0] = the last-serialized component = the current document
        return entries[0]

    def placed_nodes(self, tail=None):
        """Enumerate placed-graph nodes.

        `tail` is a byte-offset boundary: type-string occurrences at or below it are
        ignored (they belong to the embedded library). `tail=None` (default) locates the
        boundary structurally via `placed_root_offset()`, falling back to 0 if the root
        walk fails (which enumerates everything — useful for raw catalog graphs where the
        whole buffer IS the placed graph). Pass a positive int to force a byte offset.
        """
        if tail is None:
            tail = self.placed_root_offset()
            if tail is None: tail = 0
        seen, nodes = set(), []
        for m in TYPE_RE.finditer(self.d):
            off = m.start()
            if off < tail: continue
            typ = m.group().decode(); sobj = off-4
            if self.astr(sobj) != typ: continue
            info = self.owner_table_of(sobj)
            if info and info[0] not in seen:
                seen.add(info[0])
                rec = self.decode(info)
                name = next((v for v in rec.values()
                             if isinstance(v, str) and v != typ
                             and not v.startswith(("builtin", "origami", "ios", "com."))), None)
                nodes.append({"table": info[0], "type": typ, "name": name})
        return sorted(nodes, key=lambda n: n["table"])


def parse(origami_path, tail=None):
    """Parse a document (`.origami`) or a catalog patch graph.

    `tail=None` auto-selects: for a raw catalog graph the whole file is the patch's internal
    implementation, so enumerate every node (tail=0); for a `.origami` document walk the
    root reference to find the placed graph structurally (see `Graph.placed_root_offset`).
    """
    g = Graph(read_graph_bytes(origami_path))
    if tail is None:
        tail = 0 if not zipfile.is_zipfile(origami_path) else g.placed_root_offset()
        if tail is None: tail = 0  # last-resort: enumerate the whole buffer
    nodes = g.placed_nodes(tail=tail)
    kinds = {}
    for n in nodes:
        kinds[n["type"]] = kinds.get(n["type"], 0) + 1
        defaults = g.node_port_defaults(n["table"])
        if defaults: n["port_defaults"] = defaults
    return {
        "file": str(origami_path), "size": g.N, "identifier": "ORGM",
        "placed_root_offset": (tail if tail else None),
        "placed_node_count": len(nodes),
        "kinds": dict(sorted(kinds.items())),
        "placed_nodes": nodes,
        "embedded_port_defaults": g.named_port_defaults(start=0, end=tail),
        "decoded_colors": g.color_values(start=tail),
        "remaining_parser_scope": "connections/edges and a fully structural entry[0] subtree walk",
    }


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "examples/TouchOrigamiExample.origami"
    dest = sys.argv[2] if len(sys.argv) > 2 else "examples/TouchOrigamiExample.graph.json"
    out = parse(p)
    pathlib.Path(dest).write_text(json.dumps(out, indent=2))
    print(f"parsed {p} -> {dest}")
    print(f"  placed_root_offset: {out['placed_root_offset']}")
    print(f"  placed nodes: {out['placed_node_count']}")
    print("  kinds:", out["kinds"])
