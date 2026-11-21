#!/usr/bin/env python3
"""Fit a design's rung 0 and 1 coefficients and limits to its measured
global routes, and write them as its calibration file (plan.py's
CALIBRATION_KEYS) with a report.

Input, points.json (paths relative to it):

  {"design": name, "pdk": pdk.json, "layers": {layer: {"share": s}},
   "clean_overflow": 0, "worker_gib": 0,
   "points": [{"name", "block": block.json, "netlist": netlist.json,
               "outline_um": [w, h], "sides": {"N": pins, ...},
               "measured": {"overflow", "wirelength_um", "grt_insts",
                            "grt_peak_gib", "period_ps"},
               "source"}]}

`outline_um` is the core the block routed in (else its die_rule), `sides`
the pins its flow put on each side (else the side is not measured), and
every measured value is optional but the overflow.

Fits, each recorded with the points it rests on:

  rent p, k               the median of the blocks' own bisection fits
  wire_demand / rent_wire wirelength_factor: the median of measured wire
                          over Donath's; limit: between the largest ratio
                          that routed clean and the smallest that did not
  rent_terminals, escape  limit, the same way
  tangled                 score_limit: the lowest GTL score that routed
                          clean against the highest that did not
  grt_capacity            grt_per_synth_inst: the largest measured ratio;
                          max_insts: worker_gib over the largest measured
                          peak bytes per instance
  pins_per_um             facing_track_spacing: between the tightest side
                          that routed clean and the loosest that did not

A limit is written only where the clean and the failing points separate
(clean: overflow at most clean_overflow); else the rung stays
unjudged and the report says why. The report gives per feature Kendall's
tau-b against the overflow, and the residuals of log10(1 + overflow)
fitted linearly on the feature. A point whose logic alone is near its
measured period (logic_bound) is marked: its period says nothing about
the floorplan, and only its overflow is fitted.

Stdlib only.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ladder as L  # noqa: E402

TOOL = "calibrate 1"
LOGIC_BOUND = 0.8


def median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def kendall_tau_b(xs, ys):
    """Kendall's tau-b of paired values; None under three pairs."""
    n = len(xs)
    if n < 3:
        return None
    conc = disc = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif dx * dy > 0:
                conc += 1
            else:
                disc += 1
    den = math.sqrt((conc + disc + tx) * (conc + disc + ty))
    return round((conc - disc) / den, 4) if den else None


def linear_residuals(xs, ys):
    n = len(xs)
    if n < 2:
        return None, None, []
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    a = my - b * mx
    return a, b, [round(y - (a + b * x), 4) for x, y in zip(xs, ys)]


def separate(rows, key, clean, higher_is_worse=True):
    """The limit between the clean and the failing points on a feature,
    geometric mean of the two nearest; None and why when they overlap."""
    ok = [r[key] for r in rows if r.get(key) is not None and r["overflow"] <= clean]
    bad = [r[key] for r in rows if r.get(key) is not None and r["overflow"] > clean]
    if not ok or not bad:
        return None, "needs a clean and a failing point (%d clean, %d failing)" % (
            len(ok),
            len(bad),
        )
    if higher_is_worse:
        lo, hi = max(ok), min(bad)
        if lo >= hi:
            return None, "clean up to %.4g, failing from %.4g: they overlap" % (lo, hi)
    else:
        hi, lo = min(ok), max(bad)
        if lo >= hi:
            return None, "clean down to %.4g, failing up to %.4g: they overlap" % (
                hi,
                lo,
            )
    return round(math.sqrt(lo * hi) if lo > 0 else (lo + hi) / 2, 4), None


def load_rel(base, path):
    if path is None:
        return None
    with open(os.path.join(base, path)) as f:
        return json.load(f)


def layer_tracks(pdk, shares):
    return {
        n: v["tracks_per_um"] * shares.get(n, {}).get("share", 1.0)
        for n, v in pdk["layers"].items()
        if v.get("routable")
    }


def measure(pt, block, nl, pdk, lt, p, k, tg=None):
    """The point's features at the design's p and k."""
    slot = pt.get("outline_um")
    m = pt["measured"]
    row = {"name": pt["name"], "block": block["block"], "overflow": m["overflow"]}
    wd = L.wire_demand(block, lt, p, 1.0, slot, nl)
    row["wire_um_donath"] = wd and wd["demand_um"]
    row["wire_ratio"] = wd and wd["ratio"]
    rt = L.rent_terminals(block, p, k, nl)
    row["rent_ratio"] = rt and rt["ratio"]
    if nl and nl["rent"].get("p") is not None:
        rw = L.wire_demand(block, lt, nl["rent"]["p"], 1.0, slot, nl)
        row["p"] = nl["rent"]["p"]
        row["rent_wire_um_donath"] = rw["demand_um"]
        row["rent_wire_ratio"] = rw["ratio"]
    wh = L.outline_um(block, slot)
    sides = pt.get("sides") or {}
    io = pt.get("io", pdk["io"])
    if wh and sides:
        w, h = wh
        spacing = {}
        escape = {}
        buses = (nl or {}).get("buses", {})
        bits = sum(b["bits"] for b in buses.values())
        breadth = (
            sum(b["bits"] * b["breadth_mean"] for b in buses.values()) / bits
            if bits
            else 1.0
        )
        for s, pins in sides.items():
            if not pins:
                continue
            length = w if s in "NS" else h
            layers = sorted(
                io["H" if s in "EW" else "V"], key=lambda n: pdk["order"].index(n)
            )
            spacing[s] = round(
                length * pdk["layers"][layers[0]]["tracks_per_um"] / pins, 4
            )
            if nl:
                d = L.perpendicular(s)
                t = sum(v for n, v in lt.items() if pdk["layers"][n]["dir"] == d)
                escape[s] = round(pins * breadth / (length * t), 4)
        row["side_spacing"] = spacing
        row["spacing_min"] = min(spacing.values()) if spacing else None
        row["escape"] = escape
        row["escape_max"] = max(escape.values()) if escape else None
    if tg:
        if tg["gtl"]:
            row["gtl_min"] = tg["gtl"][0]["score"]
            row["gtl_share"] = tg["gtl"][0]["cells_share"]
        row["long_share"] = tg["net_range"]["long_share"]
        row["weak_share"] = tg["contraction"].get("weak_share")
    st = block.get("netlist") or {}
    if m.get("grt_insts") and st.get("insts"):
        row["grt_per_synth_inst"] = round(m["grt_insts"] / st["insts"], 4)
    if m.get("grt_peak_gib") and (m.get("grt_insts") or st.get("insts")):
        row["grt_bytes_per_inst"] = round(
            m["grt_peak_gib"] * 2**30 / (m.get("grt_insts") or st["insts"]), 1
        )
    lg = block.get("logic")
    if lg and m.get("period_ps"):
        row["logic_ps"] = lg["ps"]
        row["logic_over_period"] = round(lg["ps"] / m["period_ps"], 4)
        row["logic_bound"] = lg["ps"] >= LOGIC_BOUND * m["period_ps"]
    return row


FEATURES = [
    ("wire_ratio", True),
    ("rent_wire_ratio", True),
    ("rent_ratio", True),
    ("escape_max", True),
    ("spacing_min", False),
    ("p", True),
    ("gtl_min", False),
    ("long_share", True),
    ("weak_share", True),
]


def calibrate(spec, base):
    pdk = load_rel(base, spec["pdk"]) if isinstance(spec["pdk"], str) else spec["pdk"]
    lt = layer_tracks(pdk, spec.get("layers", {}))
    clean = spec.get("clean_overflow", 0)
    pts = []
    for pt in spec["points"]:
        b = load_rel(base, pt["block"])
        nl = load_rel(base, pt.get("netlist"))
        tg = load_rel(base, pt.get("tangle"))
        pts.append((pt, b, nl, tg))
    names = [pt["name"] for pt, _, _, _ in pts]
    fits = [nl["rent"] for _, _, nl, _ in pts if nl and nl["rent"].get("p") is not None]
    p = median([f["p"] for f in fits]) or L.RENT_DEFAULT["p"]
    k = median([f["k"] for f in fits]) or L.RENT_DEFAULT["k"]
    rows = [measure(pt, b, nl, pdk, lt, p, k, tg) for pt, b, nl, tg in pts]
    cal = {}
    notes = {}

    def src(what, used):
        return "%s: calibrate.py on %s (%s)" % (
            spec["design"],
            ", ".join(used) if used else "no point",
            what,
        )

    if fits:
        cal["rent"] = {
            "p": round(p, 4),
            "k": round(k, 4),
            "source": src(
                "median of the blocks' bisection fits",
                [pt["name"] for pt, _, nl, _ in pts if nl and nl["rent"].get("p")],
            ),
        }
    for rung, key, um in (
        ("wire_demand", "wire_ratio", "wire_um_donath"),
        ("rent_wire", "rent_wire_ratio", "rent_wire_um_donath"),
    ):
        ws = [
            (r["name"], pt["measured"]["wirelength_um"] / r[um])
            for (pt, _, _, _), r in zip(pts, rows)
            if pt["measured"].get("wirelength_um") and r.get(um)
        ]
        factor = median([w for _, w in ws]) if ws else None
        sec = {}
        if factor:
            sec["wirelength_factor"] = round(factor, 4)
            for r in rows:
                if r.get(key) is not None:
                    r[key] = round(r[key] * factor, 4)
        lim, why = separate(rows, key, clean)
        if lim is not None:
            sec["limit"] = lim
        else:
            notes[rung] = why
        if sec:
            sec["source"] = src(
                "factor: measured wire over Donath's on %s; limit: clean against failing overflow"
                % (", ".join(n for n, _ in ws) or "none"),
                [r["name"] for r in rows if r.get(key) is not None],
            )
            cal[rung] = sec
    for rung, key, worse in (
        ("rent_terminals", "rent_ratio", True),
        ("escape", "escape_max", True),
    ):
        lim, why = separate(rows, key, clean, worse)
        if lim is not None:
            cal[rung] = {
                "limit": lim,
                "source": src(
                    "clean against failing overflow",
                    [r["name"] for r in rows if r.get(key) is not None],
                ),
            }
        else:
            notes[rung] = why
    lim, why = separate(rows, "spacing_min", clean, higher_is_worse=False)
    if lim is not None:
        cal["pins_per_um"] = {
            "facing_track_spacing": lim,
            "source": src(
                "tightest clean side against loosest failing side, tracks per pin on the lowest pin layer",
                [r["name"] for r in rows if r.get("spacing_min") is not None],
            ),
        }
    else:
        notes["pins_per_um"] = why
    lim, why = separate(rows, "gtl_min", clean, higher_is_worse=False)
    if lim is not None:
        cal["tangled"] = {
            "score_limit": lim,
            "source": src(
                "the most tangled cluster's GTL score, clean against failing overflow",
                [r["name"] for r in rows if r.get("gtl_min") is not None],
            ),
        }
    else:
        notes["tangled"] = why
    g = [r["grt_per_synth_inst"] for r in rows if r.get("grt_per_synth_inst")]
    bpi = [r["grt_bytes_per_inst"] for r in rows if r.get("grt_bytes_per_inst")]
    sec = {}
    if g:
        sec["grt_per_synth_inst"] = round(max(g), 4)
    if bpi and spec.get("worker_gib"):
        sec["max_insts"] = int(round(spec["worker_gib"] * 2**30 / max(bpi), 0))
    if sec:
        sec["source"] = src(
            "the largest measured grt/synthesis instance ratio; a worker's %s GiB over the "
            "largest measured grt peak bytes per instance" % spec.get("worker_gib"),
            [
                r["name"]
                for r in rows
                if r.get("grt_per_synth_inst") or r.get("grt_bytes_per_inst")
            ],
        )
        cal["grt_capacity"] = sec
    else:
        notes["grt_capacity"] = "no point measured grt instances or peak memory"

    stats = {}
    y = [math.log10(1 + r["overflow"]) for r in rows]
    for key, worse in FEATURES:
        sel = [
            (r[key], yy, r["name"]) for r, yy in zip(rows, y) if r.get(key) is not None
        ]
        if not sel:
            continue
        xs = [s[0] for s in sel]
        ys = [s[1] for s in sel]
        tau = kendall_tau_b(xs, ys)
        a, b, res = linear_residuals(xs, ys)
        stats[key] = {
            "n": len(sel),
            "tau_b": tau if worse or tau is None else round(-tau, 4),
            "fit": None if a is None else {"a": round(a, 4), "b": round(b, 4)},
            "residuals": dict(zip([s[2] for s in sel], res)),
        }
    report = {
        "tool": TOOL,
        "design": spec["design"],
        "points": rows,
        "missing": spec.get("missing", []),
        "stats": stats,
        "unjudged": notes,
        "calibration": cal,
    }
    return cal, report, names


def write_md(report, path):
    out = ["# Calibration: %s" % report["design"], ""]
    out += [
        "| point | overflow | wire | wire at p | p | Rent | escape | spacing | logic/period |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def f(v):
        return "" if v is None else str(v)

    for r in report["points"]:
        lb = f(r.get("logic_over_period")) + (
            " logic-bound" if r.get("logic_bound") else ""
        )
        out.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["name"],
                r["overflow"],
                f(r.get("wire_ratio")),
                f(r.get("rent_wire_ratio")),
                f(r.get("p")),
                f(r.get("rent_ratio")),
                f(r.get("escape_max")),
                f(r.get("spacing_min")),
                lb,
            )
        )
    out += [
        "",
        "Kendall's tau-b against log10(1 + overflow) (positive: the feature ranks the",
        "overflow; spacing counted inverted), and the residuals of a linear fit:",
        "",
        "| feature | n | tau-b | residuals |",
        "|---|---|---|---|",
    ]
    for k, s in report["stats"].items():
        out.append(
            "| %s | %d | %s | %s |"
            % (
                k,
                s["n"],
                f(s["tau_b"]),
                ", ".join("%s %s" % kv for kv in s["residuals"].items()),
            )
        )
    out += [
        "",
        "## Calibration written",
        "",
        "```json",
        json.dumps(report["calibration"], indent=1, sort_keys=True),
        "```",
        "",
    ]
    if report["unjudged"]:
        out += ["## Left unjudged", ""]
        out += ["- %s: %s" % kv for kv in sorted(report["unjudged"].items())]
        out.append("")
    if report["missing"]:
        out += (
            ["## Points missing", ""] + ["- %s" % m for m in report["missing"]] + [""]
        )
    with open(path, "w") as fp:
        fp.write("\n".join(out))


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("points", help="points.json")
    ap.add_argument(
        "--calibration", required=True, help="the calibration file to write"
    )
    ap.add_argument("--report", help="report.json to write")
    ap.add_argument("--report-md", help="report.md to write")
    ap.add_argument(
        "--keep",
        help="an existing calibration file whose sections the fit does not write are kept",
    )
    args = ap.parse_args(argv)
    with open(args.points) as fp:
        spec = json.load(fp)
    cal, report, _ = calibrate(spec, os.path.dirname(os.path.abspath(args.points)))
    if args.keep:
        with open(args.keep) as fp:
            cal = dict(json.load(fp), **cal)
    with open(args.calibration, "w") as fp:
        json.dump(cal, fp, indent=1, sort_keys=True)
        fp.write("\n")
    if args.report:
        with open(args.report, "w") as fp:
            json.dump(report, fp, indent=1, sort_keys=True)
            fp.write("\n")
    if args.report_md:
        write_md(report, args.report_md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
