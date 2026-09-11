#!/usr/bin/env python3
"""Rewrite the OpenROAD archive_override's study patch list in MODULE.bazel.

    python3 tmp/set_patches.py 0066 0067        # profile + one candidate

0066 is always first: every arm runs the profiled binary.
"""
import re
import sys

NAMES = {
    "0066": "0066-openroad-rsz-profile-repair-setup.patch",
    "0067": "0067-openroad-rsz-progress-row-startpoints-once.patch",
    "0068": "0068-openroad-rsz-progress-row-area-only-after-a-move.patch",
    "0069": "0069-openroad-rsz-exit-setup-repair-when-nothing-moves.patch",
}

wanted = ["0066"] + [n for n in sys.argv[1:] if n != "0066"]
text = open("MODULE.bazel").read()
block = re.search(r"    patches = \[\n(.*?)    \],\n    strip_prefix = \"OpenROAD-", text, re.S)
assert block, "study patch block not found"
lines = "".join(
    '        "//patches:{}",\n'.format(NAMES[n]) for n in wanted
)
new = text[: block.start(1)] + (
    "        # Study instrumentation (study/repair-timing-runtime): where a\n"
    "        # setup repair pass spends its seconds. Prints one [RSZ-PROFILE]\n"
    "        # line per phase; changes no result. Not for upstream.\n"
) + lines + text[block.end(1):]
open("MODULE.bazel", "w").write(new)
print("MODULE.bazel patches:", wanted)
