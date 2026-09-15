#!/usr/bin/env python3
"""Unit tests for the pin activity audit.

The audit exists to catch a silent failure, so whether it actually
catches it is worth asserting rather than trusting. Every fatal class
gets a test that it fails, and every benign class a test that it does
not: a classifier that quietly buckets an unmeasured internal pin as
"clock network" would turn the study's central claim into a formality.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from classify_pins import (  # noqa: E402
    audit,
    classify,
    driver_nets,
    read_annotation,
    read_pins,
)

HEADER = [
    "path",
    "kind",
    "cell",
    "master_type",
    "port",
    "direction",
    "sig_type",
    "net",
    "net_sig_type",
    "net_special",
]


def pin(
    path,
    kind="iterm",
    cell="INVx1_ASAP7_75t_R",
    master_type="CORE",
    port="A",
    direction="INPUT",
    sig_type="SIGNAL",
    net="n1",
    net_sig_type="SIGNAL",
    net_special="0",
):
    return dict(
        zip(
            HEADER,
            [
                path,
                kind,
                cell,
                master_type,
                port,
                direction,
                sig_type,
                net,
                net_sig_type,
                net_special,
            ],
        )
    )


def write(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


class ReadPinsTest(unittest.TestCase):
    def test_columns_are_keyed_by_the_header(self):
        path = write(
            "\t".join(HEADER)
            + "\n"
            + "_1_/A\titerm\tINVx1\tCORE\tA\tINPUT\tSIGNAL\tn1\tSIGNAL\t0\n"
        )
        pins = read_pins(path)
        self.assertEqual("INVx1", pins["_1_/A"]["cell"])
        self.assertEqual("n1", pins["_1_/A"]["net"])

    def test_a_short_row_is_an_error_rather_than_a_shifted_column(self):
        """A tab inside a field would silently move every column after it."""
        path = write("\t".join(HEADER) + "\n" + "_1_/A\titerm\tINVx1\n")
        with self.assertRaises(ValueError):
            read_pins(path)


class ReadAnnotationTest(unittest.TestCase):
    LISTING = (
        "saif         1234\n"
        "unannotated     3\n"
        "Annotated pins:\n"
        " saif _1_/A\n"
        " saif _2_/ZN\n"
        "Unannotated pins:\n"
        " _3_/A\n"
        " _4_/ZN\n"
    )

    def test_both_listings_are_read(self):
        annotated, unannotated = read_annotation(write(self.LISTING))
        self.assertEqual({"_1_/A": "saif", "_2_/ZN": "saif"}, annotated)
        self.assertEqual(["_3_/A", "_4_/ZN"], unannotated)

    def test_the_summary_counts_are_not_used(self):
        """OpenSTA's `unannotated` summary is computed over two pin sets
        that filter power/ground differently, in unsigned arithmetic. The
        listing says three; there are two. The listing wins."""
        annotated, unannotated = read_annotation(write(self.LISTING))
        self.assertEqual(2, len(unannotated))


class ClassifyTest(unittest.TestCase):
    POLICY = {
        "scan_patterns": ["^SE$"],
        "waivers": [{"pattern": "^_99_/", "reason": "a written reason"}],
    }

    def classify_one(self, p, policy=None, tied=None):
        return classify(
            p["path"], p, tied or set(), policy if policy is not None else self.POLICY
        )

    def test_an_internal_cell_pin_is_the_fatal_catch_all(self):
        self.assertEqual("internal_cell_pin", self.classify_one(pin("_1_/A")))

    def test_a_clock_network_pin_is_benign(self):
        """OpenSTA gives it 2/period from the SDC, bypassing the estimator."""
        self.assertEqual(
            "clock_network", self.classify_one(pin("_1_/A", net_sig_type="CLOCK"))
        )

    def test_a_pin_on_a_tieoff_net_is_constant(self):
        self.assertEqual(
            "tied_constant", self.classify_one(pin("_1_/A", net_sig_type="TIEOFF"))
        )

    def test_a_pin_driven_by_a_tie_cell_is_constant(self):
        """The net does not always carry TIEOFF, so the driver is looked up."""
        self.assertEqual(
            "tied_constant",
            self.classify_one(pin("_1_/A", net="tie_net"), tied={"tie_net"}),
        )

    def test_an_unconnected_pin_is_benign(self):
        self.assertEqual("unconnected", self.classify_one(pin("_1_/A", net="")))

    def test_a_power_pin_is_benign(self):
        self.assertEqual(
            "power_ground",
            self.classify_one(pin("_1_/VDD", sig_type="POWER", net_sig_type="POWER")),
        )

    def test_a_top_input_port_is_fatal(self):
        """It is a levelization root: the default activity enters here."""
        self.assertEqual(
            "top_port",
            self.classify_one(
                pin("reset", kind="bterm", direction="INPUT", cell="", master_type="")
            ),
        )

    def test_a_top_output_port_is_benign(self):
        """It is downstream of a root and seeds nothing."""
        self.assertEqual(
            "top_port_output",
            self.classify_one(
                pin("done", kind="bterm", direction="OUTPUT", cell="", master_type="")
            ),
        )

    def test_a_macro_pin_is_fatal(self):
        """An unannotated SRAM is memory energy invented rather than measured."""
        self.assertEqual(
            "macro_pin",
            self.classify_one(pin("ram/CE", master_type="BLOCK", cell="fakeram_32x32")),
        )

    def test_a_scan_pin_is_benign_when_the_design_says_so(self):
        self.assertEqual("scan_test", self.classify_one(pin("_1_/SE", port="SE")))

    def test_a_waiver_needs_a_pattern_and_moves_the_pin_out_of_fatal(self):
        self.assertEqual("waived", self.classify_one(pin("_99_/A")))

    def test_a_pin_openroad_printed_but_the_odb_does_not_have_is_fatal(self):
        """A join failure hides whatever the pin really was."""
        self.assertEqual("unmatched", classify("_5_/A", None, set(), self.POLICY))


class DriverNetsTest(unittest.TestCase):
    def test_tie_cell_outputs_name_their_nets(self):
        pins = {
            "_1_/Y": pin(
                "_1_/Y",
                master_type="CORE_TIEHIGH",
                port="Y",
                direction="OUTPUT",
                net="tie_hi",
            ),
            "_2_/A": pin("_2_/A", net="tie_hi"),
        }
        self.assertEqual({"tie_hi"}, driver_nets(pins))


class AuditTest(unittest.TestCase):
    DESIGN = {"design": "cmj_x", "stage": "5_1_grt", "pin_count": 4}

    def run_audit(self, pins, annotated, unannotated, policy=None):
        return audit(
            pins,
            annotated,
            unannotated,
            self.DESIGN,
            policy if policy is not None else {},
        )

    def test_a_fully_annotated_design_passes(self):
        pins = {"_1_/A": pin("_1_/A")}
        result = self.run_audit(pins, {"_1_/A": "saif"}, [])
        self.assertEqual("pass", result["verdict"])
        self.assertEqual(1.0, result["annotated_fraction"])

    def test_one_unannotated_internal_pin_fails(self):
        pins = {"_1_/A": pin("_1_/A")}
        result = self.run_audit(pins, {}, ["_1_/A"])
        self.assertEqual("fail", result["verdict"])
        self.assertEqual(1, result["unannotated_by_class"]["internal_cell_pin"])

    def test_a_declared_budget_lets_a_stated_number_through(self):
        pins = {"_1_/A": pin("_1_/A")}
        result = self.run_audit(
            pins, {}, ["_1_/A"], {"max_unannotated_internal": 1}
        )
        self.assertEqual("pass", result["verdict"])

    def test_a_budget_does_not_excuse_an_unannotated_input_port(self):
        """The budget is for internal pins. A root is a different failure."""
        pins = {
            "reset": pin("reset", kind="bterm", direction="INPUT"),
        }
        result = self.run_audit(
            pins, {}, ["reset"], {"max_unannotated_internal": 1000}
        )
        self.assertEqual("fail", result["verdict"])

    def test_an_unmatched_pin_fails_by_default(self):
        """A name that does not join hides whatever the pin really was."""
        result = self.run_audit({}, {}, ["_5_/A"])
        self.assertEqual("fail", result["verdict"])
        self.assertEqual(1, result["unannotated_by_class"]["unmatched"])

    def test_a_declared_unmatched_fraction_lets_a_small_share_through(self):
        pins = dict(("_{}_/A".format(i), pin("_{}_/A".format(i))) for i in range(99))
        annotated = dict((p, "saif") for p in pins)
        result = self.run_audit(
            pins, annotated, ["gone/A"], {"max_unmatched_fraction": 0.02}
        )
        self.assertEqual("pass", result["verdict"])
        self.assertAlmostEqual(0.01, result["unmatched_fraction"])

    def test_the_fraction_is_of_the_whole_listed_pin_set(self):
        """A count would say nothing about whether it is small."""
        result = self.run_audit({}, {}, ["gone/A"], {"max_unmatched_fraction": 1.0})
        self.assertEqual(1.0, result["unmatched_fraction"])

    def test_a_fraction_over_budget_fails(self):
        pins = dict(("_{}_/A".format(i), pin("_{}_/A".format(i))) for i in range(9))
        annotated = dict((p, "saif") for p in pins)
        result = self.run_audit(
            pins, annotated, ["gone/A"], {"max_unmatched_fraction": 0.05}
        )
        self.assertEqual("fail", result["verdict"])

    def test_the_unmatched_budget_does_not_excuse_an_internal_pin(self):
        pins = {"_1_/A": pin("_1_/A")}
        result = self.run_audit(pins, {}, ["_1_/A"], {"max_unmatched_fraction": 1.0})
        self.assertEqual("fail", result["verdict"])

    def test_benign_classes_do_not_fail_the_audit(self):
        pins = {
            "_1_/A": pin("_1_/A", net_sig_type="CLOCK"),
            "_2_/A": pin("_2_/A", net=""),
            "_3_/VDD": pin("_3_/VDD", sig_type="POWER", net_sig_type="POWER"),
        }
        result = self.run_audit(pins, {}, ["_1_/A", "_2_/A", "_3_/VDD"])
        self.assertEqual("pass", result["verdict"])
        self.assertEqual(0, result["fatal_count"])

    def test_the_origin_breakdown_is_carried_through(self):
        pins = {"_1_/A": pin("_1_/A"), "_2_/A": pin("_2_/A")}
        result = self.run_audit(pins, {"_1_/A": "saif", "_2_/A": "user"}, [])
        self.assertEqual({"saif": 1, "user": 1}, result["annotated_by_origin"])

    def test_the_result_is_json_serialisable(self):
        """It is committed as a fixture and read by the report."""
        pins = {"_1_/A": pin("_1_/A")}
        result = self.run_audit(pins, {"_1_/A": "saif"}, [])
        json.loads(json.dumps(result))


if __name__ == "__main__":
    unittest.main()
