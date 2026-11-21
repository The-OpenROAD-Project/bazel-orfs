"""tangle.py on netlists whose tangles are known."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netlist_test as T  # noqa: E402
import tangle  # noqa: E402


def mesh_with_clump(n=48, clump=512, seed=3):
    """A mesh and a clump of randomly interconnected cells hanging off it by
    one net: the clump is the tangle."""
    lines = T.mesh(n)
    r = random.Random(seed)
    base = n * n
    lines += ["c\t%d\t0\t0" % (base + i) for i in range(clump)]
    for i in range(clump):
        lines.append(
            "n\t%d\t%s"
            % (base + i, ",".join(str(base + r.randrange(clump)) for _ in range(4)))
        )
    lines.append("n\t0\t%d" % base)
    return lines, base


class Tangle(unittest.TestCase):
    def test_finds_the_clump(self):
        lines, base = mesh_with_clump()
        out = tangle.build(lines, "0", p=0.5, k=4.0)
        top = out["gtl"][0]
        self.assertGreaterEqual(top["seed"], base)
        self.assertLess(top["score"], 0.5)
        mesh_only = tangle.build(T.mesh(48), "0", p=0.5, k=4.0)
        self.assertGreater(mesh_only["gtl"][0]["score"], top["score"])

    def test_net_range_counts_every_net_once(self):
        out = tangle.build(T.mesh(32), "0", p=0.5, k=4.0)
        nr = out["net_range"]
        self.assertLessEqual(sum(r["nets"] for r in nr["levels"]), nr["nets"])
        # a mesh's nets are local: few are cut at the top levels
        self.assertLess(nr["long_share"], 0.1)

    def test_contraction_of_a_mesh(self):
        c = tangle.build(T.mesh(32), "0", p=0.5, k=4.0)["contraction"]
        self.assertGreater(c["sampled"], 0)
        self.assertLessEqual(c["quantiles"]["q10"], c["quantiles"]["q90"])


if __name__ == "__main__":
    unittest.main()
