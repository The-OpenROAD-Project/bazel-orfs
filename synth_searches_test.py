"""synth_searches.py on a made-up yosys log under ORFS's synth.tcl."""

import io
import os
import sys
import tempfile
import unittest
from unittest import mock

import synth_searches

# (arrival second, line). A share inside synth that merges one pair, an
# extract_fa that makes two full adders and a half adder (and reuses one),
# and an abc whose own headers nest below it.
LOG = [
    (1, "2. Executing SYNTH pass."),
    (2, "2.27. Executing SHARE pass (SAT-based resource sharing)."),
    (2, "Found 3 cells in module Top that may be considered for resource sharing."),
    (2, "  Analyzing resource sharing options for $mul$1 ($mul):"),
    (2, "      New cell: $auto$share.cc:1$9 ($mul)"),
    (2, "Found 2 cells in module Sub that may be considered for resource sharing."),
    (5, "2.28. Executing OPT_SHARE pass."),
    (6, "2.28.1. Executing OPT_EXPR pass."),
    (10, "12. Executing EXTRACT_FA pass (find and extract full/half adders)."),
    (10, "Extracting full/half adders from Top:"),
    (10, "  3-Input XOR/XNOR A B C:"),
    (10, "      Created $fa cell $auto$1."),
    (10, "      Created $fa cell $auto$2."),
    (10, "      Reusing $fa cell $auto$2."),
    (10, "  2-Input XOR/XNOR A B:"),
    (10, "      Created $fa cell $auto$3."),
    (17, "13. Executing TECHMAP pass (map to technology primitives)."),
    (17, "      New cell: not in share"),
    (20, "20. Executing ABC pass (technology mapping using ABC)."),
    (21, "20.1. Extracting gate netlist of module `Top' to `/x/input.blif'.."),
    (60, "20.1.2. Re-integrating ABC results."),
    (62, "21. Executing SPLITNETS pass."),
    (63, "End of script."),
]


def run(log, end):
    s = synth_searches.Searches()
    for t, line in log:
        s.feed((line + "\n").encode(), t)
    s.end(end)
    return s.lines()


class SynthSearchesTest(unittest.TestCase):
    def test_yields_and_wall_seconds(self):
        self.assertEqual(
            run(LOG, 64),
            [
                "search extract_fa seconds=7.0 full=2 half=1",
                "search share seconds=3.0 candidates=5 merged=1",
                "search abc seconds=42.0",
                "pass 20 abc seconds=42.0",
                "pass 12 extract_fa seconds=7.0",
                "pass 2.28.1 opt_expr seconds=4.0",
                "pass 2.27 share seconds=3.0",
                "pass 13 techmap seconds=3.0",
                "pass 21 splitnets seconds=2.0",
                "pass 2 synth seconds=1.0",
                "pass 2.28 opt_share seconds=1.0",
            ],
        )

    def test_slowest_passes_only(self):
        log = [(i, f"{i}. Executing OPT pass.") for i in range(1, 13)]
        lines = run(log, 13)
        self.assertEqual(len(lines), synth_searches.SLOWEST_PASSES)

    def test_passes_that_did_not_run_have_no_line(self):
        log = [(1, "5. Executing OPT pass.")]
        self.assertEqual(run(log, 2), ["pass 5 opt seconds=1.0"])

    def test_last_pass_ends_with_the_output(self):
        log = [
            (1, "9. Executing ABC_NEW pass."),
            (2, "9.1. Executing ABC9 pass."),
            (3, "9.1.1. Executing ABC9_OPS pass."),
        ]
        self.assertEqual(
            run(log, 11),
            [
                "search abc seconds=10.0",
                "pass 9.1.1 abc9_ops seconds=8.0",
                "pass 9 abc_new seconds=1.0",
                "pass 9.1 abc9 seconds=1.0",
            ],
        )

    def test_main(self):
        text = "".join(line + "\n" for _, line in LOG).encode()
        stdin = mock.Mock(buffer=io.BytesIO(text))
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "searches.txt")
            with mock.patch.object(sys, "stdin", stdin):
                synth_searches.main([out])
            with open(out) as f:
                written = f.read().splitlines()
        self.assertEqual(
            [w.split()[1] for w in written if w.startswith("search ")],
            ["extract_fa", "share", "abc"],
        )
        self.assertIn("full=2 half=1", written[0])


if __name__ == "__main__":
    unittest.main()
