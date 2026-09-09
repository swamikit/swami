#!/usr/bin/env python3
"""Boundary tests for the conservative FlatBuffers string inspector."""
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from inspect_colors import decode_string  # noqa: E402


class DecodeStringTests(unittest.TestCase):
    def test_decodes_complete_forward_string_object(self):
        graph = bytearray(40)
        table = 8
        table_size = 8
        slot = 12
        string_offset = 20
        struct.pack_into("<I", graph, slot, string_offset - slot)
        struct.pack_into("<I", graph, string_offset, 3)
        graph[string_offset + 4:string_offset + 8] = b"hex\0"

        self.assertEqual(decode_string(graph, table, table_size, slot), "hex")

    def test_rejects_reference_into_current_table(self):
        graph = bytearray(40)
        table = 8
        table_size = 12
        slot = 12
        struct.pack_into("<I", graph, slot, 4)
        struct.pack_into("<I", graph, 16, 3)
        graph[20:24] = b"hex\0"

        self.assertIsNone(decode_string(graph, table, table_size, slot))

    def test_rejects_payload_without_flatbuffers_terminator(self):
        graph = bytearray(b"x" * 32)
        table = 0
        table_size = 8
        slot = 4
        string_offset = 12
        struct.pack_into("<I", graph, slot, string_offset - slot)
        struct.pack_into("<I", graph, string_offset, 3)
        graph[16:19] = b"hex"

        self.assertIsNone(decode_string(graph, table, table_size, slot))


if __name__ == "__main__":
    unittest.main()
