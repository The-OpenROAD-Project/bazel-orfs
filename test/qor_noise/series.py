#!/usr/bin/env python3

"""Turn the rules history into per-(design, metric) transitions.

A transition is one recorded move of a threshold: the de-padded value
before, the value after, when it happened, and -- the part that decides
whether it means anything -- whether the design was re-targeted in the
interval since the previous recorded value.

Why transitions and not a time series of samples: ORFS runs
`genRuleFile.py` with `--tighten` and `--failing` and, as far as the
commit record shows, never with `--update`. So a threshold moves only
when the measurement beat the running record, or when it blew through
the padded bound. The sequence of stored values is a **ratchet**, not a
sample path, and every estimator downstream has to be built for that.

Each transition is classified from the direction of the move and the
metric's sense:

  * `tighten` -- the new value is better. Under `--tighten` this fires on
    any improvement at all, so a tighten is a *record*, and the step size
    is a record increment, not a deviation.
  * `failing` -- the new value is worse. Under `--failing` this can only
    fire once the measurement has exceeded the previous padded threshold,
    so for a 15%-padded metric a failing step means the design moved by
    more than 15% with no one having asked it to.

`retargeted` marks the transitions that crossed a commit touching the
design's own inputs -- config.mk, SDC, floorplan, RTL. Those steps are
intent, not noise, and no honest statistic may include them.
"""

import argparse
import collections
import csv
import sys

import depad


def load_history(path, metrics):
    """Read extract.py's CSV into {(platform, design, metric): [(t, commit, value)]}."""
    series = collections.defaultdict(list)
    with open(path) as fh:
        for row in csv.DictReader(fh):
            metric = row["metric"]
            if metrics and metric not in metrics:
                continue
            try:
                value = float(row["value"])
            except (TypeError, ValueError):
                continue  # "N/A", hashes, inf
            series[(row["platform"], row["design"], metric)].append(
                (int(row["unix_time"]), row["commit"], value)
            )
    for key in series:
        # First-parent log order is newest first; make it chronological.
        series[key].sort(key=lambda r: r[0])
    return series


def load_retargets(path):
    """Read events.py's CSV into {(platform, design): sorted [unix_time]}."""
    out = collections.defaultdict(list)
    with open(path) as fh:
        for row in csv.DictReader(fh):
            out[(row["platform"], row["design"])].append(int(row["unix_time"]))
    for key in out:
        out[key].sort()
    return out


def retargeted_between(times, lo, hi):
    """True if the design's own inputs changed in (lo, hi]."""
    import bisect

    i = bisect.bisect_right(times, lo)
    j = bisect.bisect_right(times, hi)
    return j > i


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", required=True)
    ap.add_argument("--retargets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--metrics",
        default=",".join(depad.HIGH_RESOLUTION),
        help="comma-separated metrics; default is the exactly-invertible, "
        "full-precision set",
    )
    args = ap.parse_args(argv)

    metrics = set(m for m in args.metrics.split(",") if m)
    series = load_history(args.history, metrics)
    retargets = load_retargets(args.retargets)

    kinds = collections.Counter()
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "platform",
                "design",
                "metric",
                "commit",
                "unix_time",
                "prev_unix_time",
                "before",
                "after",
                "rel_change",
                "kind",
                "retargeted",
            ]
        )
        for (platform, design, metric), points in sorted(series.items()):
            lower_better = metric in depad.LOWER_IS_BETTER
            times = retargets.get((platform, design), [])
            prev = None
            for when, commit, raw in points:
                value = depad.depad(metric, raw)
                if value is None:
                    continue
                if prev is not None:
                    pt, pv = prev
                    if value != pv and pv != 0:
                        better = value < pv if lower_better else value > pv
                        kind = "tighten" if better else "failing"
                        rt = retargeted_between(times, pt, when)
                        w.writerow(
                            [
                                platform,
                                design,
                                metric,
                                commit,
                                when,
                                pt,
                                f"{pv:.6g}",
                                f"{value:.6g}",
                                f"{(value - pv) / pv:.6g}",
                                kind,
                                int(rt),
                            ]
                        )
                        kinds[(kind, rt)] += 1
                prev = (when, value)

    for (kind, rt), n in sorted(kinds.items()):
        print(f"{kind:8s} retargeted={int(rt)}: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
