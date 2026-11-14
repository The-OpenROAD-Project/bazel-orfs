"""Unit tests of module_sta's Python: endpoint files, the comparison, the A/B."""

import os
import tempfile
import unittest

import ab
import ends
import rename_module


class EndsTest(unittest.TestCase):
    def test_read_unescapes(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as d:
            p = os.path.join(d, "x.ends")
            with open(p, "w") as f:
                f.write("a/b\\[0\\]$_DFF_P_/D 12.5\n\n")
            self.assertEqual(ends.read_ends(p), {"a/b[0]$_DFF_P_/D": 12.5})

    def test_summary(self):
        s = ends.summary({"a": -3.0, "b": -1.0, "c": 2.0})
        self.assertEqual(
            (s["wns"], s["tns"], s["violating"], s["endpoints"]), (-3.0, -4.0, 2, 3)
        )

    def test_compare_catches_a_difference(self):
        # the negative control of the comparison itself: a moved slack and
        # an endpoint the reference lacks are both reported
        diff = ends.compare({"a": 1.0, "b": 2.0, "c": 0.0}, {"a": 1.0, "b": 2.5}, 0.001)
        self.assertEqual(len(diff), 2)
        self.assertEqual(ends.compare({"a": 1.0}, {"a": 1.0, "x": 5.0}, 0.001), [])


class RenameTest(unittest.TestCase):
    def test_escaped(self):
        text = "/* yosys */\nmodule \\Inner$Top.outer.inner (a, q);\n  input a;\nendmodule\n"
        self.assertEqual(
            rename_module.rename(text, "Inner_new"),
            "/* yosys */\nmodule Inner_new (a, q);\n  input a;\nendmodule\n",
        )

    def test_one_module_only(self):
        with self.assertRaises(ValueError):
            rename_module.rename(
                "module a(x);\nendmodule\nmodule b(y);\nendmodule\n", "c"
            )


class AbTest(unittest.TestCase):
    def test_report(self):
        text = ab.report({"u/f/D": 1.0, "g/D": -1.0}, {"u/f/D": -2.0, "g/D": -1.0})
        self.assertIn("worst slack", text)
        self.assertIn("Started violating in B: 1", text)
        self.assertIn("u/f/D  1.0 -> -2.0", text)
        self.assertIn("Stopped violating in B: 0", text)


if __name__ == "__main__":
    unittest.main()
