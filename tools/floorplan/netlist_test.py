"""Rent's p from the fixed partitioner on netlists whose p is known, and
each port's cone on a hand netlist."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netlist  # noqa: E402


def mesh(n):
    """A square grid, each cell driving its right and lower neighbours:
    Rent's p is 1/2."""
    lines = ["c\t%d\t0\t0" % i for i in range(n * n)]
    for y in range(n):
        for x in range(n):
            i = y * n + x
            s = [str(j) for j, ok in ((i + 1, x + 1 < n), (i + n, y + 1 < n)) if ok]
            if s:
                lines.append("n\t%d\t%s" % (i, ",".join(s)))
    return lines


def scatter(n, fanout=3, seed=1):
    """Every cell driving random cells: no locality, p near 1."""
    r = random.Random(seed)
    lines = ["c\t%d\t0\t0" % i for i in range(n)]
    for i in range(n):
        lines.append(
            "n\t%d\t%s" % (i, ",".join(str(r.randrange(n)) for _ in range(fanout)))
        )
    return lines


# input a[0] fans out to three gates, each into a register; a[1] reaches
# one gate; the registers drive q[0] through one gate
HAND = """c\t1\t0\t0
c\t2\t0\t0
c\t3\t0\t0
c\t4\t1\t0
c\t5\t1\t0
c\t6\t1\t0
c\t7\t0\t0
p\t10\ta[0]\tinput
p\t11\ta[1]\tinput
p\t12\tq[0]\toutput
p\t13\tf_in[0]\tinput
p\t14\tf_out[0]\toutput
p\t15\tf_in[1]\tinput
p\t16\tf_out[1]\toutput
c\t8\t0\t0
c\t9\t0\t0
n\tp10\t1,2,3
n\tp11\t3
n\t1\t4
n\t2\t5
n\t3\t6
n\t4\t7
n\t5\t7
n\t7\tp12
n\tp13\t8
n\t8\t9
n\t9\tp14
n\tp15\tp16
""".splitlines()


class Rent(unittest.TestCase):
    def test_mesh_is_a_half(self):
        r = netlist.Netlist(mesh(64)).rent()
        self.assertAlmostEqual(r["p"], 0.5, delta=0.08)
        self.assertEqual(r["fit"][0], 2)

    def test_scatter_is_near_one(self):
        r = netlist.Netlist(scatter(4096)).rent()
        self.assertGreater(r["p"], 0.75)

    def test_deterministic(self):
        a = netlist.Netlist(scatter(2048)).rent()
        b = netlist.Netlist(scatter(2048)).rent()
        self.assertEqual(a, b)

    def test_too_small_has_no_fit(self):
        self.assertIsNone(netlist.Netlist(HAND).rent()["p"])


class Feedthrough(unittest.TestCase):
    def test_buffer_chain_and_wire(self):
        b = netlist.build(HAND, "0")
        self.assertEqual(b["feedthrough"], {"bits": 2, "cells": 2, "connections": 4})
        self.assertEqual(b["buses"]["f_in"]["feedthrough"], 2)
        self.assertEqual(b["buses"]["a"]["feedthrough"], 0)

    def test_fanout_ranks_sinks(self):
        f = netlist.build(HAND, "0")["fanout"]
        self.assertEqual((f[0]["sinks"], f[0]["driver"]), (3, "port"))


class Cones(unittest.TestCase):
    def setUp(self):
        self.b = netlist.Netlist(HAND).buses()

    def test_input_cone_stops_at_registers(self):
        # a[0]: three gates, then three registers; a[1]: one gate, one register
        a = self.b["a"]
        self.assertEqual((a["bits"], a["sampled"]), (2, 2))
        self.assertEqual(a["cells_mean"], 4.0)
        self.assertEqual(a["breadth_mean"], 2.0)
        self.assertEqual(a["breadth_max"], 3)

    def test_output_cone_backward(self):
        q = self.b["q"]
        self.assertEqual((q["cells_mean"], q["breadth_max"]), (3.0, 2))

    def test_cap(self):
        nl = netlist.Netlist(HAND)
        self.assertEqual(nl.cone(0, cap=2), (2, 3, True))


if __name__ == "__main__":
    unittest.main()
