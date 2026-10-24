"""crossings.py: block stretches become in, out and thru keys, ranked by
the mass above the period."""

import unittest

import crossings

LINES = [
    # parent -> Frontend -> parent: through Frontend
    "2300\tXSTile->via:Frontend->XSTile\tXSTile:a:b:100\tFrontend:io_in_2_x[3]:io_out[1]:900\tXSTile:c:d:200\n",
    # MemBlock -> parent: out of MemBlock
    "2100\tMemBlock->XSTile\tMemBlock:q:io_ld_0_bits[7]:600\tXSTile:e:f:300\n",
    # parent -> Frontend: into Frontend, the same port group as the first
    "2050\tXSTile->Frontend\tXSTile:g:h:400\tFrontend:io_in_5_x[0]:r:700\n",
    # below the period: ignored
    "1900\tXSTile->Frontend\tXSTile:g:h:400\tFrontend:io_in_5_x[0]:r:700\n",
    # parent only: no block stretch
    "2500\tparent\tXSTile:g:h:2500\n",
]


class Crossings(unittest.TestCase):
    def test_port_group(self):
        self.assertEqual(crossings.port_group("io_in_2_x[3]"), "io_in_N_x")
        self.assertEqual(crossings.port_group("io_ld_0_bits"), "io_ld_N_bits")

    def test_rank(self):
        t = crossings.rank(LINES, 2000, "XSTile")
        self.assertEqual(
            t[("thru", "Frontend", "io_in_N_x", "io_out")], [1, 300, 2300, 900]
        )
        self.assertEqual(t[("out", "MemBlock", "io_ld_N_bits")], [1, 100, 2100, 600])
        self.assertEqual(t[("in", "Frontend", "io_in_N_x")], [1, 50, 2050, 700])
        self.assertEqual(len(t), 3)

    def test_render_orders_by_mass(self):
        out = crossings.render(crossings.rank(LINES, 2000, "XSTile"), 10).splitlines()
        self.assertIn("thru | Frontend", out[2])


if __name__ == "__main__":
    unittest.main()
