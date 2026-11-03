#!/usr/bin/env python3
"""Pin the facts README.pdf states about the kit's netlist into kit/pinned/.

  bazelisk run //test/coremark_joule/designs/asap7/xiangshan:kit_repin

builds the kit's synthesis and its facts (kit_facts.tcl), and writes
facts.json, rtl_ports.json and pin.json (the SHA-256 of the netlist
they describe, and the day) into kit/pinned/ in the source tree: commit
them. A commit hash would not do: the merge rebases the branch it names. README.pdf reads
the pin, so a new kit re-renders its README in seconds, and its stamp
names the netlist the pin describes beside the commit the PDF was built
from.

  repin.py --check <built facts.json> <built rtl_ports.json> <built pin.json>

compares a fresh build with the pin and fails, naming what moved, when
they differ (kit_pin_test). Python 3.6.
"""

import json
import os
import shutil
import sys

PINNED = os.path.join(
    "test", "coremark_joule", "designs", "asap7", "xiangshan", "kit", "pinned"
)


def check(built):
    stale = []
    for path in built:
        pinned = os.path.join(PINNED, os.path.basename(path))
        with open(path) as f:
            new = json.load(f)
        with open(pinned) as f:
            old = json.load(f)
        if os.path.basename(path) == "pin.json":
            # the day of a pin is not what makes it stale
            new, old = new["netlist_sha256"], old["netlist_sha256"]
        if new != old:
            keys = (
                sorted(k for k in set(new) | set(old) if new.get(k) != old.get(k))
                if isinstance(new, dict) and isinstance(old, dict)
                else ["the list"]
            )
            stale.append("%s: %s" % (os.path.basename(path), ", ".join(keys)))
    if stale:
        sys.exit(
            "kit/pinned/ is stale (%s); bazelisk run //test/coremark_joule/designs/asap7/xiangshan:kit_repin"
            % "; ".join(stale)
        )
    print("kit/pinned/ matches the build")


def write(built):
    root = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not root:
        sys.exit("repin: run it with bazelisk run")
    dest = os.path.join(root, PINNED)
    os.makedirs(dest, exist_ok=True)
    for path in built:
        shutil.copyfile(path, os.path.join(dest, os.path.basename(path)))
        print("repin: %s" % os.path.join(PINNED, os.path.basename(path)))
    with open(os.path.join(dest, "pin.json")) as f:
        print("repin: pinned netlist %s" % json.load(f)["netlist_sha256"])


def main(argv):
    if argv[1:2] == ["--check"]:
        check(argv[2:])
    else:
        write(argv[1:])


if __name__ == "__main__":
    main(sys.argv)
