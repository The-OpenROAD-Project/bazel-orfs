"""Derive a design's clock period from its own register-to-register slack.

The period in a `constraints.sdc` is a starting guess. What the study
wants is the period the core actually closes at, because the energy
number is reported at a frequency and a core scored below its achievable
one is charged too much leakage energy per iteration (paper, 5.5).

The measurement is a fixed point rather than a single reading. At a
period the optimiser met with room to spare it stops early, so
`period - WNS` understates the core; asked for the tighter period it
tries harder and closes again, until it cannot. So: build, read the
reg2reg worst slack, ask for `period - WNS`, build again. Stop when the
period stops moving (converged) or when the design stops closing
(overshot), and pin the tightest period that *did* close -- never one
that has only been predicted.

This cannot be a bazel ladder. The clock period is a synthesis input, so
every candidate re-runs synthesis and everything after it; there is no
shared checkpoint for candidates to start from the way there is for a
floorplan candidate (paper, 5.5). The loop therefore lives here and
drives bazel, in the shape of the floorplan derivation: a job that is
run, writes its evidence, and pins its answer.

Only reg2reg slack drives it. The other path groups are budgets against
an assumed register outside every port, so a period driven by the
overall WNS would be limited by that assumption rather than by the
design (paper, 3.8).
"""

import argparse
import json
import re
import subprocess
import sys

_CLK_PERIOD = re.compile(r"^(\s*set\s+clk_period\s+)(\d+)(\s*(?:;.*|#.*)?)$", re.M)


class Fatal(Exception):
    """A condition the loop must not paper over by continuing."""


def parse_probe(text):
    """Parse period_probe.tcl's `key value` output into a dict."""
    out = {}
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[0]] = parts[1].strip()
    return out


def probe_reading(text):
    """The three numbers the loop needs, checked rather than assumed.

    A probe that matched no reg2reg paths reports a worst slack of zero
    exactly as a design with no headroom does, and the two mean opposite
    things -- so the path count is part of the reading, not a diagnostic.
    """
    d = parse_probe(text)
    for key in ("period_ps", "wns_reg2reg_ps", "reg2reg_paths_returned"):
        if key not in d:
            raise Fatal("probe output has no %s; got keys %s" % (key, sorted(d)))
    paths = int(d["reg2reg_paths_returned"])
    if paths == 0:
        raise Fatal(
            "probe returned no reg2reg paths: the group matched nothing, "
            "which is not the same as a design with zero slack"
        )
    return float(d["period_ps"]), float(d["wns_reg2reg_ps"]), paths


def read_clk_period(sdc_text):
    m = _CLK_PERIOD.search(sdc_text)
    if not m:
        raise Fatal("no `set clk_period <ps>` line in the constraints")
    return int(m.group(2))


def set_clk_period(sdc_text, ps):
    """Rewrite the period, leaving every other byte of the file alone."""
    if ps <= 0:
        raise Fatal("refusing to write a period of %r ps" % ps)
    new, n = _CLK_PERIOD.subn(lambda m: m.group(1) + str(ps) + m.group(3), sdc_text)
    if n != 1:
        raise Fatal("expected exactly one `set clk_period` line, found %d" % n)
    return new


def next_candidate(period_ps, wns_ps):
    """The period the slack says the design could have closed at.

    Rounded away from the design's favour -- up -- so a rounding error
    can only ask for a period that is easier to meet than the one the
    slack implies, never one that is harder.
    """
    import math

    return int(math.ceil(period_ps - wns_ps))


# When relaxing, the deficit is scaled up before it is applied. The
# one-shot `period - WNS` estimate is measurably optimistic -- VeeR
# closed at 1591 ps with 10.6 ps of slack and then failed at 1581 --
# so relaxing by exactly the deficit tends to land still failing and
# burn an iteration. Overshooting the relax costs nothing: the downward
# walk that follows finds the real edge anyway.
RELAX_MARGIN = 1.1


def step(period_ps, wns_ps, tolerance_ps, closed_before):
    """One decision: (status, next_period).

    ('continue'|'converged') while the design closes, ('relax') while it
    has never closed, ('overshot') once it has closed and then stopped.
    A negative slack means opposite things either side of that line: a
    starting period too tight to tune from, or the edge being found.
    """
    if wns_ps < 0:
        if closed_before:
            return "overshot", period_ps
        return "relax", next_candidate(period_ps, wns_ps * RELAX_MARGIN)
    candidate = next_candidate(period_ps, wns_ps)
    if period_ps - candidate <= tolerance_ps:
        return "converged", period_ps
    return "continue", candidate


def check_probe_matches_request(requested_ps, probe_period_ps):
    """Guard against reading an artifact from a different period.

    A build that did not re-run leaves the previous period's numbers
    exactly where this loop expects the new ones, and the loop would
    then converge on evidence it never produced.
    """
    if abs(probe_period_ps - requested_ps) > 0.5:
        raise Fatal(
            "probe reports period %g ps but %g ps was asked for: the "
            "artifact is from a different build" % (probe_period_ps, requested_ps)
        )


def derive(read_probe, start_ps, max_iterations=6, tolerance_ps=2.0):
    """Run the fixed point, returning (winner_ps, status, history).

    read_probe(period_ps) -> probe text. Injected so the search is
    testable without a flow.
    """
    history = []
    period = start_ps
    winner = None
    status = "exhausted"
    for _ in range(max_iterations):
        probe_period, wns, paths = probe_reading(read_probe(period))
        check_probe_matches_request(period, probe_period)
        history.append(
            {
                "period_ps": period,
                "wns_reg2reg_ps": wns,
                "reg2reg_paths": paths,
                "closed": wns >= 0,
            }
        )
        if wns >= 0:
            winner = period
        status, nxt = step(period, wns, tolerance_ps, winner is not None)
        if status in ("converged", "overshot"):
            break
        period = nxt
    else:
        # The loop ran out of iterations with the period still moving:
        # the answer is the tightest period that closed, but it is not a
        # fixed point and must not be reported as one.
        status = "exhausted"
    if winner is None:
        raise Fatal(
            "the design did not close at any of the %d periods tried, "
            "the loosest being %g ps: relaxing is not finding a period "
            "this design meets" % (len(history), max(h["period_ps"] for h in history))
        )
    return winner, status, history


def _bazel_probe(bazel, target, artifact):
    def read(period_ps):
        subprocess.run([bazel, "build", target], check=True)
        with open(artifact) as f:
            return f.read()

    return read


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--constraints", required=True, help="the design's constraints.sdc")
    p.add_argument("--target", required=True, help="the design's _period bazel target")
    p.add_argument("--artifact", required=True, help="path the target writes")
    p.add_argument("--evidence", required=True, help="where to write the history JSON")
    p.add_argument("--bazel", default="bazelisk")
    p.add_argument("--max-iterations", type=int, default=6)
    p.add_argument("--tolerance-ps", type=float, default=2.0)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="derive and report, but leave the constraints file alone",
    )
    args = p.parse_args(argv)

    with open(args.constraints) as f:
        sdc = f.read()
    start = read_clk_period(sdc)

    def read(period_ps):
        with open(args.constraints) as fh:
            current = fh.read()
        with open(args.constraints, "w") as fh:
            fh.write(set_clk_period(current, int(period_ps)))
        return _bazel_probe(args.bazel, args.target, args.artifact)(period_ps)

    try:
        winner, status, history = derive(
            read, start, args.max_iterations, args.tolerance_ps
        )
    finally:
        # Whatever happened, the file must not be left at a period that
        # was only a candidate.
        with open(args.constraints) as fh:
            current = fh.read()
        with open(args.constraints, "w") as fh:
            fh.write(set_clk_period(current, start))

    if not args.dry_run:
        with open(args.constraints) as fh:
            current = fh.read()
        with open(args.constraints, "w") as fh:
            fh.write(set_clk_period(current, winner))

    evidence = {
        "start_ps": start,
        "winner_ps": winner,
        "status": status,
        "tolerance_ps": args.tolerance_ps,
        "history": history,
    }
    with open(args.evidence, "w") as fh:
        json.dump(evidence, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(
        "auto_period: %d -> %d ps (%s, %d builds)"
        % (start, winner, status, len(history))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
