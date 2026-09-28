"""report.py renders records, marks missing arms, refuses no records."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report  # noqa: E402


def record(**over):
    r = {
        "slew_viol": 1117,
        "cap_viol": 3,
        "fanout_viol": 0,
        "long_nets": 32,
        "period_ps": 2485.9,
        "worst_stage_share": 0.058,
        "kept": ["MainBtb", "WriteBuffer_4"],
        "kept_expected": ["WriteBuffer_4", "MainBtb"],
    }
    r.update(over)
    return r


class ReportTest(unittest.TestCase):
    def render(self, records, arms):
        with tempfile.TemporaryDirectory() as d:
            for name, r in records.items():
                json.dump(r, open(os.path.join(d, name + ".json"), "w"))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                report.main(["report.py", d] + arms)
            return out.getvalue()

    def test_row_values_and_kept(self):
        out = self.render({"B1": record()}, ["B1=base"])
        self.assertIn("| base | 1,117 | 3 | 0 | 32 | 2,486 | 6% | yes |", out)

    def test_kept_mismatch_is_no(self):
        out = self.render({"B1": record(kept=["MainBtb"])}, ["B1"])
        self.assertTrue(out.rstrip().endswith("| no |"))

    def test_missing_arm_is_not_yet_measured(self):
        out = self.render({"B1": record()}, ["B1", "A2"])
        self.assertIn("| A2 | not yet measured |", out)

    def test_no_records_refuses(self):
        with self.assertRaises(SystemExit):
            self.render({}, ["B1"])


if __name__ == "__main__":
    unittest.main()
