"""slowest_actions on a hand-written profile: what it ranks, what it sums."""

import gzip
import json
import os
import tempfile
import unittest

import slowest_actions

EVENTS = [
    {
        "cat": "action processing",
        "ph": "X",
        "dur": 30_000_000,
        "name": "Action results/2_floorplan.odb",
        "args": {"mnemonic": "OrfsFloorplan"},
    },
    {
        "cat": "action processing",
        "ph": "X",
        "dur": 2_000_000,
        "name": "Compiling a.cc [for tool]",
        "args": {"mnemonic": "CppCompile"},
    },
    {
        "cat": "action processing",
        "ph": "X",
        "dur": 3_000_000,
        "name": "Compiling b.cc [for tool]",
        "args": {"mnemonic": "CppCompile"},
    },
    {
        "cat": "critical path component",
        "ph": "X",
        "dur": 30_000_000,
        "name": "action 'Action results/2_floorplan.odb'",
    },
    {
        "cat": "critical path component",
        "ph": "X",
        "dur": 3_000_000,
        "name": "action 'Compiling b.cc [for tool]'",
    },
    # Not an action: never ranked.
    {"cat": "general information", "ph": "X", "dur": 99_000_000, "name": "build"},
]


class SlowestActionsTest(unittest.TestCase):
    def test_summary(self):
        out = slowest_actions.summarize(EVENTS, 10)
        self.assertIn("Critical path: 33 s", out)
        per_mnemonic = out.split("Time per mnemonic")[1].split("Slowest actions")[0]
        self.assertIn("30 s       1  OrfsFloorplan", per_mnemonic)
        self.assertIn("5 s       2  CppCompile", per_mnemonic)
        slowest = out.split("Slowest actions:\n")[1].splitlines()
        self.assertIn("2_floorplan.odb", slowest[0])
        self.assertIn("b.cc", slowest[1])
        self.assertNotIn("build", out.split("Slowest actions:")[1])

    def test_top_limits_each_list(self):
        slowest = slowest_actions.summarize(EVENTS, 1).split("Slowest actions:\n")[1]
        self.assertEqual(len(slowest.splitlines()), 1)

    def test_gzipped_and_plain_profiles_load_alike(self):
        doc = json.dumps({"otherData": {}, "traceEvents": EVENTS}).encode()
        with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as d:
            plain = os.path.join(d, "plain.profile")
            packed = os.path.join(d, "packed.profile")
            with open(plain, "wb") as f:
                f.write(doc)
            with open(packed, "wb") as f:
                f.write(gzip.compress(doc))
            self.assertEqual(slowest_actions.load(plain), EVENTS)
            self.assertEqual(slowest_actions.load(packed), EVENTS)


if __name__ == "__main__":
    unittest.main()
