#!/usr/bin/env python3
"""Run a gate-level simulation windowed on CoreMark's last iteration.

The window is not chosen; it is derived from the cheap RTL runs.

CoreMark prints nothing until its report, so the cycle of the first
character out is exactly where the benchmark loop ended. With D the
cycles per iteration -- the same `cycles_3 - cycles_2` the score is built
from -- the last iteration spans

    [first_output - D, first_output]

and that iteration is the one running hot: its working set is already
resident, and nothing in it is startup or reporting. Activity averaged
over anything wider understates the benchmark.

Cycle behaviour is identical between the RTL and gate-level simulations
of the same design, so the window can be measured on the fast one and
applied to the slow one. That matters: a netlist simulation is far
slower than RTL, and a SAIF over a whole run would be both enormous and
less representative.

Usage:
  saif_window.py --sim S --image I --cycles-2 A --cycles-3 B --saif O
"""

import argparse
import re
import subprocess
import sys


def read_cycles(path):
    """Return (total_cycles, first_output_cycle) from a run's cycles file."""
    total = None
    first_output = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("first_output "):
                first_output = int(line.split()[1])
            elif total is None:
                total = int(line)
    if total is None:
        raise ValueError("{}: no cycle count".format(path))
    return total, first_output


def window(cycles_2, cycles_3, first_output_3):
    """The last iteration of the three-iteration run, in cycles."""
    delta = cycles_3 - cycles_2
    if delta <= 0:
        raise ValueError(
            "cycles_3 ({}) is not greater than cycles_2 ({}): the two runs "
            "did not differ by one iteration".format(cycles_3, cycles_2)
        )
    if first_output_3 is None:
        raise ValueError(
            "the three-iteration run recorded no first-output cycle, so the "
            "end of the benchmark loop is unknown"
        )
    start = first_output_3 - delta
    if start < 0:
        raise ValueError(
            "the benchmark loop ({} cycles) is shorter than one iteration "
            "({}): the runs are not what they claim to be".format(first_output_3, delta)
        )
    return start, first_output_3


_CLK_PERIOD = re.compile(r"^\s*set\s+clk_period\s+(\d+)\s*(?:;.*|#.*)?$", re.M)


def read_clk_period(sdc_text):
    """The `set clk_period <ps>` of a constraints.sdc, as an int.

    The same line auto_period rewrites and cm_per_joule reads the
    frequency from; the three agree by reading one file.
    """
    m = _CLK_PERIOD.search(sdc_text)
    if not m:
        raise ValueError("no `set clk_period <ps>` line in the constraints")
    return int(m.group(1))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--cycles-2", required=True)
    parser.add_argument("--cycles-3", required=True)
    parser.add_argument("--saif", required=True)
    parser.add_argument("--max-cycles", default="2000000000")
    period = parser.add_mutually_exclusive_group(required=True)
    period.add_argument(
        "--clk-period-ps",
        help="Clock period in picoseconds. The SAIF records real time, "
        "because OpenSTA reads it as transitions divided by duration; a "
        "period that disagrees with the SDC scales every toggle rate, and "
        "so the power, by the ratio between them.",
    )
    period.add_argument(
        "--clk-period-from-sdc",
        metavar="CONSTRAINTS_SDC",
        help="Read the period from the design's constraints.sdc "
        "(`set clk_period <ps>`), so the period the design was built at "
        "and the duration the SAIF is timed over cannot disagree. They "
        "did: auto_period re-derived every core's period and the capture "
        "kept the old literal, which scales the reported power by the "
        "ratio between them.",
    )
    args = parser.parse_args(argv[1:])
    if args.clk_period_from_sdc:
        with open(args.clk_period_from_sdc) as f:
            args.clk_period_ps = str(read_clk_period(f.read()))

    cycles_2, _ = read_cycles(args.cycles_2)
    cycles_3, first_output_3 = read_cycles(args.cycles_3)
    start, end = window(cycles_2, cycles_3, first_output_3)

    print(
        "saif window: cycles {}..{} ({} cycles, one iteration)".format(
            start, end, end - start
        ),
        file=sys.stderr,
    )

    return subprocess.call(
        [
            args.sim,
            "+meminit=" + args.image,
            "+saif=" + args.saif,
            "+saif_start={}".format(start),
            "+saif_end={}".format(end),
            "+max_cycles=" + args.max_cycles,
            "+clk_period_ps=" + args.clk_period_ps,
        ],
        stdout=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv))
