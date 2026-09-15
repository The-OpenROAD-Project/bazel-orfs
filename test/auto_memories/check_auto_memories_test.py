#!/usr/bin/env python3
"""Unit tests for the AUTO_MEMORIES checker.

The checker only runs after synthesis, which is minutes; these run over
synthetic inputs in milliseconds, so the logic that decides pass or fail
is covered in CI even though the flow that feeds it is manual.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_auto_memories as c  # noqa: E402


def lef(width, height):
    return "MACRO m\n  SIZE {} BY {} ;\nEND m\n".format(width, height)


GOOD = {
    "memories": [
        {"name": "am_ram_2048x32", "idiomatic": True, "reason": "forced"},
        {
            "name": "regs",
            "idiomatic": False,
            "reason": "inferred inside module am_regs rather than being one",
        },
    ]
}


class InventoryTest(unittest.TestCase):
    def test_good_inventory_passes(self):
        self.assertEqual([], c.check_inventory(GOOD))

    def test_missing_convertible_memory_fails(self):
        doc = {"memories": [GOOD["memories"][1]]}
        problems = c.check_inventory(doc)
        self.assertTrue(any("am_ram_2048x32 is not in" in p for p in problems))

    def test_convertible_memory_refused_fails(self):
        """The override is forced, so a refusal means it was not read."""
        doc = json.loads(json.dumps(GOOD))
        doc["memories"][0]["idiomatic"] = False
        doc["memories"][0]["reason"] = "inferred inside module"
        problems = c.check_inventory(doc)
        self.assertTrue(any("was not converted" in p for p in problems))

    def test_inline_array_converted_fails(self):
        """The regression that generates a macro nothing can instantiate."""
        doc = {"memories": [{"name": "am_ram_2048x32", "idiomatic": True}]}
        problems = c.check_inventory(doc)
        self.assertTrue(any("no memory was refused" in p for p in problems))

    def test_refusal_without_a_reason_fails(self):
        doc = json.loads(json.dumps(GOOD))
        del doc["memories"][1]["reason"]
        problems = c.check_inventory(doc)
        self.assertTrue(any("without a reason" in p for p in problems))


class GeometryTest(unittest.TestCase):
    def _lefs(self, tmp, **shapes):
        out = {}
        for name, (w, h) in shapes.items():
            p = os.path.join(tmp, name + ".lef")
            with open(p, "w") as f:
                f.write(lef(w, h))
            out[name] = p
        return out

    def test_folded_macro_passes(self):
        """33.25 x 84.00 is what a folded 2048x32 comes out as, and is
        the geometry of the shipped fakeram7_256x256."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                [], c.check_geometry(self._lefs(tmp, m=(33.25, 84.00)))
            )

    def test_sliver_fails(self):
        """4.18 x 663.60 is an unfolded 2048x32."""
        with tempfile.TemporaryDirectory() as tmp:
            problems = c.check_geometry(self._lefs(tmp, m=(4.18, 663.60)))
            self.assertEqual(1, len(problems))
            self.assertIn("not being folded", problems[0])

    def test_no_lef_fails(self):
        self.assertTrue(any("no generated .lef" in p for p in c.check_geometry({})))

    def test_lef_without_a_size_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "m.lef")
            with open(p, "w") as f:
                f.write("MACRO m\nEND m\n")
            problems = c.check_geometry({"m": p})
            self.assertTrue(any("no SIZE" in x for x in problems))

    def test_the_worst_shipped_shape_is_accepted(self):
        """fakeram7_2048x39, 20.33 x 166.60 um, is 8.2:1 and is what the
        platform ships -- the bound must not fail the reference it is
        calibrated against. This caught a bound set at exactly 8.0."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                [], c.check_geometry(self._lefs(tmp, m=(20.33, 166.60)))
            )


class CollectTest(unittest.TestCase):
    def test_picks_files_by_name_not_by_searching(self):
        with tempfile.TemporaryDirectory() as tmp:
            views = os.path.join(tmp, "memories")
            os.mkdir(views)
            for n in ("a.lef", "a.lib", "blackboxes.txt"):
                open(os.path.join(views, n), "w").close()
            mj = os.path.join(tmp, "memories.json")
            open(mj, "w").close()
            got_json, got_lefs = c.collect([mj, views, os.path.join(tmp, "x.odb")])
            self.assertEqual(mj, got_json)
            self.assertEqual(["a"], sorted(got_lefs))


if __name__ == "__main__":
    unittest.main()
