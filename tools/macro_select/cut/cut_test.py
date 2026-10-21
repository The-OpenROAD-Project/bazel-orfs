"""The cut search's parsing, scoring and planning, on rows written by hand."""

import unittest

import cut

CENSUS = """\
module\t(top)\ttop\t100\t50.00
module\tk\tkx\t40\t20.00
module\ts0\tsbox_s0\t10\t5.00
module\ts1\tsbox_s1\t10\t5.00
cross\ts0\tsbox_s0\t3\t60.0\t30.0
cross\ts1\tsbox_s1\t5\t20.0\t5.0
cross\tk\tkx\t1\t2.0\t2.0
inside\t(top)\ttop\t8\t400.0
edge\t(top)\ts0\t3\t60.0\t30.0
period\t330.0\t380.0
paths\t9\t300\t330.0\t0.5
"""

RTLIL = """\
module \\top
  cell \\kx \\k
  end
  cell \\sbox \\s0
  end
  cell $and $1
  end
end
module \\kx
  cell \\sbox \\u0
  end
  cell \\rcon \\r
  end
end
module \\sbox
end
module \\rcon
end
module \\unused
end
"""


class ParseTest(unittest.TestCase):
    def test_rows(self):
        c = cut.parse_census(CENSUS.splitlines(True))
        self.assertEqual(len(c["module"]), 4)
        self.assertEqual(c["cross"][0]["worst"], 30.0)
        self.assertEqual(c["edge"][0]["worst"], 30.0)
        self.assertEqual(c["period"], {"worst": 330.0, "clock": 380.0})
        self.assertEqual(c["paths"]["target"], 300.0)

    def test_an_unfinished_census_is_refused(self):
        with self.assertRaises(ValueError):
            cut.parse_census(CENSUS.splitlines(True)[:-2])

    def test_an_unknown_row_is_refused(self):
        with self.assertRaises(ValueError):
            cut.parse_census(["what\t1\n"] + CENSUS.splitlines(True))


class HierarchyTest(unittest.TestCase):
    def test_types_under_the_top(self):
        hier = cut.rtlil_hierarchy(RTLIL.splitlines(True))
        self.assertEqual(cut.types_under(hier, "top"), ["kx", "rcon", "sbox"])

    def test_an_unknown_top_is_refused(self):
        with self.assertRaises(ValueError):
            cut.types_under(cut.rtlil_hierarchy(RTLIL.splitlines(True)), "nope")

    def test_a_uniquified_master_maps_to_its_rtl_type(self):
        types = ["aes_sbox", "aes_sbox_big", "aes_key_expand_128"]
        self.assertEqual(cut.rtl_type("aes_sbox_us10", types), "aes_sbox")
        self.assertEqual(cut.rtl_type("aes_sbox_big_u1", types), "aes_sbox_big")
        self.assertEqual(cut.rtl_type("aes_sbox", types), "aes_sbox")
        self.assertIsNone(cut.rtl_type("aes_sboxy", types))


class PlanTest(unittest.TestCase):
    types = ["kx", "sbox"]

    def census(self):
        return cut.parse_census(CENSUS.splitlines(True))

    def test_keep_all_comes_first_and_every_arm_is_planned(self):
        q = cut.plan(self.types, {}, None, lambda k: None)
        self.assertEqual(q[0]["keep"], ["kx", "sbox"])
        self.assertEqual(len(q), 4)

    def test_a_cut_on_a_worse_path_ranks_first(self):
        # sbox's boundary cut a path 30 ps over the target, kx's one 2 ps:
        # dropping sbox can move the period, dropping kx hardly
        base = ("kx", "sbox")
        results = {base: {"P": 330.0, "area": 50.0, "t_syn": 1.0}}
        q = cut.plan(self.types, results, base, {base: self.census()}.get)
        order = [x["keep"] for x in q]
        self.assertLess(order.index(["kx"]), order.index(["sbox"]))
        drop_sbox = q[order.index(["kx"])]
        self.assertEqual((drop_sbox["pred"], drop_sbox["pred_sum"]), (30.0, 80.0))
        # flat drops both: the same worst cut, more excess summed
        self.assertEqual(order[0], [])

    def test_time_beats_count(self):
        # s1 cut more paths (5) than s0 (3), but s0's reach the worst one
        c = self.census()
        ex = cut.crossing_excess(c, ["sbox", "kx"])
        self.assertEqual(ex["sbox"], (8, 80.0, 30.0))

    def test_greedy_past_the_exhaustive_bound(self):
        types = ["t%d" % i for i in range(5)]
        base = tuple(types)
        results = {base: {"P": 1.0, "area": 1.0, "t_syn": 1.0}}
        q = cut.plan(types, results, base, lambda k: None)
        self.assertEqual(len(q), 5)
        self.assertTrue(all(len(x["keep"]) == 4 for x in q))

    def test_the_best_arm_is_the_lexicographic_minimum(self):
        results = {
            ("a",): {"P": 300.0, "area": 9.0, "t_syn": 1.0},
            ("b",): {"P": 300.0, "area": 8.0, "t_syn": 5.0},
            ("c",): None,
            ("d",): {"P": None, "failed": "boom"},
        }
        self.assertEqual(cut.best(results), ("b",))


if __name__ == "__main__":
    unittest.main()
