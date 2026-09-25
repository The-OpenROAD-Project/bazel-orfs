"""odb_debug: a persistent OpenROAD session on a flow stage, for questions.

    load("@bazel-orfs//:openroad.bzl", "odb_debug")

    odb_debug(
        name = "cpu_place_odb_debug",
        src = ":cpu_place",
    )

    bazelisk run //my:cpu_place_odb_debug -- ODB_DEBUG_DIR=tmp/odb-debug

opens the stage's ODB in the flow's own OpenROAD, with the flow's SDC,
liberty set, RC and derates, and serves Tcl over a localhost socket until
it has been idle for a while. tools/odb_debug/odbdebug.py is the client,
tools/odb_debug/mcp_server.py the MCP server an agent talks to, and
tools/odb_debug/README.md the manual.

`bazelisk run` builds the stage first when it is out of date. For a stage
that failed or was stopped, deploy the stage's `_deps` tree and run the
daemon on the checkpoint by hand; the README shows how.
"""

load("//private:rules.bzl", "orfs_run_executable")

def odb_debug(name, src, **kwargs):
    """A runnable daemon target for the ODB of a flow stage.

    Args:
        name: Target name.
        src: The flow stage whose ODB to serve (`orfs_flow`'s `_floorplan`,
            `_place`, `_cts`, `_grt`, `_route` or `_final`; `_synth` when
            it saves an ODB).
        **kwargs: Passed to `orfs_run_executable`: `arguments` for make
            variables such as `{"GUI_TIMING": "0"}`, `visibility`, `tags`.
    """
    orfs_run_executable(
        name = name,
        src = src,
        cmd = "run",
        script = "@bazel-orfs//tools/odb_debug:daemon.tcl",
        **kwargs
    )
