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


# Core.q drives Vec.d through two inverters, Core.w drives Vec.w by wire,
# Mem.r ends at a register that drives Core.r, the top's input in drives
# Core.in and Core.q also leaves at the top's output out.
GRAPH = """parent\ttop
glue\t10.0
key\tm1\tcore\tCore
key\tm2\tvec\tVec
key\tm3\tmem\tMem
bit\tm1\tq\tq[0]\toutput\t1\t50.0
bit\tm1\tq\tq[1]\toutput\t2\t40.0
bit\tm2\td\td[0]\tinput\t4\t90.0
bit\tm2\td\td[1]\tinput\t6\t80.0
bit\tm1\tw\tw\toutput\t7\t0.0
bit\tm2\tw\tw\tinput\t7\t0.0
bit\tm3\tr\tr\toutput\t8\t0.0
bit\tm1\tr\tr\tinput\t9\t30.0
bit\tm1\tin\tin\tinput\t10\t0.0
port\tin\tinput\t10
port\tout\toutput\t1
cell\tcomb\t1\t3
cell\tcomb\t3\t4
cell\tcomb\t2\t5
cell\tcomb\t5\t6
cell\treg\t8\t9
""".splitlines()


class GraphTest(unittest.TestCase):
    def test_search(self):
        p = parent_json.build(GRAPH, "0")
        x = {
            (c["a"], c["a_bus"], c["b"], c["b_bus"]): (
                c["a_bits"],
                c["b_bits"],
                c["via"],
                c["depth"],
                c["glue_ps"],
            )
            for c in p["crossings"]
        }
        self.assertEqual(
            x,
            {
                ("Core", "q", "Vec", "d"): (2, 2, "comb", 2, 40.0),
                ("Core", "w", "Vec", "w"): (1, 1, "wire", 0, 0.0),
                ("Core", "q", "top", "out"): (2, 1, "wire", 0, 0.0),
                ("Mem", "r", "top", ""): (1, 1, "reg", 0, 0.0),
                ("top", "", "Core", "r"): (1, 1, "reg", 0, 30.0),
                ("top", "in", "Core", "in"): (1, 1, "wire", 0, 0.0),
            },
        )


if __name__ == "__main__":
    unittest.main()
