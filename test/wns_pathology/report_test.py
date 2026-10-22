import os
import tempfile
import unittest

import report

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


class ReportTest(unittest.TestCase):
    def test_no_results_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(SystemExit, "run the campaign first"):
                report.report(d)

    def test_missing_arms_are_not_yet_measured(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "facts"))
            src = os.path.join(RESULTS, "facts", "asap7_gcd_gcd.tsv")
            with open(src) as a, open(
                os.path.join(d, "facts", "asap7_gcd_gcd.tsv"), "w"
            ) as b:
                b.write(a.read())
            text, _ = report.report(d)
            self.assertIn("1 flows measured, 1 flagged", text)
            self.assertIn("Not yet measured", text)

    def test_no_endpoint_beyond_what_wns_reports(self):
        # each endpoint is read against its own clock: against the design's
        # main one, an ethmac's 1 ns endpoints sat at 3x a 300 ps clock
        _, designs = report.report(RESULTS)
        endpoints = report.load_endpoints(RESULTS)
        for stem, (_, r) in designs.items():
            if r["reg2reg_min_period"] is None:
                continue
            reported = (r["clock"] - r["wns"]) / r["clock"]
            self.assertLessEqual(max(endpoints[stem]), reported + 1e-3, stem)
        self.assertIn("<polygon", report.ridgeline_svg(designs, endpoints))

    def test_controls_reproduce_the_sweep(self):
        text, designs = report.report(RESULTS)
        self.assertNotIn("**differs**", text)
        self.assertIn("<svg", report.svg(designs))


if __name__ == "__main__":
    unittest.main()
