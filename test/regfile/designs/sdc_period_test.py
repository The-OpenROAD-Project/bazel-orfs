import unittest

from sdc_period import with_period


class WithPeriodTest(unittest.TestCase):
    def test_set_clk_period(self):
        got = with_period(
            "set clk_period 950\ncreate_clock -period $clk_period\n", "800"
        )
        self.assertEqual(got, "set clk_period 800\ncreate_clock -period $clk_period\n")

    def test_literal_period(self):
        got = with_period(
            "create_clock -name core_clock -period 600 [get_ports {clock}]\n", "450"
        )
        self.assertEqual(
            got, "create_clock -name core_clock -period 450 [get_ports {clock}]\n"
        )

    def test_none_stops(self):
        with self.assertRaises(ValueError):
            with_period("create_clock -name c [get_ports clk]\n", "1")

    def test_two_stop(self):
        with self.assertRaises(ValueError):
            with_period("set clk_period 1\nset clk_period 2\n", "3")


if __name__ == "__main__":
    unittest.main()
