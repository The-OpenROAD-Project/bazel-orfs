#!/usr/bin/env python3
"""Read what an ORFS substep log says about time, CPU and thread count.

Four facts live at the end of every ORFS substep log, and this study
turns on all four:

    [INFO ORD-0030] Using 16 thread(s).
    ...
    Elapsed time: 4:12.31[h:]min:sec. CPU time: user 3821.44 sys 91.02 (1549%). Peak memory: 8214032KB.
    Log                       Ext     Elapsed/s Peak Memory/MB sha1sum result [0:20)
    5_2_route                 .odb          252           8021 734947984bd3fee97b5f

`Elapsed time:` is written by ORFS's own flow/scripts/run_command.py,
which flow.sh routes through RUN_CMD (patches/0048). So wall, user, sys,
achieved parallelism and peak RSS are already recorded per substep and
this study measures nothing itself -- it reads what the flow wrote.

`ORD-0030` is the knob witness. `-threads N` reaching the process is the
one thing a thread study may not assume: a typo in a make override, a
variable the flow unsets, or a sub-make that re-derives NUM_CORES would
all produce a well-formed timing number for the wrong arm. OpenROAD
prints the count it actually installed, so every sample carries proof.

The `sha1sum result` column is the identical-work witness, and ORFS's
own genElapsedTime.py already computes it. Comparing runtimes only means
something if the arms produced the same layout; if `-threads` changes
the result, the timing comparison is between different work and has to
be reported as that instead. Reading the hash ORFS already wrote beats
recomputing one over the same file.

Two existing Tcl regexes read the wall field only
(test/estimation_ladder/extract.tcl, test/pre_route_pessimism/size_probe.tcl).
This is the one Python reader, and it takes the CPU fields those drop --
`cpu_pct` is the number the study turns on, since threads that do not
pay for themselves show up as user time rising while wall time does not
fall.
"""

import re

# Mirrors the optional-hours shape of the Tcl regexes cited above:
# "0:00.93" is min:sec, "1:02:03.45" is hour:min:sec.
_ELAPSED = re.compile(
    r"Elapsed time: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\[h:\]min:sec\. "
    r"CPU time: user (\d+(?:\.\d+)?) sys (\d+(?:\.\d+)?) \((\d+)%\)\. "
    r"Peak memory: (\d+)KB\."
)

_THREADS = re.compile(r"\[INFO ORD-0030\] Using (\d+) thread\(s\)\.")

# genElapsedTime.py's summary row: name, extension, whole seconds, peak
# MB, then a 20-hex-character prefix of the result file's sha1. Anchored
# on the two integers and the hash so it cannot match a log line that
# merely happens to end in hex.
_RESULT_SHA1 = re.compile(r"^\S+\s+\.\S+\s+\d+\s+\d+\s+([0-9a-f]{20})\s*$", re.M)


class LogIncomplete(Exception):
    """The log carries no timing line, so the substep did not finish."""


def parse_text(text):
    """Timing, CPU and thread count from one substep log's contents.

    Returns a dict with wall_s, user_s, sys_s, cpu_pct, peak_kb,
    threads and result_sha1. The last two are None when the log carries
    no ORD-0030 line and no genElapsedTime summary row respectively --
    unproven, which the caller must not read as a default value.

    Raises LogIncomplete when there is no `Elapsed time:` line at all:
    a substep that crashed or was killed leaves a log that parses to
    nothing, and silently scoring that as a zero is exactly the quiet
    wrong number this harness exists to prevent.

    The last match wins. run_command.py opens the log with --append, so
    a re-run into a log that was not truncated would leave two, and the
    newest is the one just measured.
    """
    hits = _ELAPSED.findall(text)
    if not hits:
        raise LogIncomplete("no 'Elapsed time:' line: the substep did not finish")
    hours, minutes, seconds, user, sys_, cpu_pct, peak_kb = hits[-1]

    threads = _THREADS.findall(text)
    sha1 = _RESULT_SHA1.findall(text)

    return {
        "wall_s": int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds),
        "user_s": float(user),
        "sys_s": float(sys_),
        "cpu_pct": int(cpu_pct),
        "peak_kb": int(peak_kb),
        "threads": int(threads[-1]) if threads else None,
        "result_sha1": sha1[-1] if sha1 else None,
    }


def parse_log(path):
    """parse_text() over a log file, with the path named on failure."""
    with open(path, errors="replace") as handle:
        text = handle.read()
    try:
        return parse_text(text)
    except LogIncomplete as exc:
        raise LogIncomplete("{}: {}".format(path, exc))
