#!/bin/sh
# gui_<stage> in a bazel-orfs tree. ORFS runs `$(OPENROAD_WEB_CMD) open.tcl`
# with ODB_FILE (or DEF_FILE, V_FILE) pointing at the stage's result;
# bazel-orfs's make points OPENROAD_WEB_CMD here, so the GUI is the
# odb-debug daemon instead of a bare `openroad -web`: the link carries a
# token and works over a VPN, and the agent's MCP tools ask the same
# session. daemon.tcl sources open.tcl itself, so ORFS's argument is
# dropped. It holds the terminal; Ctrl-C ends it.
set -e
here=$(cd "$(dirname "$0")" && pwd)
if [ -z "${ODB_DEBUG_DIR:-}" ]; then
  # The workspace's tmp/odb-debug, where the MCP server looks: the tree
  # of a `bazelisk run`, or the dirty tree's checkout.
  ws=${BUILD_WORKSPACE_DIRECTORY:-$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)}
  ODB_DEBUG_DIR=$ws/tmp/odb-debug
fi
export ODB_DEBUG_DIR
export ODB_DEBUG_PRINT_LINK=1
exec "$OPENROAD_EXE" -no_init -threads "${NUM_CORES:-1}" "$here/daemon.tcl"
