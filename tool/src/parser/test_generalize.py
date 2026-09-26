#!/usr/bin/env python3
"""Regression tests for the placed-vs-library boundary generalization.

The parser used to identify placed nodes by a hardcoded byte offset (`tail=360000`),
which worked only for the ~465 KB Touch document. On any larger `.origami` file the
tail cut falls INSIDE an embedded component definition and reports that component's
internals as "placed" nodes. This test checks the structural replacement:

  1. Interaction_Touch.origami parses to a placed graph dominated by
     `builtin.layer.*` / `origami.LongPress` / `origami.DoubleTap` — the Touch demo.
  2. Interaction_Drag.origami parses to its own placed graph (dominated by
     `origami.Drag` / `origami.DragSettings` / layers), NOT the embedded library.

Test corpus is fetched at test time from origami.design (ADR-0013 Path B):

    https://origami.design/public/origami_files/patterns/<Name>.origami

Files are cached under `tool/src/parser/.cache/` (gitignored). If the download
fails (offline dev / CI without network), the corpus tests skip gracefully so
the whole suite still runs.

Run:
    python3 -m tool.src.parser.test_generalize        # from repo root
    python3 tool/src/parser/test_generalize.py
"""
import pathlib, struct, sys, unittest, urllib.request, urllib.error

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tool" / "src"))
from parser.origami_graph import parse, Graph, read_graph_bytes  # noqa: E402

# Where fetched corpus files live locally (gitignored).
CACHE_DIR = HERE / ".cache"

# ADR-0013 Path B: public patterns are served from origami.design.
CORPUS_URL_BASE = "https://origami.design/public/origami_files/patterns"

# The interaction patterns we exercise. Each maps `<name>.origami` to a public URL
# at `{CORPUS_URL_BASE}/<name>.origami`.
INTERACTION_CORPUS = (
    "Interaction_Touch.origami",
    "Interaction_Drag.origami",
)


def _fetch_corpus_file(name):
    """Return a local `Path` to `name`, downloading from origami.design if needed.

    Returns None (rather than raising) when the file is not already cached and
    the download fails — e.g. offline dev environments or CI without egress.
    Callers should `skipTest` in that case so the rest of the suite still runs.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local = CACHE_DIR / name
    if local.exists() and local.stat().st_size > 0:
        return local
    url = f"{CORPUS_URL_BASE}/{name}"
    # origami.design returns 403 to requests without a User-Agent, so set one.
    req = urllib.request.Request(url, headers={"User-Agent": "swami-tests/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    if not data:
        return None
    local.write_bytes(data)
    return local


# The public repo used to ship one origami example (TouchOrigamiExample) under
# tool/examples/. It is gitignored (see .gitignore rule for `*.origami`) so it
# may or may not be present locally; treat it as an opportunistic smoke test.
PUBLIC_EXAMPLE = REPO_ROOT / "tool" / "examples" / "TouchOrigamiExample.origami"


class TestPlacedRootStructural(unittest.TestCase):
    """The structural locator picks a stable byte offset for every valid document."""

    def test_public_touch_example_locates_placed_root(self):
        if not PUBLIC_EXAMPLE.exists():
            self.skipTest(f"{PUBLIC_EXAMPLE} not present")
        g = Graph(read_graph_bytes(PUBLIC_EXAMPLE))
        off = g.placed_root_offset()
        self.assertIsNotNone(off, "placed_root_offset returned None on TouchOrigamiExample")
        # Sanity bounds: root is inside the file and above the file start.
        self.assertGreater(off, 0x1000)
        self.assertLess(off, g.N)

    def test_public_touch_example_kinds_match_oracle_shape(self):
        """The Touch demo's placed graph is dominated by layer patches + LongPress/DoubleTap."""
        if not PUBLIC_EXAMPLE.exists():
            self.skipTest(f"{PUBLIC_EXAMPLE} not present")
        out = parse(str(PUBLIC_EXAMPLE))
        kinds = out["kinds"]
        # Layer primitives that MUST appear in the Touch demo.
        for expected in ("builtin.layer.interaction", "builtin.layer.ellipse",
                         "builtin.layer.layer", "builtin.layer.text"):
            self.assertIn(expected, kinds, f"Touch demo missing {expected}: kinds={kinds}")
        # The Touch demo uses LongPress AND DoubleTap.
        self.assertIn("origami.LongPress", kinds, f"Touch demo missing LongPress: kinds={kinds}")
        # The Touch demo must NOT be dominated by Drag internals.
        for library_marker in ("origami.Drag", "origami.DragSettings", "origami.AddMomentum",
                               "origami.RoundtoScreenPixels"):
            self.assertNotIn(library_marker, kinds,
                             f"Touch parse contaminated with library patch {library_marker}: kinds={kinds}")
        # Reasonable node-count band: over the old hard-coded tail we saw ~49; the
        # structural boundary recovers more (~63) but is still nowhere near the full
        # library-inclusive 356. Any number outside [20, 100] is a red flag.
        self.assertGreaterEqual(out["placed_node_count"], 20)
        self.assertLessEqual(out["placed_node_count"], 100)


class TestInteractionCorpus(unittest.TestCase):
    """Verify placed-vs-library separation across the Interaction patterns.

    Corpus is fetched from origami.design at test time (ADR-0013 Path B) and
    cached under `tool/src/parser/.cache/`. Tests skip gracefully when the
    download fails (offline dev / CI without egress).
    """

    def test_interaction_touch_matches_public_example(self):
        p = _fetch_corpus_file("Interaction_Touch.origami")
        if not p:
            self.skipTest("Interaction_Touch.origami not fetchable (no network / origami.design down)")
        out = parse(str(p))
        kinds = out["kinds"]
        # Same signature as the public TouchOrigamiExample.
        self.assertIn("origami.LongPress", kinds)
        self.assertIn("origami.DoubleTap", kinds)
        for library_marker in ("origami.Drag", "origami.DragSettings"):
            self.assertNotIn(library_marker, kinds,
                             f"Interaction_Touch contaminated with {library_marker}: kinds={kinds}")
        # Touch is an independent document/table-shape oracle for typed Color.
        # Its artboard uses the same named ColorKit Purple token as the Inspector.
        self.assertTrue(any(
            abs(color["red"] - 221 / 255) < 1e-12
            and abs(color["green"] - 112 / 255) < 1e-12
            and abs(color["blue"] - 223 / 255) < 1e-12
            and color["alpha"] == 1.0
            for color in out["decoded_colors"]
        ), f"Interaction_Touch missing decoded Purple token: {out['decoded_colors']}")

    def test_interaction_drag_places_drag_not_library(self):
        p = _fetch_corpus_file("Interaction_Drag.origami")
        if not p:
            self.skipTest("Interaction_Drag.origami not fetchable (no network / origami.design down)")
        out = parse(str(p))
        kinds = out["kinds"]
        # The Drag demo's own placed graph HAS Drag / DragSettings.
        self.assertIn("origami.Drag", kinds,
                      f"Interaction_Drag placed graph missing origami.Drag: kinds={kinds}")
        self.assertIn("origami.DragSettings", kinds,
                      f"Interaction_Drag placed graph missing origami.DragSettings: kinds={kinds}")
        # And it should NOT be dominated by Touch's demo patches (LongPress/DoubleTap
        # never appear in the Drag demo's placed layer tree).
        self.assertNotIn("origami.LongPress", kinds,
                         f"Interaction_Drag contaminated with LongPress: kinds={kinds}")
        self.assertNotIn("origami.DoubleTap", kinds,
                         f"Interaction_Drag contaminated with DoubleTap: kinds={kinds}")
        # And the placed graph is NOT the whole library (would be ~350+ nodes).
        self.assertLess(out["placed_node_count"], 100,
                        f"Interaction_Drag over-counting into library: {out['placed_node_count']} nodes")

        # Input defaults are typed unions, not scalar vtable slots. Interaction Drag
        # requires this exact value; substituting an iOS deceleration constant is lossy.
        settings = next(n for n in out["placed_nodes"]
                        if n["type"] == "origami.DragSettings" and n["name"] == "Drag Settings")
        self.assertEqual(settings["port_defaults"]["Momentum Friction"],
                         {"type": "number", "value": 8.0})
        self.assertEqual(out["embedded_port_defaults"]["Rubber Band Friction"],
                         {"type": "number", "value": 8.0})
        self.assertEqual(out["embedded_port_defaults"]["Rubber Band Tension"],
                         {"type": "number", "value": 100.0})

        # Color payloads are Float64 RGBA. Purple is the corpus oracle: DD/70/DF,
        # alpha FF. This prevents the old ARGB-vs-RRGGBBAA guess from returning.
        purple = {"type": "color", "space": "sRGB", "channels": "RGBA",
                  "red": 221 / 255, "green": 112 / 255,
                  "blue": 223 / 255, "alpha": 1.0}
        self.assertTrue(any(all(abs(color[key] - value) < 1e-12
                                if isinstance(value, float) else color[key] == value
                                for key, value in purple.items())
                            for color in out["decoded_colors"]),
                        f"Interaction_Drag missing decoded Purple RGBA token: {out['decoded_colors']}")

        # A Color is accepted only through a typed value wrapper whose tag agrees
        # with payload field 17. Even the genuine color table is rejected without
        # owner metadata or with an unrelated tag, proving color-like bytes alone
        # cannot be misclassified. A corrupted union discriminator is also rejected.
        graph = Graph(read_graph_bytes(p))
        self.assertIsNone(graph.decode_value(settings["table"]))

        settings_info = graph.table(settings["table"])
        ports = graph.vector_entries(graph.field_uoffset_target(settings_info, 5))
        momentum_port = next(
            graph.table(offset) for offset in ports
            if graph.astr(graph.field_uoffset_target(graph.table(offset), 2))
            == "Momentum Friction"
        )
        number_offset = graph.field_uoffset_target(momentum_port, 4)
        number_tag = graph.field_u32(momentum_port, 0)
        self.assertIsNone(graph.decode_value(number_offset))
        self.assertIsNone(graph.decode_value(number_offset, number_tag ^ 0xFFFFFFFF))
        self.assertEqual(graph.decode_value(number_offset, number_tag),
                         {"type": "number", "value": 8.0})

        purple_offset, purple_value = next(
            (offset, value) for offset, value in graph.typed_value_payloads(
                graph.placed_root_offset())
            if value.get("type") == "color"
            and abs(value["red"] - 221 / 255) < 1e-12
            and abs(value["green"] - 112 / 255) < 1e-12
            and abs(value["blue"] - 223 / 255) < 1e-12
        )
        purple_info = graph.table(purple_offset)
        purple_tag = graph.field_u32(purple_info, 17)
        self.assertIsNone(graph.decode_value(purple_offset))
        self.assertIsNone(graph.decode_value(purple_offset, purple_tag ^ 0xFFFFFFFF))
        self.assertEqual(graph.decode_value(purple_offset, purple_tag), purple_value)

        corrupted = bytearray(graph.d)
        corrupted[purple_offset + graph.field_offset(purple_info, 0)] = 2
        self.assertIsNone(Graph(bytes(corrupted)).decode_value(purple_offset, purple_tag))


class TestTypedValueShapes(unittest.TestCase):
    """Union decoding follows vtable relationships rather than observed offsets."""

    @staticmethod
    def _value_table(fields, table_size=80):
        """Build the smallest ORGM buffer containing one schema-less value table."""
        data = bytearray(256)
        data[4:8] = b"ORGM"
        table, vtable = 96, 48
        field_count = 18  # includes the repeated union tag in field 17
        struct.pack_into('<HH', data, vtable, 4 + field_count * 2, table_size)
        for index, offset in fields.items():
            struct.pack_into('<H', data, vtable + 4 + index * 2, offset)
        struct.pack_into('<i', data, table, table - vtable)
        return data, table

    def test_number_uses_vtable_offset(self):
        data, table = self._value_table({1: 16, 17: 32})
        struct.pack_into('<d', data, table + 16, 8.0)
        struct.pack_into('<I', data, table + 32, 41)
        self.assertEqual(Graph(bytes(data)).decode_value(table, 41),
                         {"type": "number", "value": 8.0})

    def test_color_accepts_multiple_structural_field_layouts(self):
        expected = {"type": "color", "space": "sRGB", "channels": "RGBA",
                    "red": 221 / 255, "green": 112 / 255,
                    "blue": 223 / 255, "alpha": 1.0}
        # Neither layout uses the Interaction_Drag offsets (7 and 8). Both are
        # valid table shapes because their vtables preserve discriminator, RGBA
        # field, and repeated owner-tag relationships.
        for subtype_offset, rgba_offset, tag_offset in ((6, 16, 48), (12, 24, 56)):
            with self.subTest(rgba_offset=rgba_offset):
                data, table = self._value_table(
                    {0: subtype_offset, 4: rgba_offset, 17: tag_offset})
                data[table + subtype_offset] = 3
                struct.pack_into('<dddd', data, table + rgba_offset,
                                 expected["red"], expected["green"],
                                 expected["blue"], expected["alpha"])
                struct.pack_into('<I', data, table + tag_offset, 73)
                self.assertEqual(Graph(bytes(data)).decode_value(table, 73), expected)

    def test_color_rejects_wrong_owner_tag_and_overlapping_payload(self):
        data, table = self._value_table({0: 6, 4: 16, 17: 40})
        data[table + 6] = 3
        struct.pack_into('<dddd', data, table + 16, 0.1, 0.2, 0.3, 1.0)
        struct.pack_into('<I', data, table + 40, 73)
        graph = Graph(bytes(data))
        self.assertIsNone(graph.decode_value(table, 72))
        # Field 17 starts before all four channels fit, so this is not a Color.
        self.assertIsNone(graph.decode_value(table, 73))

    def test_extra_field_breaks_the_variant_shape(self):
        """Per-variant field-set validation: any unexpected field rejects the table."""
        # A Number-shaped table with an extra unrelated field is not a Number.
        data, table = self._value_table({1: 16, 2: 24, 17: 32})
        struct.pack_into('<d', data, table + 16, 8.0)
        struct.pack_into('<I', data, table + 24, 0)
        struct.pack_into('<I', data, table + 32, 41)
        self.assertIsNone(Graph(bytes(data)).decode_value(table, 41))
        # A Color-shaped table with an extra unrelated field is not a Color.
        data, table = self._value_table({0: 6, 4: 16, 9: 48, 17: 56})
        data[table + 6] = 3
        struct.pack_into('<dddd', data, table + 16, 0.1, 0.2, 0.3, 1.0)
        struct.pack_into('<I', data, table + 56, 73)
        self.assertIsNone(Graph(bytes(data)).decode_value(table, 73))

    def test_wrong_discriminator_presence_rejects_each_variant(self):
        """A Number must lack the discriminator; a Color must carry subtype 3."""
        # Discriminator present on a Number-shaped table -> not a Number.
        data, table = self._value_table({0: 6, 1: 16, 17: 32})
        data[table + 6] = 0
        struct.pack_into('<d', data, table + 16, 8.0)
        struct.pack_into('<I', data, table + 32, 41)
        self.assertIsNone(Graph(bytes(data)).decode_value(table, 41))
        # Discriminator absent on a Color-shaped table -> not a Color.
        data, table = self._value_table({4: 16, 17: 48})
        struct.pack_into('<dddd', data, table + 16, 0.1, 0.2, 0.3, 1.0)
        struct.pack_into('<I', data, table + 48, 73)
        self.assertIsNone(Graph(bytes(data)).decode_value(table, 73))
        # Discriminator present but not 3 -> not a Color.
        data, table = self._value_table({0: 6, 4: 16, 17: 48})
        data[table + 6] = 2
        struct.pack_into('<dddd', data, table + 16, 0.1, 0.2, 0.3, 1.0)
        struct.pack_into('<I', data, table + 48, 73)
        self.assertIsNone(Graph(bytes(data)).decode_value(table, 73))

    def test_malformed_populated_offsets_are_not_absent_fields(self):
        for extra_offset in (1, 80, 255):
            with self.subTest(extra_offset=extra_offset):
                data, table = self._value_table({1: 16, 2: extra_offset, 17: 32})
                struct.pack_into('<d', data, table + 16, 8.0)
                struct.pack_into('<I', data, table + 32, 41)
                self.assertIsNone(Graph(bytes(data)).decode_value(table, 41))

    def test_rejects_aliases_header_overlap_and_truncated_fields(self):
        for fields in ({1: 16, 17: 16}, {1: 16, 17: 14},
                       {1: 2, 17: 32}, {1: 76, 17: 32},
                       {1: 16, 17: 78}, {0: 16, 4: 16, 17: 48}):
            with self.subTest(fields=fields):
                data, table = self._value_table(fields)
                self.assertIsNone(Graph(bytes(data)).decode_value(table, 0))

    def test_rejects_nonfinite_numbers_and_invalid_color_channels(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.subTest(number=value):
                data, table = self._value_table({1: 16, 17: 32})
                struct.pack_into('<d', data, table + 16, value)
                struct.pack_into('<I', data, table + 32, 41)
                self.assertIsNone(Graph(bytes(data)).decode_value(table, 41))
        for channel in range(4):
            for value in (-0.01, 1.01, float('nan'), float('inf')):
                with self.subTest(channel=channel, value=value):
                    data, table = self._value_table({0: 7, 4: 8, 17: 40})
                    data[table + 7] = 3
                    channels = [0.0, 0.5, 1.0, 1.0]
                    channels[channel] = value
                    struct.pack_into('<dddd', data, table + 8, *channels)
                    struct.pack_into('<I', data, table + 40, 73)
                    self.assertIsNone(Graph(bytes(data)).decode_value(table, 73))

    def test_missing_and_truncated_value_tables_fail_closed(self):
        data, table = self._value_table({1: 16, 17: 32})
        self.assertIsNone(Graph(bytes(data)).decode_value(None, 41))
        self.assertIsNone(Graph(bytes(data[:table + 20])).decode_value(table, 41))


class TestStabilityAcrossCorpus(unittest.TestCase):
    """Every Interaction pattern locates SOME placed root — no silent failure."""

    def test_every_interaction_pattern_locates_placed_root(self):
        fetched = []
        for name in INTERACTION_CORPUS:
            p = _fetch_corpus_file(name)
            if p:
                fetched.append(p)
        if not fetched:
            self.skipTest("no Interaction_*.origami fetchable (no network / origami.design down)")
        for f in fetched:
            with self.subTest(pattern=f.name):
                g = Graph(read_graph_bytes(f))
                off = g.placed_root_offset()
                self.assertIsNotNone(off, f"{f.name}: placed_root_offset returned None")
                self.assertGreater(off, 0)
                self.assertLess(off, g.N)


if __name__ == "__main__":
    unittest.main()
