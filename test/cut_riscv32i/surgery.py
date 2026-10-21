"""riscv32i's 32-bit comparator as operators (SYNTH_VERILOG_SURGERY).

    surgery.py [--wrong] --out-dir DIR -- <verilog files>

magcompare32 is a hand-built tree of 2-bit compare cells (Stine and
Schulte); as written, synthesis sees gates and neither yosys's alumacc nor
OpenROAD's SWAP_ARITH_OPERATORS see a comparison. Its body becomes
`A < B`, `A > B`, `A == B`, the same unsigned function of the same ports.
Every other file is copied unchanged. --wrong makes LT `A <= B`: the
negative control the LEC check must reject.

Stops when magcompare32 is not found exactly as expected: a changed
upstream is a surgery to redo, not one to guess at.
"""

import argparse
import os
import re
import shutil
import sys

MODULE = re.compile(r"module magcompare32 \(GT, LT, EQ, A, B\);.*?endmodule", re.S)

BODY = """module magcompare32 (GT, LT, EQ, A, B);

   input wire [31:0] A;
   input wire [31:0] B;

   output wire       LT;
   output wire       EQ;
   output wire       GT;

   // SYNTH_VERILOG_SURGERY (test/cut_riscv32i/surgery.py): the compare
   // tree as operators, which synthesis and SWAP_ARITH_OPERATORS can see
   assign LT = A %s B;
   assign GT = A > B;
   assign EQ = A == B;

endmodule"""


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--wrong", action="store_true")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    os.makedirs(args.out_dir, exist_ok=True)
    done = False
    for path in args.files:
        out = os.path.join(args.out_dir, os.path.basename(path))
        if os.path.basename(path) != "magcompare32.v":
            shutil.copyfile(path, out)
            continue
        with open(path) as f:
            text = f.read()
        if len(MODULE.findall(text)) != 1:
            sys.exit("surgery: magcompare32 is not as expected in %s" % path)
        text = MODULE.sub(lambda m: BODY % ("<=" if args.wrong else "<"), text)
        with open(out, "w") as f:
            f.write(text)
        done = True
    if not done:
        sys.exit("surgery: no magcompare32.v among the sources")
    return 0


if __name__ == "__main__":
    sys.exit(main([a for a in sys.argv[1:] if a != "--"]))
