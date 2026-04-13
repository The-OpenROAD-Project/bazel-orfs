#!/usr/bin/env python3
import os
import runpy
import sys


def main():
    script = sys.argv[1]
    sys.argv = sys.argv[1:]
    # Strip Bazel Python-wrapper runfiles variables so that child
    # native binaries (OpenROAD, yosys, opensta) resolve their
    # *own* runfiles tree instead of inheriting the wrapper's tree.
    os.environ.pop("RUNFILES_DIR", None)
    os.environ.pop("RUNFILES_MANIFEST_FILE", None)
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
