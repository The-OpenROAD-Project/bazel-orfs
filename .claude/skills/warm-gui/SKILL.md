---
name: warm-gui
description: >-
  After a build finishes, load the stage the human most likely wants to look at into
  the odb-debug daemon in the background (the MCP server's `open` tool), so OpenROAD's
  web viewer is warm and one click away when they come to look: tens of minutes of
  loading on a large design happen while they read the build's summary. Picks the
  stage, starts it, hands over the GUI link (token-gated, reachable over a VPN) and
  says how to open it. Use when a flow build or a stage has just finished or failed,
  when the human asks for the GUI or wants to look at a design, or before a long
  build ends unattended.
---

> **Repo**: Run from your ORFS workspace root (the one with `MODULE.bazel` and the `bazel-orfs` dep). Examples use the neutral `//<project>:<module>_<stage>` naming; substitute your own targets.

ARGUMENTS: $ARGUMENTS

The web viewer is the GUI. On a large design, loading the ODB, the
liberty set and parasitics and warming up timing takes tens of minutes,
and that path has no easy wins left. So the load runs while the human is
busy elsewhere, and the GUI is ready when they want it. The daemon is
odb-debug's (`odb-debug` skill, `tools/odb_debug/README.md`): the same
session answers the agent's MCP questions and the human's browser.

## 1. Pick the stage

The one the human will want to look at next:

- the command named a stage (`bazelisk build //<project>:<module>_route`):
  that stage;
- a whole flow was built: `final`;
- the build failed: the last stage that succeeded. A stage that failed
  has no ODB to open; its checkpoint is a `//:dirty` lane's job
  (`odb-debug` skill, "a stage that failed").

The daemon runs an `odb_debug()` target. When the stage has none, add one
beside the flow:

```starlark
load("@bazel-orfs//:openroad.bzl", "odb_debug")

odb_debug(
    name = "<module>_final_odb_debug",
    src = ":<module>_final",
    tags = ["manual"],
)
```

## 2. Start it

MCP tool `open` with the target, and `arguments` for make variables
(`GUI_TIMING=0` when geometry is all the human needs: seconds instead of
minutes on a large design). It returns at once. `bazelisk run` builds
the stage first if it is out of date, so a target that is not built yet
is not an error, only a longer load.

`open` refuses when a daemon already serves the session's
`ODB_DEBUG_DIR`, and says which. One daemon holds the whole design in
memory: ask the human before replacing one (the `tcl` tool's `exit`
stops it).

The daemon runs in a session of its own and outlives the agent's. It
waits, with no idle exit, for the first question or browser visit; from
then on it exits after `ODB_DEBUG_IDLE_SECS` (default twice the load
time, at least 120 s) without one. Nothing of it is in the Bazel cache:
the next session loads it again.

## 3. Hand over the link

Poll the `gui` tool rarely, a minute or more apart: `loading` with the
end of the launch log, then `ready` with `gui_url`, or `stopped` with the
log that says why. Give the human the link as it is, with:

- **Open it in a browser on your machine.** The link carries a token,
  the only key to the session: the viewer runs any Tcl it is sent. Do
  not paste it anywhere public.
- **Over a VPN** it works as is: the daemon listens on the address the
  human's ssh session came in on (`SSH_CONNECTION`), the one their
  machine reaches. Started from a session that is not ssh, it listens on
  127.0.0.1; set `ODB_DEBUG_GUI_BIND=<the VPN address>` in `arguments`
  to reach it from elsewhere.
- **If the browser cannot connect:** is the VPN up, does the address
  answer, does a firewall block the port? Without a VPN, tunnel it:
  `ssh -L <port>:<address>:<port> <machine>`, then open the link with
  `localhost:<port>` in place of `<address>:<port>`.
- **A browser on the viewer's own 127.0.0.1 port** (daemon.json's `url`)
  works on the machine itself, but its activity does not count: the
  daemon idles out under it. Use the link.

## What this is not

- Not a cache: a warm session is one process's memory. A second machine,
  or the same one after the daemon exited, loads again.
- Not for the agent's own questions: those go through the MCP tools,
  which answer in milliseconds from the same session (`odb-debug` skill).
