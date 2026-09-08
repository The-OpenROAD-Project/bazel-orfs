"""Tests for the inventory's parsing and arithmetic.

Only the analysis math is tested here, not ORFS's files: those change on
a bump, and a test asserting their contents would fail for the right
reason at the wrong time. What is pinned is the behaviour that, when
wrong, produces a plausible answer instead of an error.
"""

import unittest

import inventory


class TclFlagsTest(unittest.TestCase):
    """The regression that motivated the tokenizer.

    The first version matched `-layer <name> -resistance <value>` with a
    regex. That works on asap7 and silently matches nothing on a platform
    writing the same flags in another order, yielding an empty layer
    table that reads exactly like a platform with no RC data.
    """

    def test_flag_order_does_not_matter(self):
        forward = inventory._tcl_flags(" -layer M2 -resistance 1.5 -capacitance 2.5")
        reversed_ = inventory._tcl_flags(" -capacitance 2.5 -resistance 1.5 -layer M2")
        self.assertEqual(forward, reversed_)
        self.assertEqual(forward["layer"], "M2")

    def test_valueless_flag_is_true(self):
        flags = inventory._tcl_flags(" -signal -layer met1")
        self.assertIs(flags["signal"], True)
        self.assertEqual(flags["layer"], "met1")


class ParseSetLayerRcTest(unittest.TestCase):
    def _write(self, text):
        import tempfile
        from pathlib import Path

        path = Path(tempfile.mkdtemp()) / "setRC.tcl"
        path.write_text(text)
        return path

    def test_via_rows_are_not_routing_layers(self):
        path = self._write(
            "set_layer_rc -layer M1 -resistance 0.07 -capacitance 1e-10\n"
            "set_layer_rc -layer M2 -resistance 0.03 -capacitance 0.17\n"
            "set_layer_rc -via V1 -resistance 0.0172\n"
            "set_wire_rc -signal -resistance 0.0265 -capacitance 0.165\n"
        )
        layers, wire_rc = inventory.parse_set_layer_rc(path)
        self.assertEqual([layer["layer"] for layer in layers], ["M1", "M2"])
        self.assertEqual(len(wire_rc), 1)
        self.assertEqual(wire_rc[0]["kind"], "absolute")

    def test_commented_lines_are_ignored(self):
        path = self._write(
            "# set_layer_rc -layer M9 -resistance 0.001\n"
            "set_layer_rc -layer M1 -resistance 0.07\n"
            "set_wire_rc -signal -layer M1\n"
        )
        layers, wire_rc = inventory.parse_set_layer_rc(path)
        self.assertEqual([layer["layer"] for layer in layers], ["M1"])
        self.assertEqual(wire_rc[0]["kind"], "layer")


class MakefileExportsTest(unittest.TestCase):
    def test_inline_comment_is_stripped_but_make_call_is_not(self):
        import tempfile
        from pathlib import Path

        path = Path(tempfile.mkdtemp()) / "config.mk"
        path.write_text(
            "export MAX_ROUTING_LAYER ?= M7 # cap\n"
            "export PDN_TCL = $(PLATFORM_DIR)/pdn.tcl\n"
        )
        got = inventory.parse_makefile_exports(path)
        self.assertEqual(got["MAX_ROUTING_LAYER"]["value"], "M7")
        self.assertEqual(got["MAX_ROUTING_LAYER"]["op"], "?=")
        self.assertEqual(got["PDN_TCL"]["value"], "$(PLATFORM_DIR)/pdn.tcl")


class SpreadTest(unittest.TestCase):
    LAYERS = [
        {"layer": "M1", "resistance": 0.08, "capacitance": None},
        {"layer": "M2", "resistance": 0.04, "capacitance": None},
        {"layer": "M3", "resistance": 0.02, "capacitance": None},
        {"layer": "M4", "resistance": 0.01, "capacitance": None},
    ]

    def test_ratio_is_max_over_min(self):
        spread = inventory.resistance_spread(self.LAYERS)
        self.assertAlmostEqual(spread["ratio"], 8.0)
        self.assertEqual(spread["bottom"], "M1")
        self.assertEqual(spread["top"], "M4")

    def test_routable_window_is_inclusive(self):
        window = inventory.routable_window(self.LAYERS, "M2", "M3")
        self.assertEqual([layer["layer"] for layer in window], ["M2", "M3"])

    def test_routable_window_falls_back_to_the_whole_stack(self):
        # An unset MIN/MAX must not silently yield an empty window: that
        # would report "no routable layers" as a spread of None.
        window = inventory.routable_window(self.LAYERS, None, None)
        self.assertEqual(len(window), len(self.LAYERS))

    def test_window_spread_is_narrower_than_the_full_stack(self):
        full = inventory.resistance_spread(self.LAYERS)
        window = inventory.resistance_spread(
            inventory.routable_window(self.LAYERS, "M2", "M3")
        )
        self.assertLess(window["ratio"], full["ratio"])


class MispricingTest(unittest.TestCase):
    LAYERS = SpreadTest.LAYERS

    def test_absolute_constant_is_priced_against_the_window(self):
        window = inventory.routable_window(self.LAYERS, "M2", "M4")
        wire_rc = [{"kind": "absolute", "resistance": "0.04", "signal": True,
                    "clock": False}]
        got = inventory.wire_rc_mispricing(self.LAYERS, wire_rc, window)
        # 0.04 against a window whose cheapest layer is M4 at 0.01.
        self.assertAlmostEqual(
            got[0]["mispricing"]["times_more_resistive_than_least"], 4.0
        )
        self.assertEqual(
            got[0]["mispricing"]["least_resistive_routable_layer"], "M4"
        )

    def test_widening_the_window_worsens_the_mispricing(self):
        """The study's claim, as arithmetic.

        A design that raises MAX_ROUTING_LAYER gains access to less
        resistive layers, so the one constant it is still charged sits
        further from what it could have had.
        """
        wire_rc = [{"kind": "absolute", "resistance": "0.04", "signal": True,
                    "clock": False}]
        narrow = inventory.wire_rc_mispricing(
            self.LAYERS, wire_rc, inventory.routable_window(self.LAYERS, "M2", "M3")
        )
        wide = inventory.wire_rc_mispricing(
            self.LAYERS, wire_rc, inventory.routable_window(self.LAYERS, "M2", "M4")
        )
        self.assertGreater(
            wide[0]["mispricing"]["times_more_resistive_than_least"],
            narrow[0]["mispricing"]["times_more_resistive_than_least"],
        )

    def test_naming_a_layer_has_nothing_to_misprice(self):
        window = inventory.routable_window(self.LAYERS, "M2", "M4")
        wire_rc = [{"kind": "layer", "layer": "M2", "signal": True, "clock": False}]
        got = inventory.wire_rc_mispricing(self.LAYERS, wire_rc, window)
        self.assertIsNone(got[0]["mispricing"])


if __name__ == "__main__":
    unittest.main()
