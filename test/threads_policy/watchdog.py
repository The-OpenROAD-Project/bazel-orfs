#!/usr/bin/env python3
"""Turn a hang into a backtrace instead of a missing row.

bazel-orfs#970 carries one open item that every previous attempt failed
to characterise: an intermittent `sta::find_timing -threads 32` hang,
CI-confirmed and never root-caused. OpenSTA replaced its dispatch-queue
spin with a latch three days later and nobody knows whether that was
the fix, *because no run of it ever produced a stack.* A hang that is
killed by a timeout leaves a truncated log and nothing to read.

So every arm runs under a watchdog. On expiry:

1. the OpenROAD and OpenSTA processes under the arm are found,
2. each gets `thread apply all bt` -- which for a hang is the whole
   answer, since the interesting part is which threads are parked and
   on what,
3. only then is the tree killed.

Two consequences that are deliberate:

**A timed-out arm is a finding, not a gap.** It is recorded with
`hang: true` and the path to its stacks. A campaign that silently drops
the arm that hung would report the hang as an absence, and an absence
averages away.

**No gdb is not a reason to lose the evidence.** Without it the
processes get `SIGABRT`, which runs OpenROAD's own handler and puts a
stack in the log. Worse than gdb, better than a SIGTERM that prints
nothing. This module lives under `test/`, so the host-tool denylist
does not apply to it; it still has to work where gdb is absent, because
that is most CI runners.
"""

import os
import signal
import subprocess

# What is worth a backtrace. The `make` and shell processes above them
# are parked in wait() and say nothing about the hang.
TOOLS = ("openroad", "opensta", "sta")


def read_ppids(proc="/proc"):
    """{pid: ppid} for every process, from /proc.

    Read in one pass: a process tree walked lazily changes underneath
    the walk, and children of a hung tool can exit while it is read.
    """
    out = {}
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc, name, "stat")) as handle:
                fields = handle.read().rsplit(")", 1)[-1].split()
            # After the comm field: state, ppid, ...
            out[int(name)] = int(fields[1])
        except (OSError, IndexError, ValueError):
            # The process exited between listdir and read. Not an
            # error: it is not hung.
            continue
    return out


def descendants(root_pid, ppids):
    """Every pid under `root_pid`, deepest last.

    Pure, so the tree logic is testable without a hung process. A cycle
    cannot occur in a real process tree, but a torn read of /proc can
    produce one, and looping forever inside the hang handler would be a
    poor way to report a hang.
    """
    out = []
    frontier = [root_pid]
    seen = {root_pid}
    children = {}
    for pid, ppid in ppids.items():
        children.setdefault(ppid, []).append(pid)
    while frontier:
        pid = frontier.pop(0)
        for child in sorted(children.get(pid, [])):
            if child in seen:
                continue
            seen.add(child)
            out.append(child)
            frontier.append(child)
    return out


def process_name(pid, proc="/proc"):
    try:
        with open(os.path.join(proc, str(pid), "comm")) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def tools_under(root_pid, proc="/proc"):
    """The tool processes under an arm, which are the ones to dump."""
    ppids = read_ppids(proc)
    out = []
    for pid in descendants(root_pid, ppids):
        name = process_name(pid, proc).lower()
        if any(tool in name for tool in TOOLS):
            out.append((pid, name))
    return out


def have_gdb(runner=subprocess.run):
    try:
        return (
            runner(
                ["gdb", "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
    except OSError:
        return False


def capture(root_pid, dest, proc="/proc", runner=subprocess.run, timeout_s=120):
    """Write what every tool thread under `root_pid` is doing, to `dest`.

    Returns the path when something was written, else None. Never
    raises: this runs while an arm is already going wrong, and losing
    the hang record to a second failure would be the worst outcome.
    """
    found = tools_under(root_pid, proc)
    if not found:
        return None
    gdb = have_gdb(runner)
    lines = []
    for pid, name in found:
        lines.append("=== pid {} ({})".format(pid, name))
        if not gdb:
            # OpenROAD installs a handler that prints a stack on abort.
            lines.append(
                "gdb is not installed; sent SIGABRT so the tool's own "
                "handler prints a stack into the arm's log"
            )
            try:
                os.kill(pid, signal.SIGABRT)
            except OSError as error:
                lines.append("could not signal: {}".format(error))
            continue
        try:
            out = runner(
                [
                    "gdb",
                    "-p",
                    str(pid),
                    "--batch",
                    "-ex",
                    "thread apply all bt",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_s,
            )
            lines.append(out.stdout or "")
        except (OSError, subprocess.SubprocessError) as error:
            lines.append("gdb failed: {}".format(error))
    try:
        with open(dest, "w") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        return None
    return dest


def kill_tree(process):
    """Stop an arm and everything it started.

    The arm is launched in its own session (`start_new_session=True`),
    so one `killpg` reaches `make`, the shell wrappers and the tool.
    Killing only the `make` process would leave a hung OpenROAD holding
    its cores, and every arm measured after it would be measuring that.
    """
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except OSError:
        try:
            process.kill()
        except OSError:
            pass
