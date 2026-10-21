#!/usr/bin/env python3
"""bazelisk run @bazel-orfs//:odb_debug -- //<project>:<module>_<stage> [VAR=value ...]

Start the odb-debug daemon on a flow stage in the background, in a
session of its own that outlives this command, wait until OpenROAD's web
viewer is ready and print its link: the warm GUI the warm-gui skill hands
over, from a shell. The stage is built first if it is out of date.

The daemon lives in $ODB_DEBUG_DIR, by default the workspace's
tmp/odb-debug, where the odb-debug MCP server looks. VAR=value are make
variables for the daemon: GUI_TIMING=0 when geometry is all you need,
ODB_DEBUG_GUI_BIND=<address> to listen where a browser on another machine
reaches this one (by default the address an ssh session came in on, else
127.0.0.1).

Standard library only, Python 3.6 syntax, like odbdebug.py beside it.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import odbdebug  # noqa: E402

POLL_SECS = 2


def main(argv, environ=None, sleep=time.sleep):
    environ = os.environ if environ is None else environ
    if len(argv) < 2 or argv[1].startswith("-"):
        sys.stderr.write(__doc__)
        return 2
    target = argv[1]
    workspace = environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    directory = os.path.join(
        workspace, environ.get("ODB_DEBUG_DIR") or os.path.join("tmp", "odb-debug")
    )
    try:
        launched = odbdebug.launch(target, directory, argv[2:], workspace=workspace)
    except odbdebug.DaemonError as e:
        sys.stderr.write("%s\n" % e)
        return 1
    sys.stderr.write("loading %s, log: %s\n" % (target, launched["log"]))
    state = odbdebug.gui_state(directory)
    while state["state"] == "loading":
        sleep(POLL_SECS)
        state = odbdebug.gui_state(directory)
    if state["state"] != "ready":
        sys.stderr.write("the daemon stopped:\n%s\n" % state.get("log_tail", ""))
        return 1
    print(state["gui_url"])
    sys.stderr.write("%s\n" % odbdebug.GUI_HOW)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
