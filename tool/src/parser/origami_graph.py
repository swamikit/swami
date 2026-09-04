#!/usr/bin/env python3
"""
origami_graph — schema-less FlatBuffers reader for the .origami graph document.

`.origami` is a zip; the graph doc is `<name>.diamond/graph`, FlatBuffers, file_identifier
"ORGM", no shipped schema. The document embeds Origami's whole component *library*; the
*placed* graph is a small subset. Separating them is the core challenge (see CLAUDE.md).

Iteration 1: enumerates the PLACED graph. Placed nodes live in the file's tail (the
document node section), after the embedded library. Each node is a FlatBuffers table that
owns a type-id string ("builtin.*", "origami.*", "ios.*"); we find those strings, walk back
to the owning table, and decode it.

TODO (next iterations): decode ports + connections into edges; read layer values (colors,
sizes) validated against the oracle; find the placed-node section by root reference rather
than the tail-offset heuristic (generalization).
"""
import zipfile, struct, re, json, sys, pathlib

TYPE_RE = re.compile(rb'(builtin|origami|ios)\.[A-Za-z][A-Za-z0-9.]*')

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

    def placed_nodes(self, tail=360000):
        """Enumerate placed-graph nodes (in the document tail, past the library)."""
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
    implementation, so enumerate every node (tail=0); for a `.origami` document keep the
    tail heuristic that separates the placed graph from the embedded library.
    """
    g = Graph(read_graph_bytes(origami_path))
    if tail is None:
        tail = 0 if not zipfile.is_zipfile(origami_path) else 360000
    nodes = g.placed_nodes(tail=tail)
    kinds = {}
    for n in nodes:
        kinds[n["type"]] = kinds.get(n["type"], 0) + 1
    return {
        "file": str(origami_path), "size": g.N, "identifier": "ORGM",
        "placed_node_count": len(nodes),
        "kinds": dict(sorted(kinds.items())),
        "placed_nodes": nodes,
        "_todo": "edges (ports/connections), layer values vs oracle, generalize tail heuristic",
    }


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "examples/TouchOrigamiExample.origami"
    dest = sys.argv[2] if len(sys.argv) > 2 else "examples/TouchOrigamiExample.graph.json"
    out = parse(p)
    pathlib.Path(dest).write_text(json.dumps(out, indent=2))
    print(f"parsed {p} -> {dest}")
    print(f"  placed nodes: {out['placed_node_count']}")
    print("  kinds:", out["kinds"])
