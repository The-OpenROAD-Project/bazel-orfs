"""The study's log and KPI parsers read what OpenROAD and kpi_run.tcl write."""

import contextlib
import io
import os
import tempfile
import unittest

import td_share
import xs_table

GPL_LOG = """\
[    0.100] [INFO GPL-0002] DBU: 1000
[    5.000] [INFO GPL-0100] Timing-driven iteration 1/2, virtual: false.
[    5.001] [INFO GPL-0101]    Iter: 300, overflow: 0.633, keep resizer changes at: 1, HPWL: 1
[    5.002] [INFO RSZ-9901] findResizeSlacks repair_design: 2.000 s
[    7.500] [INFO GPL-9911] Timing-driven slacks from rsz: 2.499 s
[    7.501] [INFO GPL-0106] Timing-driven: worst slack 1e-10
[   20.000] [INFO GPL-0100] Timing-driven iteration 2/2, virtual: true.
[   20.001] [INFO GPL-0101]    Iter: 600, overflow: 0.194, keep resizer changes at: 0.3, HPWL: 1
[   20.501] [INFO GPL-9911] Timing-driven slacks from sta: 0.500 s
[   20.502] [INFO GPL-0106] Timing-driven: worst slack -2e-10
[   30.000] [INFO GPL-0003] SiteSize: 1
Elapsed time: 0:31.25[h:]min:sec. CPU time: user 1 sys 1 (99%). Peak memory: 1KB.
"""

KPI = """\
reg2reg       200 ps  a -> b
reg2reg endpoints bin 10 ps from 30 ps: 1 2 3
reg2reg min period 1800 ps
"""


def _write(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False)
    f.write(text)
    f.close()
    return f.name


class ParsersTest(unittest.TestCase):
    def test_reweights_timed_from_0101_to_0106(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            td_share.summarise("x", _write(GPL_LOG))
        text = out.getvalue()
        self.assertIn("2 re-weights 3.0 s", text)
        self.assertIn("overflow 0.633, virtual false: 2.5 s", text)
        self.assertIn("overflow 0.194, virtual true: 0.5 s", text)

    def test_reweight_sum_from_9911(self):
        self.assertAlmostEqual(xs_table.reweights(_write(GPL_LOG)), 2.999)

    def test_elapsed_prefers_closing_line(self):
        self.assertAlmostEqual(xs_table.elapsed(_write(GPL_LOG)), 31.25)

    def test_elapsed_hours(self):
        log = _write("Elapsed time: 1:02:03.50[h:]min:sec.\n")
        self.assertAlmostEqual(xs_table.elapsed(log), 3723.5)

    def test_period(self):
        self.assertEqual(xs_table.period(_write(KPI)), 1800.0)

    def test_missing_is_none(self):
        self.assertIsNone(xs_table.period(os.path.join(tempfile.gettempdir(), "no")))


if __name__ == "__main__":
    unittest.main()
