#!/usr/bin/env python3
"""Prefix every ORFS log line with elapsed seconds.

A drop-in for ORFS's `RUN_CMD` (`flow/scripts/run_command.py`), injected
by the stage rules when `--@bazel-orfs//:log_timestamps` is on. ORFS
funnels every logged tool invocation through that one variable, so
overriding it stamps every stage log without patching ORFS.

    [    0.000] [INFO GPL-0002] DBU: 1000
    [  184.421]       1300 |   0.0912 | 1.234560e+06 |  -0.31% | ...

The prefix is elapsed wall seconds since the command started, so a log
answers "where did the four hours go" by inspection -- which iteration
of which grind, and how fast the iterations were coming. That is the
question an ORFS log otherwise cannot answer at all: `Took N seconds`
(util.tcl) and the closing `Elapsed time:` line arrive only once the
command is over.

Timing is measured when a line is read out of the child's pipe, so it
is emission time only to the extent the child flushes as it goes.
OpenROAD's logger does; anything that block-buffers will show as a
burst of identical stamps, which is itself worth knowing.

The heavy lifting -- process management, rusage accounting, the closing
`Elapsed time:` line ORFS's own tooling parses -- stays in ORFS's
run_command.py, which this delegates to. Only the stamping and the log
write happen here.
"""

import argparse
import os
import subprocess
import sys
import time


def stamp(prefix_seconds):
    return "[{:9.3f}] ".format(prefix_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a command with timestamped log output.",
    )
    parser.add_argument("--log", help="Log file path")
    parser.add_argument("--append", action="store_true", help="Append to the log")
    parser.add_argument("--tee", action="store_true", help="Also write to stdout")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("No command specified")

    flow_home = os.environ.get("FLOW_HOME")
    if not flow_home:
        sys.stderr.write("log_timestamps.py: FLOW_HOME is not set\n")
        return 1
    run_command = os.path.join(flow_home, "scripts", "run_command.py")

    # --tee, never --log: run_command.py streams everything to its stdout
    # and this process owns the log file. Its closing timing line goes to
    # stderr, so merge stderr in to keep it in the log.
    child = [sys.executable, run_command, "--tee", "--"] + cmd

    log_file = None
    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
        log_file = open(args.log, "a" if args.append else "w")

    start = time.monotonic()
    proc = subprocess.Popen(
        child,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = stamp(time.monotonic() - start) + raw.decode(errors="replace")
            if args.tee:
                sys.stdout.write(line)
                sys.stdout.flush()
            if log_file:
                log_file.write(line)
                log_file.flush()
        proc.wait()
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        if log_file:
            log_file.close()

    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
