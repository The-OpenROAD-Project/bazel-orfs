#!/usr/bin/env python3
"""Translate pymtl3 ChecksumRTL to synthesizable Verilog.

Based on pymtl3/examples/ex02_cksum/cksum-translate.
"""

import argparse
import os
import shutil

from pymtl3.passes.backends.yosys import YosysTranslationPass
from examples.ex02_cksum.ChecksumRTL import ChecksumRTL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Output .v file path")
    args = parser.parse_args()

    cksum = ChecksumRTL()
    cksum.set_metadata(YosysTranslationPass.enable, True)
    cksum.elaborate()
    cksum.apply(YosysTranslationPass())

    # Translation writes to cwd with auto-generated filename
    generated = cksum.get_metadata(YosysTranslationPass.translated_filename)
    shutil.copy(generated, args.output)


if __name__ == "__main__":
    main()
