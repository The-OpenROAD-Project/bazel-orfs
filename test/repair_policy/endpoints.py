#!/usr/bin/env python3
"""Phase 0 of the yield study: what each endpoint visit of the setup sweep bought.

Reads the [RSZ-ENDPOINT] trace (patches/0078) the campaign stored per
repair_timing call and answers, per design and flow step:

  * the yield table: visits grouped by how they ended, with the passes,
    seconds and TNS they took and bought;
  * concentration: how much of the phase's TNS gain the top tenth of
    visits holds, and what share of passes bought nothing;
  * order: the passes needed for 90% of the gain in the sweep's own
    (worst-first) order against the same visits sorted by gain per pass,
    which is the most a yield order could save;
  * probe: if every endpoint were given k passes first, the share of the
    gain whose first improvement falls inside k, and what those probes
    would cost -- whether a cheap triage can find the paying endpoints;
  * the jackpot: the visits that hold the gain, with their position in
    the sweep, entry slack and first improving pass.

    endpoints.py --results DIR --arm base-p00670068t [--designs ...] [--out DIR]

With --out, writes one CSV of every visit and a cumulative-gain figure
per design and step.
"""

import argparse
import csv
import glob
import json
import os
import sys

PROBES = (1, 2, 3, 5, 10, 20)
STEPS_WITH_SETUP = ("2_1_floorplan", "4_1_cts", "5_1_grt")


def load_arm(results_dir, arm):
    out = {}
    for path in sorted(glob.glob(os.path.join(results_dir, "*_full_{}_r*.json".format(arm)))):
        with open(path) as handle:
            record = json.load(handle)
        out.setdefault(record["design"], record)
    return out


def visits(record, step):
    """All traced visits of the step's setup calls, with gains derived.

    gain: TNS bought by the visit in ps (positive is better); egain: the
    endpoint's own slack gain; per: gain per pass.
    """
    got = record["substeps"].get(step) or {}
    out = []
    for call_index, ends in enumerate(got.get("repair_endpoints") or []):
        kind = got["repair"][call_index]["kind"]
        for e in ends:
            v = dict(e)
            v["call"] = call_index
            v["kind"] = kind
            v["gain"] = e["tns_out"] - e["tns_in"]
            v["egain"] = e["slack_out"] - e["slack_in"]
            v["per"] = v["gain"] / e["passes"] if e["passes"] else 0.0
            out.append(v)
    return out


def fmt(v, d=1):
    if v is None:
        return "–"
    if isinstance(v, float):
        return "{:.{d}f}".format(v, d=d)
    return str(v)


def yield_table(vs):
    """Visits by exit reason: count, passes, seconds, TNS gain."""
    total_gain = sum(v["gain"] for v in vs) or 1.0
    total_passes = sum(v["passes"] for v in vs) or 1
    by = {}
    for v in vs:
        by.setdefault((v["phase"], v["exit"]), []).append(v)
    lines = [
        "| phase | exit | visits | passes | of passes | seconds | TNS gained (ps) | of gain | gain/pass |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (phase, exit_), group in sorted(by.items(), key=lambda kv: -sum(v["gain"] for v in kv[1])):
        passes = sum(v["passes"] for v in group)
        gain = sum(v["gain"] for v in group)
        lines.append("| {} | {} | {} | {} | {:.0f}% | {:.1f} | {:.0f} | {:.0f}% | {:.1f} |".format(
            phase, exit_, len(group), passes, 100.0 * passes / total_passes,
            sum(v["s"] for v in group), gain, 100.0 * gain / total_gain,
            gain / passes if passes else 0.0))
    return "\n".join(lines)


def concentration(vs):
    gains = sorted((v["gain"] for v in vs), reverse=True)
    total = sum(gains) or 1.0
    top = max(1, len(gains) // 10)
    zero_passes = sum(v["passes"] for v in vs if v["gain"] <= 0)
    passes = sum(v["passes"] for v in vs) or 1
    return {
        "visits": len(vs),
        "top10_share": 100.0 * sum(gains[:top]) / total,
        "top10_n": top,
        "paying": sum(1 for g in gains if g > 0),
        "zero_pass_share": 100.0 * zero_passes / passes,
        "total_gain": sum(gains),
        "total_passes": passes,
    }


def passes_for(vs, share, key):
    """Passes spent before `share` of the total gain is reached, visiting in `key` order."""
    order = sorted(vs, key=key)
    total = sum(v["gain"] for v in vs)
    if total <= 0:
        return None
    got = 0.0
    spent = 0
    for v in order:
        spent += v["passes"]
        got += v["gain"]
        if got >= share * total:
            return spent
    return spent


def order_table(vs):
    total_passes = sum(v["passes"] for v in vs) or 1
    sweep = passes_for(vs, 0.9, lambda v: (v["call"], v["pass0"]))
    yield_order = passes_for(vs, 0.9, lambda v: -v["per"])
    return sweep, yield_order, total_passes


def probe_table(vs):
    """Share of gain found by a k-pass probe, and the probe's cost."""
    total_gain = sum(v["gain"] for v in vs if v["gain"] > 0) or 1.0
    total_passes = sum(v["passes"] for v in vs) or 1
    lines = ["| probe passes k | visits improving within k | of gain held | probe cost, of all passes |",
             "| ---: | ---: | ---: | ---: |"]
    for k in PROBES:
        found = [v for v in vs if v["gain"] > 0 and 0 < v["gain1"] <= k]
        cost = sum(min(v["passes"], k) for v in vs)
        lines.append("| {} | {} | {:.0f}% | {:.0f}% |".format(
            k, len(found), 100.0 * sum(v["gain"] for v in found) / total_gain,
            100.0 * cost / total_passes))
    return "\n".join(lines)


def jackpot_table(vs, n=8):
    top = sorted(vs, key=lambda v: -v["gain"])[:n]
    lines = ["| rank | phase | sweep index | started at pass | passes | first gain at | entry slack | exit slack | TNS gained | exit |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for i, v in enumerate(top, 1):
        lines.append("| {} | {} | {}/{} | {} | {} | {} | {:.1f} | {:.1f} | {:.0f} | {} |".format(
            i, v["phase"], v["idx"], v["of"], v["pass0"], v["passes"], v["gain1"] or "–",
            v["slack_in"], v["slack_out"], v["gain"], v["exit"]))
    return "\n".join(lines)


def spearman(xs, ys):
    def ranks(a):
        order = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and a[order[j + 1]] == a[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0 + 1
            i = j + 1
        return r
    n = len(xs)
    if n < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def predictors(vs):
    """Rank correlation of a visit's gain with what is known before it starts."""
    gains = [v["gain"] for v in vs]
    return {
        "entry slack (more negative first)": spearman([-v["slack_in"] for v in vs], gains),
        "sweep position (earlier first)": spearman([-v["idx"] for v in vs], gains),
        "path depth (deeper first)": spearman([v["depth"] for v in vs], gains),
        "candidates generated in the visit": spearman([v["cand"] for v in vs], gains),
    }


def report(design, step, vs):
    c = concentration(vs)
    sweep, yo, total = order_table(vs)
    lines = ["### {} {}".format(design, step), ""]
    lines.append("{} visits, {} paying, {:.0f} ps of TNS gained over {} passes. "
                 "The top {} visits hold {:.0f}% of the gain; {:.0f}% of passes bought nothing.".format(
                     c["visits"], c["paying"], c["total_gain"], c["total_passes"], c["top10_n"],
                     c["top10_share"], c["zero_pass_share"]))
    if sweep is not None:
        lines.append("Passes to 90% of the gain: {} in sweep order, {} if the same visits ran best gain-per-pass first ({:.0f}% and {:.0f}% of the phase).".format(
            sweep, yo, 100.0 * sweep / total, 100.0 * yo / total))
    lines += ["", yield_table(vs), "", probe_table(vs), "", jackpot_table(vs), ""]
    lines.append("Rank correlation of a visit's TNS gain with what is known before it: "
                 + "; ".join("{} {}".format(k, fmt(v, 2)) for k, v in predictors(vs).items()) + ".")
    lines.append("")
    return "\n".join(lines)


def write_csv(path, design, step, vs):
    keys = ["design", "step", "call", "kind", "phase", "idx", "of", "pass0", "pass1", "passes", "s",
            "slack_in", "slack_out", "wns_in", "wns_out", "tns_in", "tns_out", "gain", "egain",
            "gain1", "gainN", "depth", "cand", "att", "acc", "buf", "clone", "sizeup", "sizeupm",
            "sizedn", "swap", "vt", "unbuf", "split", "reroute", "exit", "end"]
    new = not os.path.exists(path)
    with open(path, "a", newline="") as handle:
        w = csv.writer(handle)
        if new:
            w.writerow(keys)
        for v in vs:
            row = dict(v, design=design, step=step)
            w.writerow([row.get(k) for k in keys])


def figure(out, design, step, vs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    total = sum(v["gain"] for v in vs)
    if total <= 0:
        return None
    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    for label, key, color in (("sweep order (worst slack first)", lambda v: (v["call"], v["pass0"]), "#2a78d6"),
                              ("same visits, best gain per pass first", lambda v: -v["per"], "#eb6834")):
        xs, ys, sp, g = [0], [0.0], 0, 0.0
        for v in sorted(vs, key=key):
            sp += v["passes"]
            g += v["gain"]
            xs.append(sp)
            ys.append(100.0 * g / total)
        ax.step(xs, ys, where="post", color=color, linewidth=2, label=label)
    ax.set_xlabel("passes spent", color="#0b0b0b", fontsize=9)
    ax.set_ylabel("share of the phase's TNS gain (%)", color="#0b0b0b", fontsize=9)
    ax.set_title("{} {}: what the order of the sweep costs".format(design, step), fontsize=10, loc="left")
    ax.set_facecolor("#fcfcfb")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.yaxis.grid(True, color="#e1e0d9", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    name = "order_{}_{}.png".format(design.replace("/", "+"), step)
    fig.savefig(os.path.join(out, name))
    plt.close(fig)
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--arm", default="base-p00670068t")
    parser.add_argument("--designs", nargs="*")
    parser.add_argument("--steps", nargs="*", default=list(STEPS_WITH_SETUP))
    parser.add_argument("--out", help="directory for visits.csv and the figures")
    args = parser.parse_args()
    arm = load_arm(args.results, args.arm)
    designs = args.designs or sorted(arm)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        csv_path = os.path.join(args.out, "visits.csv")
        if os.path.exists(csv_path):
            os.remove(csv_path)
    for design in designs:
        record = arm.get(design)
        if not record:
            sys.stdout.write("{}: not measured\n".format(design))
            continue
        for step in args.steps:
            vs = visits(record, step)
            if not vs:
                continue
            sys.stdout.write(report(design, step, vs) + "\n")
            if args.out:
                write_csv(csv_path, design, step, vs)
                name = figure(args.out, design, step, vs)
                if name:
                    sys.stdout.write("wrote {}\n\n".format(os.path.join(args.out, name)))


if __name__ == "__main__":
    main()
