"""SYNTH_VERILOG_SURGERY fixture: invert one continuous assignment.

surgery.py --invert <net> --out-dir <dir> -- <verilog files>

Copies each file into <dir> under its own name, rewriting
`assign <net> = <expr>;` to `assign <net> = ~(<expr>);`. Stops when not
exactly one file assigns <net> that way, as a surgery script should when
it does not recognise its input.
"""

import argparse
import os
import re
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--invert", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    pattern = re.compile(r"assign\s+%s\s*=\s*([^;]+);" % re.escape(args.invert))
    edited = 0
    for path in args.files:
        with open(path) as f:
            text = f.read()
        text, n = pattern.subn(r"assign %s = ~(\1);" % args.invert, text)
        edited += n
        with open(os.path.join(args.out_dir, os.path.basename(path)), "w") as f:
            f.write(text)
    if edited != 1:
        sys.exit("surgery.py: %d assignments to %s, expected 1" % (edited, args.invert))


if __name__ == "__main__":
    main()
