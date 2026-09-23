#!/usr/bin/env python3
"""
origami_graph — schema-less FlatBuffers reader for the .origami graph document.

`.origami` is a zip; the graph doc is `<name>.diamond/graph`, FlatBuffers, file_identifier
"ORGM", no shipped schema. The document embeds Origami's whole component *library*; the
*placed* graph is a small subset. Separating them is the core challenge (see CLAUDE.md).

Iteration 2 (structural): the placed graph is found by STRUCTURE, not a byte offset.
  1. Enumerate the library table set by walking root field 14 (the embedded library).
  2. Scan for "node vectors" — FlatBuffers vectors whose elements are tables that own a
     patch-type string ("builtin.*"/"origami.*"/"ios.*"). Every component (library or
     placed) has one.
  3. The PLACED node vector is the one whose elements are NOT in the library set.
  4. Read its nodes+ports, then find the sibling CONNECTION vector by content
     (elements shaped [srcNodeId, srcPortId, dstNodeId, dstPortId]) and decode edges.

This removes the `tail=360000` heuristic (ADR: it was tuned to the Touch example and
over-included embedded composite patches on larger files). Validated on the Touch example
(51 placed nodes / 40 edges, matching the CLAUDE.md oracle mechanism). NOT YET validated on
a file that embeds a composite patch (e.g. Interaction_Drag) — but library-exclusion is
correct by construction there: a placed `origami.Drag` is ONE node; Drag's internals live
in the library and are excluded. See NEEDS-VERIFY.

Strictness note: table validation caps vtable size (real Origami tables are small). Loose
validation makes random bytes read as giant fake tables and the walk explodes — the single
most important correctness lever for a schema-less walk.
"""
import zipfile, struct, re, json, sys, pathlib

TYPE_RE = re.compile(r'^(builtin|origami|ios)\.[A-Za-z][A-Za-z0-9.]*$')
LIBRARY_ROOT_FIELD = 14          # root VEC field holding the embedded component library
MAX_VTABLE = 240                 # <=118 fields; real tables are small
MAX_TABLE = 4000


def read_graph_bytes(path):
    """Read graph FlatBuffers from a `.origami` zip or a raw catalog `graph` file."""
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
        if t < 0 or t + 4 > self.N: return None
        ln = self.u32(t)
        if 0 < ln < 400 and t + 4 + ln <= self.N:
            s = self.d[t+4:t+4+ln]
            if all(32 <= b < 127 for b in s):
                try: return s.decode()
                except UnicodeDecodeError: return None
        return None

    def table(self, t):
        """STRICT table validator: returns (t, vtable, vsize, tsize) or None."""
        if t < 4 or t + 4 > self.N: return None
        vt = t - self.i32(t)
        if vt < 0 or vt + 4 > self.N: return None
        vs = self.u16(vt)
        if vs < 4 or vs % 2 or vs > MAX_VTABLE or vt + vs > self.N: return None
        ts = self.u16(vt + 2)
        if ts < 4 or ts > MAX_TABLE or t + ts > self.N: return None
        return (t, vt, vs, ts)

    def slots(self, info):
        t, vt, vs, ts = info; out = {}
        for i in range((vs - 4) // 2):
            fo = self.u16(vt + 4 + i * 2)
            if fo and 4 <= fo and fo + 4 <= ts: out[i] = t + fo
        return out

    def scalar(self, info, i):
        s = self.slots(info); return self.u32(s[i]) if i in s else None

    def field(self, slot):
        """Classify a table field slot: ('str',s) | ('tab',t) | ('vec',count,base) | ('scalar',v)."""
        v = self.u32(slot); tgt = slot + v
        s = self.astr(tgt)
        if s is not None: return ("str", s)
        if v and self.table(tgt): return ("tab", tgt)
        if v and tgt + 4 <= self.N:
            c = self.u32(tgt); b = tgt + 4
            if 0 < c <= 20000 and b + c * 4 <= self.N and self.table(b + self.u32(b)):
                return ("vec", c, b)
        return ("scalar", v)

    def vec_elems(self, base, count):
        out = []
        for k in range(count):
            p = base + k * 4
            if p + 4 > self.N: break
            out.append(p + self.u32(p))
        return out

    # --- structural placed-graph detection ---------------------------------

    def _root_vec(self, field_index):
        info = self.table(self.root())
        s = self.slots(info)
        if field_index not in s: return None
        f = self.field(s[field_index])
        return (f[1], f[2]) if f[0] == "vec" else None

    def library_tables(self, budget=400000):
        """Offset-reachable table set under the embedded library (root field 14)."""
        lib = self._root_vec(LIBRARY_ROOT_FIELD)
        if not lib: return set()
        count, base = lib
        seen, stack, steps = set(), list(self.vec_elems(base, count)), 0
        while stack and steps < budget:
            steps += 1
            t = stack.pop()
            if t in seen: continue
            info = self.table(t)
            if not info: continue
            seen.add(t)
            for slot in self.slots(info).values():
                f = self.field(slot)
                if f[0] == "tab": stack.append(f[1])
                elif f[0] == "vec":
                    for e in self.vec_elems(f[2], f[1])[:4000]: stack.append(e)
        return seen

    def _owns_type(self, t):
        info = self.table(t)
        if not info: return None
        for slot in self.slots(info).values():
            f = self.field(slot)
            if f[0] == "str" and TYPE_RE.match(f[1]): return f[1]
        return None

    def node_vectors(self, min_count=6):
        """Every FlatBuffers vector whose elements are ~all patch-type tables."""
        out = []
        p = 0
        while p + 4 < self.N:
            c = self.u32(p); b = p + 4
            if min_count <= c <= 20000 and b + c * 4 <= self.N:
                sample = min(c, 12); typed = tabs = 0
                for k in range(sample):
                    e = (b + k * 4) + self.u32(b + k * 4)
                    if self.table(e):
                        tabs += 1
                        if self._owns_type(e): typed += 1
                if tabs == sample and typed >= sample - 1:
                    out.append((p, c, b))
                    p = b + c * 4; continue
            p += 4
        return out

    def placed_node_vector(self):
        """Select the placed-graph node vector.

        The placed document is the graph that owns the artboard (a `*.Screen` node);
        library patch-definitions never contain one. Prefer that; then a node-vector
        outside the embedded library; then the largest. (Offset-reachability from the
        library root can't fully bound the library because components reference their
        nodes by id, so the artboard test is the load-bearing discriminator.)
        """
        cands = self.node_vectors()
        if not cands: return None
        lib = self.library_tables()
        scored = []
        for (p, c, b) in cands:
            els = self.vec_elems(b, c)
            has_screen = any((self._owns_type(e) or "").endswith(".Screen") for e in els)
            non_library = (sum(1 for e in els if e in lib) / max(1, c)) < 0.30
            scored.append((has_screen, non_library, c, b))
        scored.sort(key=lambda s: (s[0], s[1], s[2]), reverse=True)
        best = scored[0]
        return (best[3], best[2])

    def decode_nodes(self, base, count):
        nodes, ports = {}, {}
        for e in self.vec_elems(base, count):
            info = self.table(e)
            if not info: continue
            typ = None; strs = []
            for slot in self.slots(info).values():
                f = self.field(slot)
                if f[0] == "str":
                    strs.append(f[1])
                    if TYPE_RE.match(f[1]): typ = f[1]
            if not typ: continue
            nid = self.scalar(info, 0)
            name = next((s for s in strs if s != typ
                         and not s.startswith(("builtin", "origami", "ios", "com."))), None)
            for slot in self.slots(info).values():        # ports = child vectors of tables w/ an id
                f = self.field(slot)
                if f[0] == "vec":
                    for pe in self.vec_elems(f[2], f[1]):
                        pinfo = self.table(pe)
                        if not pinfo: continue
                        pid = self.scalar(pinfo, 0); pname = None
                        for psl in self.slots(pinfo).values():
                            pf = self.field(psl)
                            if pf[0] == "str" and not TYPE_RE.match(pf[1]): pname = pf[1]; break
                        if pid is not None: ports[pid] = (name or typ, pname)
            if nid is not None:
                nodes[nid] = {"id": nid, "type": typ, "name": name}
        return nodes, ports

    def connection_vector(self, nodes, min_count=4):
        """The vector whose elements are [srcNode, srcPort, dstNode, dstPort] tables."""
        best = None
        p = 0
        while p + 4 < self.N:
            c = self.u32(p); b = p + 4
            if min_count <= c <= 4000 and b + c * 4 <= self.N:
                valid = 0
                for e in self.vec_elems(b, c):
                    info = self.table(e)
                    if not info: continue
                    v0, v2 = self.scalar(info, 0), self.scalar(info, 2)
                    if v0 in nodes and v2 in nodes: valid += 1
                purity = valid / c
                if purity >= 0.8 and valid >= min_count and (best is None or valid > best[0]):
                    best = (valid, p, c, b)
            p += 4
        return None if best is None else (best[3], best[2])

    def decode_edges(self, base, count, nodes, ports):
        edges = []
        for e in self.vec_elems(base, count):
            info = self.table(e)
            if not info: continue
            sN, sP, dN, dP = (self.scalar(info, 0), self.scalar(info, 1),
                              self.scalar(info, 2), self.scalar(info, 3))
            if sN in nodes and dN in nodes:
                def lab(n, p):
                    nd = nodes[n]; pn = ports.get(p, (None, None))[1]
                    base_ = nd["name"] or nd["type"]
                    return base_ + (f".{pn}" if pn else "")
                edges.append({"src_node": sN, "src_port": sP, "dst_node": dN, "dst_port": dP,
                              "src": lab(sN, sP), "dst": lab(dN, dP)})
        return edges


def parse(origami_path):
    g = Graph(read_graph_bytes(origami_path))
    nv = g.placed_node_vector()
    if nv is None:
        return {"file": str(origami_path), "size": g.N, "identifier": "ORGM",
                "error": "no placed node vector found"}
    base, count = nv
    nodes, ports = g.decode_nodes(base, count)
    cv = g.connection_vector(nodes)
    edges = g.decode_edges(cv[0], cv[1], nodes, ports) if cv else []
    kinds = {}
    for n in nodes.values():
        kinds[n["type"]] = kinds.get(n["type"], 0) + 1
    return {
        "file": str(origami_path), "size": g.N, "identifier": "ORGM",
        "method": "structural (library-exclusion; no byte offset)",
        "placed_node_count": len(nodes),
        "edge_count": len(edges),
        "kinds": dict(sorted(kinds.items())),
        "nodes": sorted(nodes.values(), key=lambda n: (n["type"], n["name"] or "")),
        "edges": edges,
        "_todo": "layer values vs oracle; input-port default-value union decoding",
    }


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "examples/TouchOrigamiExample.origami"
    dest = sys.argv[2] if len(sys.argv) > 2 else "examples/TouchOrigamiExample.graph.json"
    out = parse(p)
    pathlib.Path(dest).write_text(json.dumps(out, indent=2))
    print(f"parsed {p} -> {dest}")
    print(f"  placed nodes: {out.get('placed_node_count')}  edges: {out.get('edge_count')}")
    print("  kinds:", out.get("kinds"))
