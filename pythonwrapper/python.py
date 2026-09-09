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
    # Same reasoning, for child *python* scripts. rules_python's venv
    # runs us with PYTHONSAFEPATH=1, which suppresses the script's own
    # directory from sys.path -- so a flow script that runs another
    # python script cannot import that script's siblings, and fails on
    # something like "No module named 'utils'" that reproduces nowhere
    # else. ORFS's AUTO_MEMORIES hits this: gen_memories.py spawns
    # FakeRAM's run.py, which imports its own utils/ package.
    #
    # The flow's scripts are written against a plain `python3`, where
    # the script directory is on sys.path. Dropping the variable gives
    # children exactly that. It does not affect this interpreter, which
    # has already started, and runpy.run_path below never put the script
    # directory on sys.path anyway.
    os.environ.pop("PYTHONSAFEPATH", None)
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
