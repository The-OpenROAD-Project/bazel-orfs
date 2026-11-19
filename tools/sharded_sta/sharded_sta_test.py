"""Unit tests of sharded_sta's Python: the tree, the shard plans, the merge."""

import os
import tempfile
import unittest

import merge
import plan
import tree

TREE = {
    "top": "Top",
    "modules": {
        "Top": {"file": "partition_top.v", "children": ["Mid$Top.mid", "Other"]},
        "Mid$Top.mid": {"file": "partition_Mid.v", "children": ["Leaf"]},
        "Leaf": {"file": "partition_Leaf.v", "children": []},
        "Other": {"file": "partition_Other.v", "children": []},
    },
}


class TreeTest(unittest.TestCase):
    def test_kept_children_through_flattened_modules(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as d:
            files = {
                "partition_top.v": "module Top(clock);\n  Helper h (.a(x));\n  \\Mid$Top.mid  mid (.clock(clock));\nendmodule\n"
                "module Helper(a);\n  Other other (.a(a));\n  BUF_X1 b (.A(a));\nendmodule\n",
                "partition_Mid.v": "module \\Mid$Top.mid (clock);\n  Leaf leaf (.clock(clock));\nendmodule\n",
                "partition_Leaf.v": "module Leaf(clock);\n  DFF_X1 r (.CK(clock));\nendmodule\n",
                "partition_Other.v": "module Other(a);\nendmodule\n",
            }
            paths = []
            for name, text in files.items():
                p = os.path.join(d, name)
                with open(p, "w") as f:
                    f.write(text)
                paths.append(p)
            t = tree.tree("Top", paths)
            self.assertEqual(
                sorted(t["modules"]), ["Leaf", "Mid$Top.mid", "Other", "Top"]
            )
            self.assertEqual(t["modules"]["Top"]["children"], ["Mid$Top.mid", "Other"])
            self.assertEqual(t["modules"]["Mid$Top.mid"]["children"], ["Leaf"])

    def test_missing_top(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as d:
            p = os.path.join(d, "partition_a.v")
            with open(p, "w") as f:
                f.write("module A();\nendmodule\n")
            with self.assertRaises(ValueError):
                tree.tree("Top", [p])


class PlanTest(unittest.TestCase):
    def test_subtree_and_files(self):
        self.assertEqual(plan.subtree(TREE, "Mid$Top.mid"), ["Leaf", "Mid$Top.mid"])
        self.assertEqual(
            plan.files(TREE, ["Leaf", "Mid$Top.mid"]),
            ["partition_Leaf.v", "partition_Mid.v"],
        )

    def test_owners_and_glue(self):
        own = plan.owners(TREE, {"mid": ["Mid"], "other": ["Other"]}, "glue")
        self.assertEqual(
            own,
            {
                ("Top",): "glue",
                ("Top", "Mid$Top.mid"): "mid",
                ("Top", "Mid$Top.mid", "Leaf"): "mid",
                ("Top", "Other"): "other",
            },
        )

    def test_deep_listing_forces_ancestors_and_models_the_rest(self):
        shards = {"leaf": ["Leaf"], "rest": ["Mid", "Other"]}
        self.assertEqual(
            plan.shard_plan(TREE, shards, "glue", "leaf"),
            (
                ["Leaf", "Mid$Top.mid", "Top"],
                ["Other"],
                ["Leaf"],
                ["Mid$Top.mid", "Other"],
            ),
        )
        self.assertEqual(
            plan.shard_plan(TREE, shards, "glue", "rest"),
            (
                ["Mid$Top.mid", "Other", "Top"],
                ["Leaf"],
                ["Mid$Top.mid", "Other"],
                ["Leaf"],
            ),
        )
        self.assertEqual(
            plan.shard_plan(TREE, shards, "glue", "glue"),
            (["Top"], ["Mid$Top.mid", "Other"], [], ["Leaf", "Mid$Top.mid", "Other"]),
        )

    def test_a_module_kept_in_two_places_has_an_owner_per_place(self):
        shared = {
            "top": "Top",
            "modules": {
                "Top": {"file": "t", "children": ["A", "B"]},
                "A": {"file": "a", "children": ["S"]},
                "B": {"file": "b", "children": ["S"]},
                "S": {"file": "s", "children": []},
            },
        }
        own = plan.owners(shared, {"a": ["A"]}, "glue")
        self.assertEqual(
            (own[("Top", "A", "S")], own[("Top", "B", "S")]), ("a", "glue")
        )
        self.assertEqual(
            plan.shard_plan(shared, {"a": ["A"]}, "glue", "a")[:2],
            (["A", "S", "Top"], ["B"]),
        )
        self.assertEqual(
            plan.shard_plan(shared, {"a": ["A"]}, "glue", "glue")[:2],
            (["B", "S", "Top"], ["A"]),
        )

    def test_refusals(self):
        with self.assertRaises(ValueError):
            plan.owners(TREE, {"a": ["Mid"], "b": ["Mid$Top.mid"]}, "glue")
        with self.assertRaises(ValueError):
            plan.owners(TREE, {"a": ["Nope"]}, "glue")
        two = {
            "top": "T",
            "modules": {
                "T": {"file": "t", "children": ["X$T.a", "X$T.b"]},
                "X$T.a": {"file": "a", "children": []},
                "X$T.b": {"file": "b", "children": []},
            },
        }
        self.assertEqual(plan.resolve(two, "X"), ["X$T.a", "X$T.b"])
        with self.assertRaises(ValueError):
            plan.resolve_one(two, "X")


class MergeTest(unittest.TestCase):
    def test_merge_refuses_a_pin_twice(self):
        with self.assertRaises(ValueError):
            merge.merge({"a": [("p", 1.0, True)], "b": [("p", 1.0, True)]})

    def test_report_keeps_modelled_out_of_the_period(self):
        merged = merge.merge(
            {"a": [("p", 5.0, True), ("q", -50.0, False)], "b": [("r", -3.0, True)]}
        )
        r = merge.report(merged, {}, 10)
        self.assertEqual((r["endpoints"], r["exact"], r["modelled"]), (3, 2, 1))
        self.assertEqual(
            (r["wns_exact"], r["wns_modelled"], r["tns_exact"]), (-3.0, -50.0, -3.0)
        )
        self.assertEqual([w["endpoint"] for w in r["worst"]], ["r", "p"])
        self.assertEqual(sum(b["count"] for b in r["histogram_exact"]), 2)


if __name__ == "__main__":
    unittest.main()
