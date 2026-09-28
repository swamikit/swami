#!/usr/bin/env python3
"""Fast unit tests for the M2-color layer-color decode (origami_graph).

These avoid a full `parse()` (the placed-node walk is slow); they exercise the
color decode directly against a known byte offset and the palette heuristic
against a synthetic inventory.
"""
import pathlib
import unittest

import origami_graph as og

CACHE = pathlib.Path(__file__).parent / ".cache"
DRAG = CACHE / "Interaction_Drag.origami"

# Byte-proven ground truth: Origami Core "Purple" #DD70DF is the Interaction_Drag
# artboard fill; its color table starts at offset 533672 (struct at +8).
DRAG_MAGENTA_TABLE = 533672


class ColorDecodeTests(unittest.TestCase):
    def setUp(self):
        self.g = og.Graph(og.read_graph_bytes(str(DRAG)))

    def test_decodes_known_magenta(self):
        rgba = self.g.color_rgba(DRAG_MAGENTA_TABLE)
        self.assertIsNotNone(rgba, "expected a color table at the known magenta offset")
        r, gr, b, a = rgba
        # #DD70DF = (221, 112, 223) / 255, opaque.
        self.assertAlmostEqual(r, 221 / 255, places=5)
        self.assertAlmostEqual(gr, 112 / 255, places=5)
        self.assertAlmostEqual(b, 223 / 255, places=5)
        self.assertAlmostEqual(a, 1.0, places=6)
        self.assertEqual(og.color_hex(rgba), "#DD70DFFF")

    def test_rejects_non_color_offset(self):
        # The document root is not a color table.
        self.assertIsNone(self.g.color_rgba(self.g.root()))

    def test_inventory_finds_magenta_in_placed_region(self):
        pr = self.g.placed_root_offset() or 0
        inv = self.g.color_inventory(pr)
        hexes = {c["hex"] for c in inv}
        self.assertIn("#DD70DFFF", hexes)
        # Library palette-name colors live below placed_root and must not leak in.
        self.assertTrue(all(c["table"] >= pr for c in inv))

    def test_palette_keeps_chromatic_drops_grayscale(self):
        inventory = [
            {"hex": "#DD70DFFF", "rgba": [0.8667, 0.4392, 0.8745, 1.0]},  # magenta ×2
            {"hex": "#DD70DFFF", "rgba": [0.8667, 0.4392, 0.8745, 1.0]},
            {"hex": "#000000FF", "rgba": [0.0, 0.0, 0.0, 1.0]},           # black default
            {"hex": "#FFFFFFFF", "rgba": [1.0, 1.0, 1.0, 1.0]},           # white default
            {"hex": "#80808000", "rgba": [0.5, 0.5, 0.5, 0.0]},           # transparent gray
            {"hex": "#5DAFEAFF", "rgba": [0.365, 0.686, 0.918, 1.0]},     # blue ×1
        ]
        pal = og.Graph.palette(inventory)
        hexes = [c["hex"] for c in pal]
        self.assertEqual(hexes, ["#DD70DFFF", "#5DAFEAFF"])  # chromatic only, most-used first
        self.assertEqual(pal[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
