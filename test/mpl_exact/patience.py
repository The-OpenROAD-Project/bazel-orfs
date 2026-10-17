"""Replay annealing runs from their improvement traces under an early stop.

A run stops at the first stretch of `patience` steps without a new best
cost. The trace is exact: the annealer's random sequence up to that point is
unchanged, so the cost it would return is the best cost reached before the
stop. Prints, per patience, the fraction of steps saved and the relative
cost loss (median, 95th percentile, worst) of the stopped run against the
full run, per kind of problem.

usage: patience.py <dump.jsonl>... [--patience 50,100,...]
"""

import argparse
import collections
import json
import statistics


def replay(run, patience):
    steps = run["steps"]
    best = None
    last = 0
    for step, cost in run["improvements"]:
        if step - last > patience:
            return last + patience, best
        best, last = cost, step
    stop = min(steps, last + patience)
    return stop, best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dumps", nargs="+")
    parser.add_argument("--patience", default="25,50,100,200,400")
    args = parser.parse_args()
    runs = collections.defaultdict(list)
    for path in args.dumps:
        for line in open(path):
            r = json.loads(line)
            if r["improvements"]:
                runs[r["tag"].split(":")[0]].append(r)
    for kind, rs in sorted(runs.items()):
        full_steps = sum(r["steps"] for r in rs)
        print(f"{kind}: {len(rs)} runs")
        for p in map(int, args.patience.split(",")):
            steps = 0
            losses = []
            before_first = 0
            for r in rs:
                stop, best = replay(r, p)
                steps += stop
                final = r["improvements"][-1][1]
                if best is None:
                    # Stopped before the first improvement: the initial
                    # cost, not in the trace, is returned.
                    before_first += 1
                    continue
                losses.append((best - final) / abs(final) if final else 0.0)
            losses.sort()
            print(
                f"  patience {p:4d}: steps {100 * steps / full_steps:5.1f}% "
                f"loss median {100 * statistics.median(losses):.2f}% "
                f"p95 {100 * losses[int(0.95 * (len(losses) - 1))]:.2f}% "
                f"worst {100 * losses[-1]:.2f}% "
                f"stopped-before-first-improvement {before_first}"
            )


if __name__ == "__main__":
    main()
