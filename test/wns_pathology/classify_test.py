import unittest

from classify import classify, parse

# gcd at 220 ps as in ORFS #4583: an output's 20 % budget sets WNS
GCD = """clock.core_clock\t220
reg2reg.slack\t-5
reg2reg.capture\tcore_clock
reg2reg.to\tctrl/state_reg/D
reg2out.slack\t-30
reg2out.from\tdpath/a_reg/CLK
reg2out.to\tresp_msg[13]
reg2out.delay\t200
reg2out.pin_wire\t20
worst.launch\tcore_clock
worst.capture\tcore_clock
worst.macro\t0
wns\t-30
reg2reg.top10\t225 224 223 222 221 220 219 218 217 216
instances\t500
hold.buffers\t0
hold.sampled\t0
hold.from_input\t0
floor\t120
check_setup.ran\t1
"""


def flags(text):
    return classify(parse(text))["flags"]


class ClassifyTest(unittest.TestCase):
    def test_io_budget_sets_wns(self):
        out = classify(parse(GCD))
        self.assertEqual(out["flags"], ["P1"])
        self.assertEqual(out["worst_group"], "reg2out")
        self.assertEqual(out["reg2reg_min_period"], 225)

    def test_healthy_design_has_no_flags(self):
        self.assertEqual(
            flags(GCD.replace("reg2out.slack\t-30", "reg2out.slack\t-6")), []
        )

    def test_pin_wire(self):
        self.assertIn("P2", flags(GCD.replace("pin_wire\t20", "pin_wire\t60")))

    def test_outlier(self):
        text = GCD.replace("225 224", "260 224")
        self.assertIn("P4", flags(text))

    def test_floor(self):
        self.assertIn("P5", flags(GCD.replace("floor\t120", "floor\t220")))

    def test_slack_rich(self):
        text = GCD.replace("reg2reg.slack\t-5", "reg2reg.slack\t60").replace(
            "wns\t-30", "wns\t0"
        )
        self.assertIn("P7", flags(text))

    def test_out_of_reach(self):
        self.assertIn(
            "P8", flags(GCD.replace("reg2reg.slack\t-5", "reg2reg.slack\t-80"))
        )

    def test_unseen_registers(self):
        out = classify(parse(GCD + "check_setup.unclocked_register/latch_pins\t12\n"))
        self.assertIn("P3", out["flags"])
        self.assertIn("12", out["evidence"]["P3"])

    def test_ports_without_delays_are_not_unseen(self):
        text = GCD + "check_setup.Warning:_unconstrained_input_ports\t65\n"
        self.assertNotIn("P3", flags(text))
        text += "check_setup.Warning:_unconstrained_endpoints\t995\n"
        self.assertNotIn("P3", flags(text))
        text += "check_setup.unconstrained_register_pins\t990\n"
        self.assertIn("P3", flags(text))

    def test_counted_zero_is_no_flag(self):
        self.assertNotIn(
            "P3", flags(GCD + "check_setup.unconstrained_register_pins\t0\n")
        )

    def test_macro_and_cross_clock(self):
        text = GCD.replace("worst.macro\t0", "worst.macro\t1").replace(
            "worst.launch\tcore_clock", "worst.launch\tother"
        )
        self.assertEqual(flags(text)[-2:], ["P6", "P9"])

    def test_hold_infestation_needs_inputs(self):
        text = GCD.replace("hold.buffers\t0", "hold.buffers\t100").replace(
            "hold.sampled\t0", "hold.sampled\t100"
        )
        self.assertNotIn("P10", flags(text))
        self.assertIn("P10", flags(text.replace("from_input\t0", "from_input\t90")))

    def test_no_reg2reg(self):
        text = "\n".join(l for l in GCD.splitlines() if not l.startswith("reg2reg."))
        self.assertIn("P0", flags(text))

    def test_virtual_io_clock_is_not_a_crossing(self):
        text = GCD.replace("worst.capture\tcore_clock", "worst.capture\tvclk")
        self.assertIn("P9", flags(text))
        self.assertNotIn("P9", flags(text + "virtual.vclk\t1\n"))

    def test_check_setup_must_have_run(self):
        with self.assertRaises(ValueError):
            classify(parse(GCD.replace("check_setup.ran\t1\n", "")))

    def test_no_clock_refuses(self):
        with self.assertRaises(ValueError):
            classify(parse("wns\t0\n"))


if __name__ == "__main__":
    unittest.main()
