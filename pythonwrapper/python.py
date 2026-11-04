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
    # A plain `python3` caches each module it imports as bytecode in a
    # __pycache__ beside the source, which in a build is someone else's
    # tree: an external repository, or the workspace. A .pyc embeds its
    # source's mtime, so it differs per machine, and any glob that picks
    # it up puts that difference into an action's cache key. FakeRAM's
    # utils/ did, through the @orfs FakeRAM filegroup, and every
    # synthesis missed the cache on every machine but the one that wrote
    # it. No bytecode is written: by this interpreter, which imports the
    # script's modules, nor by any child python, which inherits the
    # variable (gen_memories.py runs FakeRAM with sys.executable).
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
