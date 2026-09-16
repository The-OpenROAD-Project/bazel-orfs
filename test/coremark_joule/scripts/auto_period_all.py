#!/usr/bin/env python3
"""auto_period for several designs at once, one bazel invocation per round.

auto_period.py walks one design: build its `_period` probe, read the
reg2reg slack, ask for `period - WNS`, build again. Four designs walked
one after another serialise four flows that share nothing, on a machine
that would run them side by side. This driver keeps auto_period's
decision logic -- step(), probe_reading(), set_clk_period() are imported,
not copied -- and changes only the schedule: every round builds the
probe targets of every design that has not converged in a single
`bazel build`, then steps each design on its own reading.

The per-design evidence JSON is the same shape auto_period writes, so
§5.5's tables read either.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auto_period as ap  # noqa: E402


class Design:
    def __init__(self, spec):
        # The bazel label carries a colon of its own; the paths around it
        # are absolute and colon-free, so peel the fixed fields off both
        # ends and what remains is the label.
        name, constraints, rest = spec.split(":", 2)
        target, artifact, evidence = rest.rsplit(":", 2)
        self.name = name
        self.constraints = constraints
        self.target = target
        self.artifact = artifact
        self.evidence = evidence
        with open(constraints) as f:
            self.period = ap.read_clk_period(f.read())
        self.start = self.period
        self.history = []
        self.winner = None
        self.status = "running"

    def pin(self, period_ps):
        with open(self.constraints) as f:
            text = f.read()
        with open(self.constraints, "w") as f:
            f.write(ap.set_clk_period(text, period_ps))
        self.period = period_ps


def run_round(designs, read_probes, tolerance_ps):
    """One round over every unconverged design; returns those still running."""
    active = [d for d in designs if d.status == "running"]
    readings = read_probes([d for d in active])
    still = []
    for d, text in zip(active, readings):
        probe_period, wns, paths = ap.probe_reading(text)
        ap.check_probe_matches_request(d.period, probe_period)
        d.history.append(
            {
                "period_ps": d.period,
                "wns_reg2reg_ps": wns,
                "reg2reg_paths": paths,
                "closed": wns >= 0,
            }
        )
        if wns >= 0:
            d.winner = d.period
        status, nxt = ap.step(d.period, wns, tolerance_ps, d.winner is not None)
        if status in ("converged", "overshot"):
            d.status = status
        else:
            d.pin(nxt)
            still.append(d)
    return still


def derive_all(designs, read_probes, max_iterations=6, tolerance_ps=2.0):
    for _ in range(max_iterations):
        if not run_round(designs, read_probes, tolerance_ps):
            break
    for d in designs:
        if d.status == "running":
            d.status = "exhausted"
        if d.winner is None:
            raise ap.Fatal(
                "%s did not close at any of the %d periods tried"
                % (d.name, len(d.history))
            )
        # Pin the winner, which may not be the last period tried.
        if d.period != d.winner:
            d.pin(d.winner)
    return designs


def bazel_probes(bazel):
    # `bazel run` starts us inside the runfiles tree, and bazel refuses to
    # be invoked from an output directory; build from the workspace root.
    cwd = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or None

    def read(active):
        subprocess.run(
            [bazel, "build"] + [d.target for d in active], check=True, cwd=cwd
        )
        out = []
        for d in active:
            with open(d.artifact) as f:
                out.append(f.read())
        return out

    return read


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--design",
        action="append",
        required=True,
        metavar="NAME:CONSTRAINTS:TARGET:ARTIFACT:EVIDENCE",
        help="one design: its constraints.sdc, its _period bazel target, the "
        "path that target writes, and where to write its history JSON",
    )
    p.add_argument("--bazel", default="bazelisk")
    p.add_argument("--max-iterations", type=int, default=6)
    p.add_argument("--tolerance-ps", type=float, default=2.0)
    args = p.parse_args(argv[1:])
    designs = [Design(s) for s in args.design]
    try:
        derive_all(
            designs, bazel_probes(args.bazel), args.max_iterations, args.tolerance_ps
        )
    except ap.Fatal as e:
        print("auto_period_all: %s" % e, file=sys.stderr)
        return 1
    for d in designs:
        with open(d.evidence, "w") as f:
            json.dump(
                {
                    "start_ps": d.start,
                    "winner_ps": d.winner,
                    "status": d.status,
                    "tolerance_ps": args.tolerance_ps,
                    "history": d.history,
                },
                f,
                indent=2,
            )
            f.write("\n")
        print("%-14s %5d -> %5d ps  %s" % (d.name, d.start, d.winner, d.status))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
