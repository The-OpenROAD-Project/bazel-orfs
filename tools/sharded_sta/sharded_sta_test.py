"""Unit tests of sharded_sta's Python: the kept-module tree and name resolution."""

import os
import tempfile
import unittest

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

    def test_resolve(self):
        self.assertEqual(plan.resolve_one(TREE, "Mid"), "Mid$Top.mid")
        with self.assertRaises(ValueError):
            plan.resolve(TREE, "Nope")
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


if __name__ == "__main__":
    unittest.main()
