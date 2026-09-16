#!/usr/bin/env python3
"""auto_period_all: every round builds only the designs still walking, each steps on its own slack."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auto_period_all as apa  # noqa: E402

SDC = "set clk_name clk\nset clk_period {}\n"


def probe(period, wns):
    return "period_ps {}\nwns_reg2reg_ps {}\nreg2reg_paths_returned 8\n".format(
        period, wns
    )


class AutoPeriodAllTest(unittest.TestCase):
    def test_two_designs_walk_independently_and_rounds_shrink(self):
        with tempfile.TemporaryDirectory() as d:
            specs = []
            for name, start in [("a", 1000), ("b", 2000)]:
                sdc = os.path.join(d, name + ".sdc")
                with open(sdc, "w") as f:
                    f.write(SDC.format(start))
                specs.append(
                    "{}:{}:{}:{}:{}".format(
                        name,
                        sdc,
                        "//x:" + name,
                        os.path.join(d, name + ".txt"),
                        os.path.join(d, name + ".json"),
                    )
                )
            designs = [apa.Design(s) for s in specs]
            rounds = []

            # a closes with 100 ps of slack then converges; b never has slack
            # to give, so it converges in round one and drops out.
            def read(active):
                rounds.append([x.name for x in active])
                out = []
                for x in active:
                    if x.name == "a":
                        out.append(probe(x.period, 100.0 if x.period == 1000 else 1.0))
                    else:
                        out.append(probe(x.period, 0.5))
                return out

            apa.derive_all(designs, read)
            self.assertEqual(rounds, [["a", "b"], ["a"]])
            a, b = designs
            self.assertEqual((a.winner, a.status), (900, "converged"))
            self.assertEqual((b.winner, b.status), (2000, "converged"))
            with open(a.constraints) as f:
                self.assertIn("set clk_period 900", f.read())

    def test_winner_is_pinned_even_after_overshoot(self):
        with tempfile.TemporaryDirectory() as d:
            sdc = os.path.join(d, "c.sdc")
            with open(sdc, "w") as f:
                f.write(SDC.format(1000))
            c = apa.Design(
                "c:{}://x:c:{}:{}".format(
                    sdc, os.path.join(d, "c.txt"), os.path.join(d, "c.json")
                )
            )

            # The label keeps its colon; the paths either side are whole.
            self.assertEqual(c.target, "//x:c")
            self.assertEqual(c.artifact, os.path.join(d, "c.txt"))
            self.assertEqual(c.evidence, os.path.join(d, "c.json"))

            def read(active):
                # 1000 closes with 50 ps; 950 fails: overshot, winner 1000.
                return [
                    probe(x.period, 50.0 if x.period == 1000 else -3.0) for x in active
                ]

            apa.derive_all([c], read)
            self.assertEqual((c.winner, c.status), (1000, "overshot"))
            with open(sdc) as f:
                self.assertIn("set clk_period 1000", f.read())


if __name__ == "__main__":
    unittest.main()
