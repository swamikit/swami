#!/usr/bin/env python3
"""Lightweight inspector for color tokens in an Origami placed graph.

The inspector recognizes only FlatBuffers strings and tables with both a
``name`` and an eight-character ``hex`` field. It intentionally does not infer
colors from arbitrary 32-bit values.
"""
import struct
import sys
import zipfile


def read_graph_bytes(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            name = next(name for name in archive.namelist() if name.endswith("graph"))
            return archive.read(name)
    with open(path, "rb") as graph_file:
        return graph_file.read()


def decode_string(graph, table, table_size, slot):
    """Decode a forward FlatBuffers string reference without crossing objects."""
    if slot + 4 > len(graph):
        return None

    relative_offset = struct.unpack_from("<I", graph, slot)[0]
    string_offset = slot + relative_offset

    # FlatBuffers uoffsets point forward to a four-byte-aligned object. A field
    # in this table cannot point into the table object itself.
    if (
        relative_offset == 0
        or string_offset < table + table_size
        or string_offset % 4 != 0
        or string_offset + 4 > len(graph)
    ):
        return None

    length = struct.unpack_from("<I", graph, string_offset)[0]
    if not 1 < length < 200:
        return None

    payload_start = string_offset + 4
    payload_end = payload_start + length
    # FlatBuffers strings include a trailing NUL that is not part of length.
    if payload_end >= len(graph) or graph[payload_end] != 0:
        return None

    payload = graph[payload_start:payload_end]
    if not all(32 <= byte < 127 for byte in payload):
        return None
    return payload.decode("ascii")


def decode_table(graph, table):
    if table + 16 > len(graph):
        return None
    try:
        vtable = table - struct.unpack_from("<i", graph, table)[0]
        if vtable < 0 or vtable + 8 > len(graph):
            return None
        vtable_size = struct.unpack_from("<H", graph, vtable)[0]
        table_size = struct.unpack_from("<H", graph, vtable + 2)[0]
        if vtable_size < 4 or vtable_size % 2 or vtable + vtable_size > len(graph):
            return None
        if table_size < 8 or table_size > 2000 or table + table_size > len(graph):
            return None
    except struct.error:
        return None

    record = {"table": table}
    for index in range((vtable_size - 4) // 2):
        field_offset = struct.unpack_from("<H", graph, vtable + 4 + index * 2)[0]
        if not field_offset or field_offset + 4 > table_size:
            continue
        value = decode_string(graph, table, table_size, table + field_offset)
        if value is not None:
            record[str(index)] = value
    return record


def find_color_tables(graph, placed_root):
    colors = []
    for table in range(placed_root, len(graph) - 32):
        record = decode_table(graph, table)
        if record is None:
            continue
        strings = [value for value in record.values() if isinstance(value, str)]
        has_hex = any(
            len(value) == 8
            and all(character in "0123456789ABCDEFabcdef" for character in value)
            for value in strings
        )
        has_name = any(
            not (
                len(value) == 8
                and all(character in "0123456789ABCDEFabcdef" for character in value)
            )
            for value in strings
        )
        if has_hex and has_name:
            colors.append(record)
    return colors


def find_radius_tables(graph, placed_root):
    radii = []
    for table in range(placed_root, len(graph) - 32):
        record = decode_table(graph, table)
        if record is not None and any(
            value in ("radius", "cornerRadius") for value in record.values()
        ):
            radii.append(record)
    return radii


def main():
    graph = read_graph_bytes(sys.argv[1])
    graph_size = len(graph)
    assert graph[4:8] == b"ORGM", "not an ORGM FlatBuffers document"
    root = struct.unpack_from("<I", graph, 0)[0]
    root_vtable = root - struct.unpack_from("<i", graph, root)[0]
    root_vtable_size = struct.unpack_from("<H", graph, root_vtable)[0]
    if 14 * 2 + 4 < root_vtable_size:
        field_offset = struct.unpack_from("<H", graph, root_vtable + 4 + 14 * 2)[0]
        slot = root + field_offset
        vector = slot + struct.unpack_from("<I", graph, slot)[0]
        count = struct.unpack_from("<I", graph, vector)[0]
        offsets = [
            vector + 4 + index * 4
            + struct.unpack_from("<I", graph, vector + 4 + index * 4)[0]
            for index in range(count)
        ]
        offsets.sort(reverse=True)
        placed_root = offsets[0]
        print(f"placed_root = {placed_root}, file size = {graph_size}")
    else:
        placed_root = 0
        print(f"(no field-14 vector; scanning whole file, size = {graph_size})")

    colors = find_color_tables(graph, placed_root)
    print(f"\nColor-like tables in placed region: {len(colors)}")
    for color in colors[:30]:
        print(f"  table={color['table']} {color}")

    print("\nRadius-like tables in placed region:")
    radii = find_radius_tables(graph, placed_root)
    for radius in radii[:30]:
        print(f"  table={radius['table']} {radius}")


if __name__ == "__main__":
    main()
