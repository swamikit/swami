#!/usr/bin/env python3
"""
origami_graph — schema-less FlatBuffers reader for the .origami graph document.

`.origami` is a zip; the graph doc is `<name>.diamond/graph`, FlatBuffers, file_identifier
"ORGM", no shipped schema. The document embeds Origami's whole component *library*; the
*placed* graph is a small subset. Separating them is the core challenge (see CLAUDE.md).

Iteration 3 walks the current document directly: root field 4 points to the document
component; its field 9 is the placed child-node vector and field 10 is the connection
vector. Nodes expose input/output port vectors in fields 5/6. This produces an exact,
identifier-resolved structural graph instead of inferring membership from string offsets.

Raw catalog graphs do not use the document wrapper. They retain the conservative string
scan as a compatibility path until catalog component traversal is decoded.

TODO (next iterations): decode typed port-default values; represent nested component
implementations; read layer values validated against the oracle.
"""
import zipfile, struct, re, json, sys, pathlib

TYPE_RE = re.compile(rb'(builtin|origami|ios)\.[A-Za-z][A-Za-z0-9.]*')

MAX_VTABLE_SIZE = 200
DOCUMENT_COMPONENT_FIELD = 4
CHILD_NODES_FIELD = 9
CONNECTIONS_FIELD = 10
INPUT_PORTS_FIELD = 5
OUTPUT_PORTS_FIELD = 6

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
        if vs < 4 or vs > MAX_VTABLE_SIZE or vs % 2 or vt+vs > self.N: return None
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

    def field_uoffset_target(self, tinfo, field_idx):
        """Return the byte offset a uoffset field points at, or None if the field is absent."""
        t, vt, vs, ts = tinfo
        slot_in_vt = 4 + field_idx*2
        if slot_in_vt + 2 > vs: return None
        fo = self.u16(vt + slot_in_vt)
        if not fo or fo + 4 > ts: return None
        slot = t + fo
        if slot + 4 > self.N: return None
        return slot + self.u32(slot)

    def field_offset(self, tinfo, field_idx):
        """Return the absolute slot for a present field, or None."""
        t, vt, vs, ts = tinfo
        slot_in_vt = 4 + field_idx*2
        if slot_in_vt + 2 > vs: return None
        fo = self.u16(vt + slot_in_vt)
        if not fo or fo >= ts: return None
        return t + fo

    def field_u32(self, tinfo, field_idx):
        """Return a scalar u32 field, or None when the field is absent."""
        slot = self.field_offset(tinfo, field_idx)
        if slot is None or slot + 4 > tinfo[0] + tinfo[3]: return None
        return self.u32(slot)

    def field_string(self, tinfo, field_idx):
        target = self.field_uoffset_target(tinfo, field_idx)
        return self.astr(target) if target is not None else None

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

    def document_component(self):
        """Return the current document component table referenced by the root."""
        rinfo = self.table(self.root())
        if not rinfo: return None
        target = self.field_uoffset_target(rinfo, DOCUMENT_COMPONENT_FIELD)
        info = self.table(target) if target is not None else None
        if not info: return None
        # A document component always has a child-node vector. Requiring it prevents a
        # schema drift from silently turning an arbitrary field-4 table into the graph.
        if self.field_uoffset_target(info, CHILD_NODES_FIELD) is None: return None
        return info

    def placed_root_offset(self):
        """Compatibility name for the structurally located document component offset."""
        info = self.document_component()
        return info[0] if info else None

    def ports(self, node_info, field_idx, direction):
        vec = self.field_uoffset_target(node_info, field_idx)
        entries = self.vector_entries(vec) if vec is not None else None
        out = []
        for target in entries or []:
            info = self.table(target)
            if not info: continue
            port_id = self.field_u32(info, 0)
            if port_id is None: continue
            out.append({
                "id": port_id,
                "ordinal": self.field_u32(info, 1),
                "name": self.field_string(info, 2),
                "direction": direction,
                # The wrapper exists, but its typed union payload is not decoded yet.
                # Preserve the fact without inventing a literal value.
                "has_default": self.field_uoffset_target(info, 5) is not None,
            })
        return out

    def value_overrides(self, port_ids):
        """Decode instance-level port values keyed by the port id in field 17.

        Origami stores only overridden values here; absence means the patch's catalog
        default applies. The value table is a sparse union. Decode the scalar/compound
        shapes needed by the public interaction corpus and preserve unknown shapes as
        raw field metadata instead of guessing.
        """
        values = {}
        for target in range(self.N - 4):
            info = self.table(target)
            if not info or info[2] < 40: continue
            port_id = self.field_u32(info, 17)
            if port_id not in port_ids: continue
            active = [idx for idx in range((info[2] - 4)//2)
                      if self.field_offset(info, idx) is not None]
            kind_slot = self.field_offset(info, 0)
            type_tag = self.d[kind_slot] if kind_slot is not None else None
            value = {"type_tag": type_tag}
            if self.field_offset(info, 6) is not None:
                value.update(kind="bool", value=bool(self.d[self.field_offset(info, 6)]))
            elif self.field_offset(info, 1) is not None:
                value.update(kind="number", value=struct.unpack_from(
                    '<d', self.d, self.field_offset(info, 1))[0])
            elif self.field_offset(info, 2) is not None:
                slot = self.field_offset(info, 2)
                value.update(kind="point", value=list(struct.unpack_from('<dd', self.d, slot)))
            elif self.field_offset(info, 4) is not None:
                slot = self.field_offset(info, 4)
                value.update(kind="vector4", value=list(struct.unpack_from('<dddd', self.d, slot)))
            elif self.field_offset(info, 7) is not None:
                value.update(kind="integer", value=self.u32(self.field_offset(info, 7)))
            else:
                value.update(kind="opaque", active_fields=active)
            # A port can carry its catalog default and then a document override.
            # FlatBuffers serialization places the override later; keep the last table.
            values[port_id] = value
        return values

    def document_graph(self):
        """Decode the placed document into nodes, ports, and identifier-resolved edges."""
        component = self.document_component()
        if not component: return None
        node_vec = self.field_uoffset_target(component, CHILD_NODES_FIELD)
        node_entries = self.vector_entries(node_vec) if node_vec is not None else None
        nodes = []
        ports_by_id = {}
        nodes_by_id = {}
        for target in node_entries or []:
            info = self.table(target)
            if not info: continue
            node_id = self.field_u32(info, 0)
            node_type = self.field_string(info, 2)
            if node_id is None or not node_type or not TYPE_RE.fullmatch(node_type.encode()):
                continue
            inputs = self.ports(info, INPUT_PORTS_FIELD, "input")
            outputs = self.ports(info, OUTPUT_PORTS_FIELD, "output")
            node = {
                "id": node_id,
                "table": target,
                "type": node_type,
                "name": self.field_string(info, 4),
                "inputs": inputs,
                "outputs": outputs,
            }
            nodes.append(node)
            nodes_by_id[node_id] = node
            for port in inputs + outputs:
                ports_by_id[port["id"]] = (node, port)

        overrides = self.value_overrides(set(ports_by_id))
        for _node, port in ports_by_id.values():
            if port["id"] in overrides:
                port["value"] = overrides[port["id"]]

        connection_vec = self.field_uoffset_target(component, CONNECTIONS_FIELD)
        connection_entries = self.vector_entries(connection_vec) if connection_vec is not None else None
        edges = []
        for target in connection_entries or []:
            info = self.table(target)
            if not info: continue
            ids = [self.field_u32(info, i) for i in range(4)]
            if any(value is None for value in ids): continue
            src_node_id, src_port_id, dst_node_id, dst_port_id = ids
            src_node = nodes_by_id.get(src_node_id)
            dst_node = nodes_by_id.get(dst_node_id)
            src_port = ports_by_id.get(src_port_id)
            dst_port = ports_by_id.get(dst_port_id)
            edges.append({
                "table": target,
                "source": {
                    "node_id": src_node_id,
                    "node": src_node["name"] if src_node else None,
                    "port_id": src_port_id,
                    "port": src_port[1]["name"] if src_port else None,
                },
                "destination": {
                    "node_id": dst_node_id,
                    "node": dst_node["name"] if dst_node else None,
                    "port_id": dst_port_id,
                    "port": dst_port[1]["name"] if dst_port else None,
                },
                "resolved": bool(src_node and dst_node and src_port and dst_port),
            })
        return {
            "id": self.field_u32(component, 0),
            "name": self.field_string(component, 4),
            "table": component[0],
            "nodes": nodes,
            "edges": edges,
        }

    def placed_nodes(self, tail=None):
        """Compatibility string scan for raw catalog graphs or forced boundaries.

        `tail` is a byte-offset boundary: type-string occurrences at or below it are
        ignored. For zipped documents, prefer `document_graph()`, which walks declared
        vectors and cannot confuse node metadata with nodes. `tail=None` falls back to
        zero so a raw catalog graph is scanned in full.
        """
        if tail is None:
            tail = 0
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

    `tail=None` auto-selects: for a raw catalog graph the whole file is scanned; for a
    `.origami` document the declared document, node, port, and connection vectors are
    walked structurally. A numeric `tail` forces the legacy string-scan compatibility path.
    """
    g = Graph(read_graph_bytes(origami_path))
    is_document = zipfile.is_zipfile(origami_path)
    graph = g.document_graph() if is_document and tail is None else None
    if graph:
        nodes = graph["nodes"]
        edges = graph["edges"]
        placed_root = graph["table"]
    else:
        if tail is None: tail = 0
        nodes = g.placed_nodes(tail=tail)
        edges = []
        placed_root = tail or None
    kinds = {}
    for n in nodes:
        kinds[n["type"]] = kinds.get(n["type"], 0) + 1
    return {
        "schema_version": 1,
        "file": str(origami_path), "size": g.N, "identifier": "ORGM",
        "document": ({key: graph[key] for key in ("id", "name", "table")} if graph else None),
        "placed_root_offset": placed_root,
        "placed_node_count": len(nodes),
        "edge_count": len(edges),
        "unresolved_edge_count": sum(not edge["resolved"] for edge in edges),
        "kinds": dict(sorted(kinds.items())),
        "placed_nodes": nodes,
        "edges": edges,
        "_todo": "typed port-default values, nested components, layer values vs oracle",
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
