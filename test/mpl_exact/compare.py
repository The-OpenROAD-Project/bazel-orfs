"""Join mpl's annealer outcome with the exact check, per problem.

usage: compare.py <problems.csv> <exact.csv>
Prints a disagreement line for every problem where the annealer found a
valid result and the exact check says it does not fit (a model bug or a
solver bug, never acceptable), and a summary.
"""

import csv
import sys


def main():
    problems = {r["id"]: r for r in csv.DictReader(open(sys.argv[1]))}
    rows = list(csv.DictReader(open(sys.argv[2])))
    counts = {}
    bad = 0
    exact_total = sa_total = 0.0
    for r in rows:
        p = problems[r["tag"]]
        sa_valid = int(p["valid_runs"]) > 0
        key = (
            p["tag"].split(":")[0],
            "sa_valid" if sa_valid else "sa_invalid",
            r["status"],
        )
        counts[key] = counts.get(key, 0) + 1
        exact_total += float(r["seconds"])
        sa_total += float(p["sa_seconds"])
        if sa_valid and r["status"] == "does_not_fit":
            bad += 1
            print(
                f"DISAGREE {r['tag']} {p['tag']} {p['width']}x{p['height']} "
                f"cause={r['cause']}"
            )
    for key in sorted(counts):
        print("%-16s %-11s %-13s %d" % (*key, counts[key]))
    print(
        f"problems={len(rows)} disagreements={bad} "
        f"sa_seconds={sa_total:.2f} exact_seconds={exact_total:.3f}"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
