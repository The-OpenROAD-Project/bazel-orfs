import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parent_json  # noqa: E402

DUMP = """parent\ttop
glue\t80.5
module\tcore\tCore\t600.0
cross\tCore\tcore\tq\t32\tVec\tvec\td\t32\tcomb\t4\t200.0
cross\tCore\tcore\tw\t8\tVec\tvec\tw\t8\twire\t0\t0.0
cross\tMem\tmem\tr\t16\ttop\treg\t\t16\treg\t2\t0.0
cross\ttop\treg\t\t16\tCore\tcore\tr\t16\treg\t2\t44.0
cross\ttop\t-\tin\t4\tCore\tcore\tin\t4\twire\t0\t0.0
""".splitlines()


class ParentJsonTest(unittest.TestCase):
    def setUp(self):
        p = parent_json.build(DUMP, "0")
        self.p = p
        self.x = {
            (c["a"], c["a_inst"], c["a_bus"], c["b"], c["b_inst"], c["b_bus"]): c
            for c in p["crossings"]
        }

    def test_buses_and_bits(self):
        c = self.x[("Core", "core", "q", "Vec", "vec", "d")]
        self.assertEqual(
            (c["a_bits"], c["b_bits"], c["bits"], c["via"], c["glue_ps"]),
            (32, 32, 32, "comb", 200.0),
        )

    def test_glue_registers_and_ports(self):
        self.assertEqual(self.x[("Mem", "mem", "r", "top", "reg", "")]["via"], "reg")
        self.assertEqual(
            self.x[("top", "reg", "", "Core", "core", "r")]["glue_ps"], 44.0
        )
        self.assertIn(("top", "-", "in", "Core", "core", "in"), self.x)

    def test_glue_and_modules(self):
        self.assertEqual(self.p["glue"]["std_um2"], 80.5)
        self.assertEqual(self.p["modules"]["core"], {"module": "Core", "um2": 600.0})


if __name__ == "__main__":
    unittest.main()
