"""tinyRocket-regfile's inventory: rocket_rf is a register file in place
of Rocket._T_288, and no entry for the array itself is left."""

import json
import sys
import unittest

PATH = sys.argv.pop(1)


class SeamTest(unittest.TestCase):
    def setUp(self):
        with open(PATH) as f:
            self.memories = {m["name"]: m for m in json.load(f)["memories"]}

    def test_register_file_in_the_arrays_place(self):
        rf = self.memories["rocket_rf"]
        self.assertEqual("regfile", rf["kind"])
        self.assertIn("in place of Rocket._T_288", rf["reason"])
        self.assertEqual((32, 32, 2, 1), (rf["rows"], rf["bits"], rf["read_ports"], rf["write_ports"]))

    def test_the_array_is_not_left_as_flops(self):
        self.assertNotIn("Rocket._T_288", self.memories)


if __name__ == "__main__":
    unittest.main()
