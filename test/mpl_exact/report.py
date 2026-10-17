"""The study PR body's tables, from whatever results exist.

usage: report.py --dumps DIR [--bench results.csv] [--qor results.csv]
A section without data renders as "Not yet measured".
"""

import argparse
import collections
import csv
import glob
import json
import math
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def agreement(dumps):
    rows = []
    for d in sorted(glob.glob(os.path.join(dumps, "*", "problems.csv"))):
        design = os.path.basename(os.path.dirname(d))
        exact_path = os.path.join(os.path.dirname(d), "exact4.csv")
        if not os.path.exists(exact_path):
            continue
        problems = {r["id"]: r for r in csv.DictReader(open(d))}
        n = undecided = fits = nofit = rescued = disagree = 0
        sa = exact = 0.0
        slowest = 0.0
        for r in csv.DictReader(open(exact_path)):
            p = problems[r["tag"]]
            n += 1
            sa += float(p["sa_seconds"])
            exact += float(r["seconds"])
            slowest = max(slowest, float(r["seconds"]))
            placed = int(p["valid_runs"]) > 0
            if r["status"] == "undecided":
                undecided += 1
            elif r["status"] == "fits":
                fits += 1
                rescued += not placed
            else:
                nofit += 1
                disagree += placed
        rows.append(
            (design, n, fits, nofit, undecided, rescued, disagree, sa, exact, slowest)
        )
    if not rows:
        return "Not yet measured.\n"
    out = [
        "| design | problems | fit | do not fit | undecided | annealer "
        "missed | disagree | annealing s | exact s | slowest s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    total = [0] * 9
    for r in rows:
        out.append("| %s | %d | %d | %d | %d | %d | %d | %.1f | %.2f | %.2f |" % r)
        for i in range(8):
            total[i] += r[i + 1]
        total[8] = max(total[8], r[9])
    out.append(
        "| **all** | %d | %d | %d | %d | %d | %d | %.1f | %.2f | %.2f |" % tuple(total)
    )
    return "\n".join(out) + "\n"


def patience(dumps):
    files = glob.glob(os.path.join(dumps, "*", "mpl_dump.*.jsonl"))
    if not files:
        return "Not yet measured.\n"
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(HERE, "patience.py"),
            *files,
            "--patience",
            "200,400",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return "```\n" + r.stdout + "```\n"


def bench(path):
    if not path or not os.path.exists(path):
        return "Not yet measured.\n"
    runs = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in csv.DictReader(open(path)):
        if r["seconds"]:
            runs[r["design"]][r["arm"]].append(
                (float(r["seconds"]), float(r["macro_net_hpwl_um"] or 0))
            )
    out = [
        "| design | base s | new s | speedup | verdict | base HPWL um | "
        "new HPWL um | HPWL delta | runs |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    ratios = []
    for design in sorted(runs):
        b, n = runs[design]["base"], runs[design]["new"]
        if not b or not n:
            continue
        bs = [x[0] for x in b]
        ns = [x[0] for x in n]

        def fmt(v):
            m = statistics.mean(v)
            s = 2 * statistics.stdev(v) if len(v) > 1 else 0.0
            return "%.2f ± %.2f" % (m, s)

        bh, nh = b[0][1], n[0][1]
        ratio = statistics.mean(bs) / statistics.mean(ns)
        ratios.append(ratio)
        # Single-digit percent differences are not claimed.
        verdict = (
            "faster" if ratio >= 1 / 0.9 else "slower" if ratio <= 1 / 1.1 else "same"
        )
        out.append(
            "| %s | %s | %s | %.2fx | %s | %.0f | %.0f | %+.2f%% | "
            "%d/%d |"
            % (
                design,
                fmt(bs),
                fmt(ns),
                ratio,
                verdict,
                bh,
                nh,
                100 * (nh - bh) / bh if bh else 0,
                len(bs),
                len(ns),
            )
        )
    if ratios:
        geo = math.exp(statistics.mean(math.log(r) for r in ratios))
        out.append(
            "\nGeometric mean speedup of mpl: %.2fx over %d designs "
            "(± is 2σ over the runs).\n" % (geo, len(ratios))
        )
    return "\n".join(out) + "\n"


def qor(path):
    if not path or not os.path.exists(path):
        return "Not yet measured.\n"
    rows = collections.defaultdict(dict)
    for r in csv.DictReader(open(path)):
        rows[r["design"]][r["arm"]] = r
    out = [
        "| design | base WNS ps | new WNS ps | delta ps | base mpl s | " "new mpl s |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    deltas = []
    for design in sorted(rows):
        b, n = rows[design].get("base"), rows[design].get("new")
        if not b or not n:
            continue
        key = next((k for k in b if k.endswith("timing__setup__ws")), None)
        if not key or not b[key] or not n.get(key):
            continue
        bw, nw = float(b[key]), float(n[key])
        deltas.append(nw - bw)
        out.append(
            "| %s | %.1f | %.1f | %+.1f | %s | %s |"
            % (
                design,
                bw,
                nw,
                nw - bw,
                b.get("mpl_seconds", ""),
                n.get("mpl_seconds", ""),
            )
        )
    if deltas:
        better = sum(d > 0 for d in deltas)
        worse = sum(d < 0 for d in deltas)
        out.append(
            "\nWNS at global route, new minus base: median %+.1f ps; "
            "%d better, %d worse, %d equal over %d designs.\n"
            % (
                statistics.median(deltas),
                better,
                worse,
                len(deltas) - better - worse,
                len(deltas),
            )
        )
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dumps", required=True)
    parser.add_argument("--bench")
    parser.add_argument("--qor")
    args = parser.parse_args()
    if not glob.glob(os.path.join(args.dumps, "*", "problems.csv")):
        raise SystemExit("run the campaign first: no dumps in " + args.dumps)
    print("### The exact check against the annealer\n")
    print(agreement(args.dumps))
    print("### Early stop, replayed\n")
    print(patience(args.dumps))
    print("### mpl runtime and wirelength\n")
    print(bench(args.bench))
    print("### QoR at global route\n")
    print(qor(args.qor))


if __name__ == "__main__":
    main()
