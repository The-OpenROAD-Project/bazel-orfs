"""compare.py on endpoint files written by hand."""

import os
import subprocess
import sys
import tempfile
import unittest

import compare


def tsv(rows):
    f = tempfile.NamedTemporaryFile(
        "w", suffix=".tsv", delete=False, dir=os.environ.get("TEST_TMPDIR")
    )
    f.write("".join("%s\t%s\n" % r for r in rows))
    f.close()
    return f.name


class CompareTest(unittest.TestCase):
    def test_a_kept_and_a_flattened_register_are_one(self):
        ends = compare.read(tsv([("riscv/dp/rf/q[0]/D", "800.0")]))
        self.assertEqual(ends, {"riscv.dp.rf.q[0].D": 800.0})

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(ValueError):
            compare.read(tsv([]))

    def test_the_band_counts_faster_and_slower(self):
        control = {"a": 1000.0, "b": 950.0, "c": 500.0, "d": 920.0}
        other = {"a": 900.0, "b": 960.0, "c": 400.0, "e": 1.0}
        # c is far below the band in both; d and e are in one run only
        self.assertEqual(compare.compare(control, other), (1, 1, 100.0, 10.0, 2))

    def test_eps_in_another_unit(self):
        control = {"a": 2.000, "b": 1.900}
        other = {"a": 1.9995, "b": 1.950}
        faster, slower, gain, loss, unmatched = compare.compare(
            control, other, eps=0.001
        )
        self.assertEqual((faster, slower, gain, unmatched), (0, 1, 0.0, 0))
        self.assertAlmostEqual(loss, 0.05)

    def test_the_table(self):
        c = tsv([("a", "1000.0"), ("b", "950.0")])
        o = tsv([("a", "900.0"), ("b", "960.0")])
        out = subprocess.run(
            [
                sys.executable,
                compare.__file__,
                "--clock",
                "950",
                "control=" + c,
                "other=" + o,
            ],
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.decode()
        self.assertIn("| control | 1000.0 ps (105.3 % of 950)", out)
        self.assertIn("| other | 960.0 ps | -4.0 % | 1 | 1 |", out)


if __name__ == "__main__":
    unittest.main()
