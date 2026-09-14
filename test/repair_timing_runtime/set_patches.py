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
    "0070": "0070-openroad-rsz-policy-endpoint-yield-gate.patch",
    "0071": "0071-openroad-rsz-policy-last-gasp-after-gaining-phase.patch",
    "0072": "0072-openroad-rsz-policy-move-type-budget.patch",
    "0073": "0073-openroad-rsz-policy-all.patch",
    "0074": "0074-openroad-rsz-return-controller.patch",
    "0075": "0075-openroad-rsz-experiment-worst-slack-query.patch",
    "0076": "0076-openroad-rsz-experiment-controller-window-report.patch",
    "0077": "0077-openroad-rsz-defer-and-revisit.patch",
    "0078": "0078-openroad-rsz-trace-endpoint-visits.patch",
}

wanted = ["0066"] + [n for n in sys.argv[1:] if n != "0066"]
text = open("MODULE.bazel").read()
block = re.search(
    r"    patches = \[\n(.*?)    \],\n    strip_prefix = \"OpenROAD-", text, re.S
)
assert block, "study patch block not found"
lines = "".join('        "//patches:{}",\n'.format(NAMES[n]) for n in wanted)
new = (
    text[: block.start(1)]
    + (
        "        # Study instrumentation (study/repair-timing-runtime): where a\n"
        "        # setup repair pass spends its seconds. Prints one [RSZ-PROFILE]\n"
        "        # line per phase; changes no result. Not for upstream.\n"
    )
    + lines
    + text[block.end(1) :]
)
open("MODULE.bazel", "w").write(new)
print("MODULE.bazel patches:", wanted)
