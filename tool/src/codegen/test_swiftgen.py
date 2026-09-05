#!/usr/bin/env python3
"""Tests for legacy generation and semantic-IR planning."""
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from swiftgen import CodegenBlocked, analyze, gen  # noqa: E402


class TestLegacyTouchCodegen(unittest.TestCase):
    def test_touch_oracle_still_generates(self):
        ir = json.loads((REPO_ROOT / "tool/examples/TouchOrigamiExample.ir.json").read_text())
        swift = gen(ir)
        self.assertIn("public struct TouchOrigamiExampleView", swift)
        self.assertIn(".interaction(", swift)


class TestSemanticPlan(unittest.TestCase):
    @staticmethod
    def graph_ir():
        return {
            "schema_version": 1,
            "file": "Interaction_Drag.origami",
            "unresolved_edge_count": 0,
            "placed_nodes": [
                {"id": 1, "type": "ios.Screen", "name": "Artboard", "inputs": [], "outputs": []},
                {"id": 2, "type": "origami.Drag", "name": "Drag", "inputs": [
                    {"id": 20, "name": "Enable", "has_default": True, "value": {
                        "kind": "bool", "value": True
                    }},
                    {"id": 21, "name": "Start", "has_default": True},
                ], "outputs": [{"id": 22, "name": "Position"}]},
                {"id": 3, "type": "builtin.layer.binding", "name": "Position", "inputs": [
                    {"id": 30, "name": "Position", "has_default": True}
                ], "outputs": []},
            ],
            "edges": [{
                "source": {"node_id": 2, "port_id": 22},
                "destination": {"node_id": 3, "port_id": 30},
            }],
        }

    def test_general_ir_is_categorized_and_blocked_explicitly(self):
        plan = analyze(self.graph_ir())
        self.assertEqual(plan["node_count"], 3)
        self.assertEqual(plan["edge_count"], 1)
        self.assertEqual([node["type"] for node in plan["categories"]["interaction"]],
                         ["origami.Drag"])
        self.assertEqual(plan["blockers"][0]["kind"], "port_defaults")
        self.assertEqual(plan["blockers"][0]["ports"][0]["port"], "Start")
        self.assertFalse(plan["ready"])

        with self.assertRaisesRegex(CodegenBlocked, "port_defaults=1, layer_hierarchy=1"):
            gen(self.graph_ir())


if __name__ == "__main__":
    unittest.main()
