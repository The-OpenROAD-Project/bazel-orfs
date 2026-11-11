"""Detailed placement of a register file's own flow needs no recovery.

The cells left to placement go to the band of rows around generate_ram's
FIRM array, so the negotiation legalizer converges in phase 1 and leaves
no cell to the diamond search (DPL-0700, DPL-0702, DPL-0704) and none
illegal (DPL-0701).
"""

import os
import sys
import unittest

LOGS = [p for p in sys.argv[1:] if os.path.basename(p) == "3_5_place_dp.log"]


class BandTest(unittest.TestCase):
    def test_no_recovery(self):
        self.assertEqual(len(LOGS), 1, sys.argv[1:])
        with open(LOGS[0]) as f:
            log = f.read()
        self.assertIn("Negotiation phase 1 converged", log)
        for msg in ("DPL-0700", "DPL-0701", "DPL-0702", "DPL-0704"):
            self.assertNotIn(msg, log)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
