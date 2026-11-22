#!/usr/bin/env python3
"""A shard whose SAIF scope is wrong is caught by the sum.

    wrong_scope_test.py MERGE WRONG_SHARD PARENT_SHARD BLOCK_SHARD...

The wrong shard is BlockA's, read at the parent's scope instead of its
own. A wrong scope does not annotate nothing: the parent's cells and
BlockA's share generated names (`_360_`), and OpenSTA binds every pin
whose instance and port names match, so a quarter of BlockA's pins
(525 of 2,309) take the activity of unrelated parent cells and its
SAIF-driven report moves away from its vectorless one. Equal reports
are therefore not the check. The parent's shard says where its ODB has
each child, and the sum checks each child's scope against it; the
annotation rate is the second line. The sum, given the wrong shard in
place of BlockA's good one, must fail and name it by either;
the same set with the good shard must sum, so the failure is the wrong
scope's and nothing else's.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

MERGE, WRONG, PARENT = sys.argv[1:4]
GOOD = sys.argv[4:]


def load(path):
    with open(path) as f:
        return json.load(f)


def run(shards):
    d = tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR"))
    outs = [os.path.join(d, n) for n in ("less.json", "driven.json", "report.json")]
    return subprocess.run(
        [
            MERGE,
            "--vectorless",
            outs[0],
            "--vector-driven",
            outs[1],
            "--report",
            outs[2],
        ]
        + shards,
        capture_output=True,
        text=True,
    )


class WrongScopeTest(unittest.TestCase):
    def test_wrong_scope_binds_by_name_collision(self):
        s = load(WRONG)
        self.assertEqual(s["unit"], "u_blocka")
        annotated = s["annotation"]["saif_pins"]
        self.assertGreater(annotated, 0)
        self.assertLess(annotated, 0.9 * s["annotation"]["pins"])
        self.assertNotEqual(s["vector_driven"]["design"], s["vectorless"]["design"])

    def rest(self):
        good_a = [p for p in GOOD if load(p)["unit"] == "u_blocka"]
        self.assertEqual(len(good_a), 1)
        return [p for p in GOOD if p not in good_a]

    def test_sum_refuses_it_by_the_parents_odb(self):
        result = run([PARENT, WRONG] + self.rest())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "u_blocka: read the SAIF at TOP/mini_top, but the parent's ODB has "
            "it at TOP/mini_top/u_blocka",
            result.stderr,
        )

    def test_sum_refuses_it_by_its_annotation_rate(self):
        # without the parent's account of where its children are, the
        # rate alone still catches it
        parent = load(PARENT)
        del parent["child_scopes"]
        path = os.path.join(
            tempfile.mkdtemp(dir=os.environ.get("TEST_TMPDIR")), "p.json"
        )
        with open(path, "w") as f:
            json.dump(parent, f)
        result = run([path, WRONG] + self.rest())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("u_blocka: the SAIF annotated", result.stderr)
        self.assertIn("at scope TOP/mini_top, under 90%", result.stderr)

    def test_good_set_sums(self):
        result = run([PARENT] + GOOD)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
