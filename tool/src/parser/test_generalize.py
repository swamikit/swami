#!/usr/bin/env python3
"""Regression tests for the placed-vs-library boundary generalization.

The parser used to identify placed nodes by a hardcoded byte offset (`tail=360000`),
which worked only for the ~465 KB Touch document. On any larger `.origami` file the
tail cut falls INSIDE an embedded component definition and reports that component's
internals as "placed" nodes. This test checks the structural replacement:

  1. Interaction_Touch.origami still parses to a placed graph dominated by
     `builtin.layer.*` / `origami.LongPress` / `origami.DoubleTap` — the Touch demo.
  2. Interaction_Drag.origami now parses to its own placed graph (dominated by
     `origami.Drag` / `origami.DragSettings` / layers), NOT the embedded library.

Test files are not checked into the public repo — they live in swami-private
(`/Volumes/SatechiSSD/Developer/swami-private/patterns/Interaction/`). The test skips
gracefully when it can't find them so CI still runs.

Run:
    python3 -m tool.src.parser.test_generalize        # from repo root
    python3 tool/src/parser/test_generalize.py
"""
import os, pathlib, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tool" / "src"))
from parser.origami_graph import parse, Graph, read_graph_bytes  # noqa: E402

# Search paths for the private test corpus. First hit wins.
PRIVATE_CORPUS_CANDIDATES = [
    pathlib.Path(os.environ.get("SWAMI_PRIVATE_PATTERNS", "")),
    pathlib.Path("/Volumes/SatechiSSD/Developer/swami-private/patterns/Interaction"),
    REPO_ROOT.parent / "swami-private" / "patterns" / "Interaction",
    # Also allow dropping files next to this test for CI convenience.
    HERE / "fixtures",
]


def _corpus_file(name):
    for base in PRIVATE_CORPUS_CANDIDATES:
        if not base or not str(base): continue
        p = base / name
        if p.exists(): return p
    return None


# The public repo ships one origami example that is fully public: TouchOrigamiExample.
# Use it as a smoke test that ALWAYS runs.
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

    These tests require the private corpus (`swami-private/patterns/Interaction/`).
    They skip gracefully in environments (CI) where the files aren't available.
    """

    def test_interaction_touch_matches_public_example(self):
        p = _corpus_file("Interaction_Touch.origami")
        if not p:
            self.skipTest("Interaction_Touch.origami not available (needs swami-private)")
        out = parse(str(p))
        kinds = out["kinds"]
        # Same signature as the public TouchOrigamiExample.
        self.assertIn("origami.LongPress", kinds)
        self.assertIn("origami.DoubleTap", kinds)
        for library_marker in ("origami.Drag", "origami.DragSettings"):
            self.assertNotIn(library_marker, kinds,
                             f"Interaction_Touch contaminated with {library_marker}: kinds={kinds}")

    def test_interaction_drag_places_drag_not_library(self):
        p = _corpus_file("Interaction_Drag.origami")
        if not p:
            self.skipTest("Interaction_Drag.origami not available (needs swami-private)")
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


class TestStabilityAcrossCorpus(unittest.TestCase):
    """Every Interaction pattern locates SOME placed root — no silent failure."""

    def test_every_interaction_pattern_locates_placed_root(self):
        base = _corpus_file("Interaction_Drag.origami")
        if not base:
            self.skipTest("private Interaction corpus not available")
        base_dir = base.parent
        found_any = False
        for f in sorted(base_dir.glob("Interaction_*.origami")):
            found_any = True
            with self.subTest(pattern=f.name):
                g = Graph(read_graph_bytes(f))
                off = g.placed_root_offset()
                self.assertIsNotNone(off, f"{f.name}: placed_root_offset returned None")
                self.assertGreater(off, 0)
                self.assertLess(off, g.N)
        self.assertTrue(found_any, "no Interaction_*.origami files found")


if __name__ == "__main__":
    unittest.main()
