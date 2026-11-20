import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parent_json  # noqa: E402

DUMP = """parent\ttop
glue\t80.5
module\tcore\tCore\t600.0
cross\tCore\tcore\tq[0]\tVec\tvec\td[0]\tcomb\t3\t100.0\t300.0
cross\tCore\tcore\tq[0]\tVec\tvec\td[1]\tcomb\t4\t100.0\t350.0
cross\tCore\tcore\tq[1]\tVec\tvec\td[1]\tcomb\t4\t250.0\t350.0
cross\tCore\tcore\tw[0]\tVec\tvec\tw[0]\twire\t0\t40.0\t40.0
cross\tMem\tmem\tr[0]\tCore\tcore\tr[0]\treg\t2\t0.0\t44.0
cross\ttop\t-\tin[0]\tCore\tcore\tin[0]\twire\t0\t0.0\t0.0
""".splitlines()


class ParentJsonTest(unittest.TestCase):
    def setUp(self):
        p = parent_json.build(DUMP, "0")
        self.p = p
        self.x = {(c["a"], c["a_bus"], c["b"], c["b_bus"]): c for c in p["crossings"]}

    def test_every_bit_of_each_end(self):
        c = self.x[("Core", "q", "Vec", "d")]
        self.assertEqual((c["a_bits"], c["b_bits"], c["bits"]), (2, 2, 2))
        self.assertEqual(c["depth"], 4)

    def test_glue_delay_is_worst_in_less_worst_out(self):
        self.assertEqual(self.x[("Core", "q", "Vec", "d")]["glue_ps"], 100.0)
        self.assertEqual(self.x[("Core", "w", "Vec", "w")]["glue_ps"], 0.0)
        self.assertEqual(self.x[("Mem", "r", "Core", "r")]["glue_ps"], 44.0)

    def test_glue_and_modules(self):
        self.assertEqual(self.p["glue"]["std_um2"], 80.5)
        self.assertEqual(self.p["modules"]["core"], {"module": "Core", "um2": 600.0})
        self.assertIn(("top", "in", "Core", "in"), self.x)


if __name__ == "__main__":
    unittest.main()
