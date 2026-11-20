"""Each seeded fault, planned on the toy's own extracts, is the first stop
with the right block, side and bus; the clean cut is feasible.

Arguments: <variant>=<verdict.json>=<stopped_at or feasible>,<block>,<side>,<bus>
with - for a field that does not apply."""

import json
import sys
import unittest

CASES = []


class PlanTest(unittest.TestCase):
    def test_variants(self):
        self.assertTrue(CASES)
        for variant, path, expect in CASES:
            with self.subTest(variant=variant):
                with open(path) as f:
                    v = json.load(f)
                stop, block, side, bus = expect.split(",")
                if stop == "feasible":
                    self.assertEqual(v["verdict"], "feasible", v["findings"])
                    continue
                self.assertEqual(v["stopped_at"], stop)
                fails = [
                    f
                    for f in v["findings"]
                    if f["status"] == "fail" and f["rung"] == stop
                ]
                self.assertEqual(fails[0]["block"], block)
                if side != "-":
                    self.assertEqual(fails[0]["side"], side)
                if bus != "-":
                    self.assertEqual(fails[0]["bus"], bus)
                self.assertTrue(fails[0]["remedies"])


if __name__ == "__main__":
    CASES = [a.split("=", 2) for a in sys.argv[1:]]
    unittest.main(argv=sys.argv[:1])
