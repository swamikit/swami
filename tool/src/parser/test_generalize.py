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
import pathlib, sys, unittest, urllib.request, urllib.error

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tool" / "src"))
from parser.origami_graph import parse, Graph, read_graph_bytes, VISUAL_LAYERS  # noqa: E402

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

# Patterns that exercise the placed-vs-library isolation (ADR-0017 + the no-artboard
# fallback). Each historically over-counted into an embedded library component:
#   Layers_List / Logic_Counter — no *.Screen inside the placed patch vector, so the
#     old selector grabbed a ~140-205 node wireless/binding library component.
#   Loops_Sum — artboard is desktop.Screen (non-iOS), previously unrecognized.
ISOLATION_CORPUS = (
    "Animation_Delay.origami",
    "Layers_List.origami",
    "Logic_Counter.origami",
    "Loops_Sum.origami",
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
    """The structural locator finds the placed node-vector for every valid document."""

    def test_public_touch_example_locates_placed_root(self):
        if not PUBLIC_EXAMPLE.exists():
            self.skipTest(f"{PUBLIC_EXAMPLE} not present")
        g = Graph(read_graph_bytes(PUBLIC_EXAMPLE))
        nv = g.placed_node_vector()
        self.assertIsNotNone(nv, "placed_node_vector returned None on TouchOrigamiExample")
        base, count = nv
        # Sanity bounds: the node vector is inside the file and non-empty.
        self.assertGreater(base, 0)
        self.assertLess(base, g.N)
        self.assertGreater(count, 0)

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
                nv = g.placed_node_vector()
                self.assertIsNotNone(nv, f"{f.name}: placed_node_vector returned None")
                base, count = nv
                self.assertGreater(base, 0)
                self.assertLess(base, g.N)
                self.assertGreater(count, 0)


class TestPlacedGraphIsolation(unittest.TestCase):
    """The placed graph is the artboard's own graph, never an embedded library component.

    Regression guard for the corpus-wide over-count (ADR-0017 + the no-artboard
    fallback): before the structural selector most patterns resolved to a 140-276 node
    blob dominated by an embedded scroll/list/logic component's wireless and binding
    plumbing. The placed graph is small (tens, not hundreds) and is a visual layer tree,
    not plumbing.
    """

    def _assert_isolated(self, name, out):
        n = out["placed_node_count"]
        kinds = out["kinds"]
        # Tens, not hundreds. A blob (an embedded library component) is 100+.
        self.assertGreaterEqual(n, 4, f"{name}: implausibly small placed graph: {n}")
        self.assertLess(n, 100, f"{name}: placed graph looks library-inclusive: {n} nodes")
        # Not dominated by an embedded component's internal wireless/binding plumbing.
        plumbing = sum(v for k, v in kinds.items()
                       if k in ("builtin.wirelessReceiver", "builtin.wirelessBroadcaster",
                                "builtin.layer.combinerBinding"))
        self.assertLess(plumbing, 0.30 * n,
                        f"{name}: placed graph is mostly wireless/binding plumbing "
                        f"({plumbing}/{n}) — likely a library component: kinds={kinds}")
        # It is a real artboard: has a screen node, or visual layers.
        screens = sum(v for k, v in kinds.items() if k.endswith(".Screen"))
        visual = sum(v for k, v in kinds.items() if k in VISUAL_LAYERS)
        self.assertTrue(screens or visual,
                        f"{name}: placed graph has neither a screen nor visual layers: {kinds}")

    def test_isolation_corpus(self):
        fetched = [(n, _fetch_corpus_file(n)) for n in ISOLATION_CORPUS]
        fetched = [(n, p) for (n, p) in fetched if p]
        if not fetched:
            self.skipTest("no isolation corpus fetchable (no network / origami.design down)")
        for name, p in fetched:
            with self.subTest(pattern=name):
                self._assert_isolated(name, parse(str(p)))


class TestPortDefaults(unittest.TestCase):
    """Input-port default values decode as inline f64 doubles from the port `f[4]` table (M2)."""

    def test_interaction_drag_port_defaults(self):
        p = _fetch_corpus_file("Interaction_Drag.origami")
        if not p:
            self.skipTest("Interaction_Drag not fetchable (no network / origami.design down)")
        out = parse(str(p))
        seen = {}
        for n in out["nodes"]:
            for d in n.get("ports", []):
                seen.setdefault((n["type"], d["port"]), d["default"])
        self.assertTrue(seen, "no port defaults decoded at all")
        # A layer Opacity default is a fraction in [0, 1] (Origami standard is 1.0).
        opac = seen.get(("builtin.layer.layer", "Opacity"))
        self.assertIsNotNone(opac, "no layer Opacity default decoded")
        self.assertTrue(all(0.0 <= v <= 1.0 for v in opac), f"Opacity out of range: {opac}")
        # DragSettings Momentum Friction decodes to a positive number read from the graph.
        mf = seen.get(("origami.DragSettings", "Momentum Friction"))
        self.assertIsNotNone(mf, "no DragSettings Momentum Friction default decoded")
        self.assertGreater(mf[0], 0, f"Momentum Friction not positive: {mf}")


if __name__ == "__main__":
    unittest.main()
