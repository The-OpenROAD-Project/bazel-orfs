#!/usr/bin/env python3

"""Tests for fleet.py.

The cases that matter are the ones where a plausible implementation would
quietly give a maintainer the wrong impression: one design carrying a
verdict on its own, a trade being reported as a regression, and
`did-not-resolve` being allowed to look like `inert`.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fleet


def v(verdict, improved=(), regressed=(), tied=()):
    return {
        "verdict": verdict,
        "improved": list(improved),
        "regressed": list(regressed),
        "tied": list(tied),
        "missing": [],
        "errors": [],
    }


class Witnesses(unittest.TestCase):
    def test_one_design_alone_never_carries_a_verdict(self):
        got = fleet.score({"a": v("better", improved=["core_area"])})
        self.assertEqual(got["verdict"], "did-not-resolve")
        self.assertIn("core_area", got["unsupported_axes"])

    def test_two_agreeing_designs_resolve(self):
        got = fleet.score(
            {
                "a": v("better", improved=["core_area"]),
                "b": v("better", improved=["core_area"]),
            }
        )
        self.assertEqual(got["verdict"], "better")

    def test_two_designs_on_different_axes_do_not_resolve(self):
        # One witness each on two axes is not two witnesses on either.
        got = fleet.score(
            {
                "a": v("better", improved=["core_area"]),
                "b": v("better", improved=["power"]),
            }
        )
        self.assertEqual(got["verdict"], "did-not-resolve")

    def test_witness_threshold_is_configurable(self):
        verdicts = {
            "a": v("worse", regressed=["period"]),
            "b": v("worse", regressed=["period"]),
        }
        self.assertEqual(fleet.score(verdicts, witnesses=2)["verdict"], "worse")
        self.assertEqual(
            fleet.score(verdicts, witnesses=3)["verdict"], "did-not-resolve"
        )


class Verdicts(unittest.TestCase):
    def test_a_trade_is_not_a_regression(self):
        got = fleet.score(
            {
                "a": v("trade", improved=["core_area"], regressed=["period"]),
                "b": v("trade", improved=["core_area"], regressed=["period"]),
            }
        )
        self.assertEqual(got["verdict"], "trade")

    def test_regression_with_support_is_worse(self):
        got = fleet.score(
            {
                "a": v("worse", regressed=["power"]),
                "b": v("worse", regressed=["power"]),
            }
        )
        self.assertEqual(got["verdict"], "worse")

    def test_hard_violation_escalates_on_one_witness(self):
        # Hard constraints have a measured residual of exactly zero, so a
        # single witness is admissible where it is not for anything else.
        got = fleet.score(
            {"a": {"verdict": "dominated", "improved": [], "regressed": ["core_area"]},
             "b": v("did-not-resolve")}
        )
        self.assertEqual(got["verdict"], "worse")
        self.assertEqual(got["hard_violations"], ["a"])

    def test_nothing_moved_is_unresolved_not_inert(self):
        got = fleet.score({"a": v("did-not-resolve"), "b": v("did-not-resolve")})
        self.assertEqual(got["verdict"], "did-not-resolve")
        self.assertNotEqual(got["verdict"], "inert")

    def test_inert_requires_every_design_bit_identical(self):
        verdicts = {"a": v("did-not-resolve"), "b": v("did-not-resolve")}
        self.assertEqual(
            fleet.score(verdicts, identical=["a", "b"])["verdict"], "inert"
        )
        # A single design left out is enough to lose the claim.
        self.assertEqual(
            fleet.score(verdicts, identical=["a"])["verdict"], "did-not-resolve"
        )

    def test_no_designs_is_not_applicable(self):
        self.assertEqual(fleet.score({})["verdict"], "not-applicable")


class Reporting(unittest.TestCase):
    def test_unresolved_says_it_is_not_evidence_of_no_effect(self):
        text = fleet.render(fleet.score({"a": v("better", improved=["power"])}))
        self.assertIn("NOT the same as no effect", text)

    def test_render_names_the_verdict_first(self):
        text = fleet.render(fleet.score({}))
        self.assertTrue(text.startswith("QoR Pareto score: NOT-APPLICABLE"))


class Cli(unittest.TestCase):
    def run_cli(self, verdicts, extra=()):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, doc in verdicts.items():
                p = os.path.join(d, f"{name}.pareto.json")
                with open(p, "w") as fh:
                    json.dump(doc, fh)
                paths.append(p)
            out = os.path.join(d, "fleet.json")
            rc = fleet.main([*paths, "--out", out, *extra])
            with open(out) as fh:
                return rc, json.load(fh)

    def test_design_name_comes_from_the_filename(self):
        _rc, got = self.run_cli({"sky130hd_gcd": v("did-not-resolve")})
        self.assertEqual(got["designs"], ["sky130hd_gcd"])

    def test_worse_exits_nonzero_and_trade_does_not(self):
        rc, _ = self.run_cli(
            {"a": v("worse", regressed=["power"]), "b": v("worse", regressed=["power"])}
        )
        self.assertEqual(rc, 1)
        rc, _ = self.run_cli(
            {
                "a": v("trade", improved=["core_area"], regressed=["power"]),
                "b": v("trade", improved=["core_area"], regressed=["power"]),
            }
        )
        self.assertEqual(rc, 0, "a trade is a legitimate pull request")

    def test_did_not_resolve_does_not_fail_by_default(self):
        rc, got = self.run_cli({"a": v("did-not-resolve")})
        self.assertEqual(got["verdict"], "did-not-resolve")
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
