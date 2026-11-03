#!/usr/bin/env python3
"""Write the XSTile implementation kit to a directory and unpack it there.

  bazelisk run //test/coremark_joule/designs/asap7/xiangshan:export -- <dir>

writes <dir>/xiangshan-xstile-asap7.tar.gz and unpacks it beside the
archive, into <dir>/xiangshan-xstile-asap7/. A relative <dir> is taken
from where bazelisk was run. It stops if that kit directory exists: a
tool's results/ may be in it.
Python 3.6.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit  # noqa: E402


def main(argv):
    if len(argv) != 2 or argv[1].startswith("-"):
        sys.exit(
            "usage: bazelisk run //test/coremark_joule/designs/asap7/xiangshan:export -- <dir>"
        )
    archive = os.environ.get("KIT_ARCHIVE")
    if not archive:
        sys.exit("export: KIT_ARCHIVE is not set; run it with bazelisk run")
    archive = os.path.abspath(archive)
    dest = os.path.expanduser(argv[1])
    if not os.path.isabs(dest):
        dest = os.path.join(
            os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd()), dest
        )
    dest = os.path.normpath(dest)
    if not os.path.isdir(dest):
        sys.exit("export: %s is not a directory" % dest)
    out = os.path.join(dest, kit.ROOT + ".tar.gz")
    tree = os.path.join(dest, kit.ROOT)
    # an earlier kit may hold a tool's results/: never overwritten
    if os.path.exists(tree):
        sys.exit(
            "export: %s exists; move it away first (its results/ may be a tool's output)"
            % tree
        )
    shutil.copyfile(archive, out)
    kit.main(["unpack", "--in", out, "--dir", dest])
    print("export: %s" % out)
    print("export: %s/README.pdf" % tree)


if __name__ == "__main__":
    main(sys.argv)
