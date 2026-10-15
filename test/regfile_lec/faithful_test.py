"""lec_fixture.py writes firtool's own text at XiangShan's sizes.

Each of XiangShan's datapath register files, as the Chisel build emitted
it, against the fixture generator at that module's parameters, token for
token (layout aside). The LEC tests run the same generator small; this
is what makes the small fixtures the RTL firtool would write.

Usage: faithful_test.py <xiangshan_flat.sv, as a runfiles path>
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lec_fixture  # noqa: E402
import tokdiff  # noqa: E402

FLAT = ""

MODULES = {
    "FpRegFile": "--words 256 --bits 64 --reads 14 --writes 7 --latency 1",
    "VfRegFile": "--words 128 --bits 128 --reads 14 --writes 7 --latency 1",
    "IntRegFile": "--words 224 --bits 64 --reads 12 --writes 9 --latency 1 "
    "--banks 4 --banked --zero-word",
}


class FaithfulTest(unittest.TestCase):
    def test_modules(self):
        with tempfile.TemporaryDirectory() as d:
            for module, args in MODULES.items():
                with self.subTest(module=module):
                    out = os.path.join(d, module)
                    lec_fixture.main(["--out", out, "--module", module] + args.split())
                    want = tokdiff.tokens(FLAT, module)
                    got = tokdiff.tokens(out + ".sv", module)
                    self.assertEqual(len(want), len(got), module)
                    self.assertEqual(want, got, module)


if __name__ == "__main__":
    FLAT = sys.argv.pop(1)
    unittest.main()
