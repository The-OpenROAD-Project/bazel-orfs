#!/usr/bin/env python3
"""The shards' sum is the flat report of the same physical design.

    sum_test.py GRT_FLAT_LESS GRT_FLAT_DRIVEN GRT_SUM_LESS GRT_SUM_DRIVEN \\
                PL_FLAT_LESS PL_FLAT_DRIVEN PL_SUM_LESS PL_SUM_DRIVEN

The flat report is the parent's global-route ODB with every block
dissolved into its own global route's cells, nets and guides; the sum is
stage_power_shards' over the parent's and the blocks' own ODBs. Both are
taken twice, parasitics estimated from placement (PL) and from global
routing (GRT). Only the SAIF-driven arm is compared: in a block's own
shard an input port is a root of OpenSTA's activity propagation and gets
its default activity, so a vectorless sum is not the flat vectorless
number and is not meant to be (28 % under it on the toy).

Placement parasitics depend on pin places alone, which the dissolve
keeps, so every net inside a unit has the same capacitance in both, and
the comparison is of the accounting. Measured per instance on the toy:
every cell's switching power inside a block equal to the flat one's,
leakage equal everywhere. What is left is on the nets that cross a
block boundary:

  switching  the flat design estimates such a net as one Steiner tree
             over all its pins; the shards as two, the parent's to the
             block pin and the block's from its port, which is where the
             wire goes. Two trees through a point are never shorter than
             one: the sum is above the flat number, +1.9 % of switching
             on the toy, all of it on boundary nets.
  internal   the first cells inside a block see the SDC's ideal input
             slew, a block's output drivers no load past the port:
             +7 and -8 uW against each other, -0.02 % net.

With global-routing parasitics the flat design's dissolved nets carry
the blocks' guides moved into the parent's gcell grid, and its router
does not rebuild every one of them as the block did (pins reported
without a route, EST-0026): the flat number's own wire is short, by 13 %
on the blocks' clock nets. Leakage and internal power, which do not
depend on that wire, are still compared; switching is not.
"""

import json
import sys
import unittest

KINDS = ["internal", "switching", "leakage", "total"]

# relative to the flat number
PLACEMENT_TOL = {
    "leakage": 1e-5,
    "internal": 1e-3,
    "switching": 0.03,
    "total": 0.01,
}
GRT_TOL = {
    "leakage": 1e-5,
    "internal": 1e-3,
}


def load(path):
    with open(path) as f:
        return json.load(f)["Total"]


GRT = (load(sys.argv[2]), load(sys.argv[4]), load(sys.argv[1]))
PLACEMENT = (load(sys.argv[6]), load(sys.argv[8]), load(sys.argv[5]))


def rel(summed, flat, k):
    return (summed[k] - flat[k]) / flat[k]


class SumTest(unittest.TestCase):
    def check(self, name, arm, tol):
        flat, summed, _ = arm
        for k in KINDS:
            print(
                "{:9} {:9} flat {:.6e} sum {:.6e} {:+.3%}".format(
                    name, k, flat[k], summed[k], rel(summed, flat, k)
                )
            )
        for k, t in tol.items():
            with self.subTest(parasitics=name, kind=k):
                self.assertLessEqual(abs(rel(summed, flat, k)), t)

    def test_placement_sum_is_flat(self):
        self.check("placement", PLACEMENT, PLACEMENT_TOL)

    def test_boundary_nets_count_at_least_the_flat_wire(self):
        flat, summed, _ = PLACEMENT
        self.assertGreaterEqual(summed["switching"], flat["switching"])

    def test_grt_sum_is_flat_where_wire_does_not_matter(self):
        self.check("grt", GRT, GRT_TOL)

    def test_saif_moved_the_flat_number(self):
        # the comparisons mean something only if the SAIF bound
        for flat_driven, _, flat_less in (GRT, PLACEMENT):
            self.assertNotEqual(flat_less["total"], flat_driven["total"])


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
