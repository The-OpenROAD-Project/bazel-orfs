"""The retiming study (OpenROAD #12304): collect, report and plot.

    python3 -I test/repair_noise/retime.py collect   # from bazel outputs
    python3 -I test/repair_noise/retime.py report    # PR body tables
    bazelisk run //test/repair_noise:retime_plot     # the figures

`collect` asks bazel where the outputs are (cquery, exact paths, no
globbing in output trees) and writes docs/studies/retime/results.json.
`report` and `plot` read only that file, floors.json (odb-debug's
floor_retime on each base arm's grt) and noise.json (the QoR dashboard's
master history, as ORFS #4893); a design or arm missing renders as "not
yet measured".

Arms, all but seed2 from the base arm's floorplan: base and seed2 are the
ORFS #4893 arms; rt sets PLACE_RETIME=1 (retime in global placement, as
ORFS draft #4904 runs it); rt_seed2 is rt with the seed of seed2, a
second draw of the effect against seed2. fin_base and fin_rt run base and
rt to the end of the flow on a subset.
"""

import json
import math
import os
import re
import subprocess
import sys

from two_pass import binom_tail, design_period_ps, elapsed_s, first_error, took

PANEL = [
    "asap7/gcd",
    "asap7/ibex",
    "asap7/ethmac",
    "asap7/swerv_wrapper",
    "asap7/mock-alu",
    "asap7/tinyRocket",
    "asap7/jpeg",
    "nangate45/black_parrot",
    "nangate45/ariane133",
    "nangate45/swerv_wrapper",
    "nangate45/tinyRocket",
    "nangate45/jpeg",
    "sky130hd/microwatt",
    "sky130hd/ibex",
    "sky130hd/riscv32i",
    "sky130hd/aes",
    "sky130hd/jpeg",
    "sky130hs/jpeg",
    "gf180/ibex",
    "gf180/jpeg",
]
FINAL = [
    "asap7/gcd",
    "asap7/ibex",
    "asap7/tinyRocket",
    "nangate45/tinyRocket",
    "sky130hd/aes",
    "sky130hs/jpeg",
]
ARMS = ["base", "seed2", "rt", "rt_seed2"]
# (name, arm, reference): the effects tested against the noise floor
COMPARISONS = [
    ("seed2", "seed2", "base"),
    ("rt", "rt", "base"),
    ("rt_seed2", "rt_seed2", "seed2"),
]
CONTROL_WIDTHS = [4, 8, 16, 32]
CONTROL_PERIOD_PS = 250.0
CONTROL_STAGES = 3
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.path.dirname(
    os.path.dirname(HERE)
)
DOCS = os.path.join(ROOT, "docs", "studies", "retime")
RESULTS = os.path.join(DOCS, "results.json")
NOISE = os.path.join(DOCS, "noise.json")
FLOORS = os.path.join(DOCS, "floors.json")
DASH = {"nangate45/black_parrot": "nangate45/bp"}


def variant(key):
    return key.replace("/", "_").replace("-", "_")


def unit_ps(key):
    return 1.0 if key.startswith("asap7") else 1000.0


# ------------------------------------------------------------- log parsing

CENSUS = re.compile(r"^RETIME_CENSUS (.*)$")
ROUND = re.compile(
    r"^\s*(start|\d+)\s*\|\s*(\d*)\s*\|\s*(\d*)\s*\|\s*(\d*)\s*\|"
    r"\s*(-?[\d.]+)\s*\|\s*(-?[\d.]+)\s*\|\s*(\d+)\s*$"
)
TOTALS = re.compile(
    r"\[INFO RET-0053\] Retime: slides (\d+), rounds (\d+), WNS (-?[\d.]+), "
    r"TNS (-?[\d.]+), registers (\d+), placed (\d+), resized (\d+)\."
)
GRAPH = re.compile(
    r"\[INFO RET-0014\] Retiming graph: (\d+) gates, (\d+) edges, (\d+) "
    r"registers, (\d+) pinned gates, (\d+) fenced registers\."
)


def parse_retime_log(path):
    """What retime said in a 3_3_place_gp.log: census, rounds, totals.

    Returns None when the log has no `retime` command; {"error": ...}
    when the stage stopped on an error.
    """
    if not path or not os.path.exists(path):
        return None
    out = {"rounds": []}
    ran = False
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.strip() == "retime":
                ran = True
            m = CENSUS.match(line)
            if m:
                out["census"] = {
                    k: int(v) for k, v in (x.split("=") for x in m.group(1).split())
                }
            m = GRAPH.search(line)
            if m:
                out["graph"] = dict(
                    zip(
                        ["gates", "edges", "registers", "pinned", "fenced"],
                        map(int, m.groups()),
                    )
                )
            m = ROUND.match(line)
            if m and ran:
                out["rounds"].append(
                    {
                        "round": 0 if m.group(1) == "start" else int(m.group(1)),
                        "kept": int(m.group(4) or 0),
                        "wns": float(m.group(5)),
                        "tns": float(m.group(6)),
                        "registers": int(m.group(7)),
                    }
                )
            m = TOTALS.search(line)
            if m:
                out["totals"] = dict(
                    zip(
                        [
                            "slides",
                            "rounds",
                            "wns",
                            "tns",
                            "registers",
                            "placed",
                            "resized",
                        ],
                        [float(x) if "." in x else int(x) for x in m.groups()],
                    )
                )
            if line.startswith("[ERROR ") and "error" not in out:
                out["error"] = line.strip()
    if not ran and "error" not in out:
        return None
    out["retime_s"] = took(path, "retime")
    return out


# ------------------------------------------------------------- statistics


def verdicts(results):
    """Per comparison: z per design, calibrated Z, sign test.

    z = Δperiod / (√2 σ); σ is scaled by the RMS of seed2's z (at least
    1), as ORFS #4893's decision rule does. Negative is better.
    """
    zs = {c: [] for c, _, _ in COMPARISONS}
    for r in results:
        s = r.get("sigma_ps")
        if not s:
            continue
        for c, arm, ref in COMPARISONS:
            b = r["arms"].get(ref, {}).get("period_ps")
            p = r["arms"].get(arm, {}).get("period_ps")
            if b is None or p is None:
                continue
            d = p - b
            zs[c].append((r["key"], d, d / (math.sqrt(2) * s), 100 * d / b))
    seed = [z for _, _, z, _ in zs["seed2"]]
    k = max(1.0, math.sqrt(sum(z * z for z in seed) / len(seed))) if seed else 1.0
    out = {"sigma_scale": k}
    for c, _, _ in COMPARISONS:
        l = zs[c]
        if not l:
            out[c] = None
            continue
        zc = [z / k for _, _, z, _ in l]
        better = sum(1 for _, d, _, _ in l if d < 0)
        worse = sum(1 for _, d, _, _ in l if d > 0)
        pct = sorted(p for _, _, _, p in l)
        out[c] = {
            "n": len(l),
            "Z": sum(zc) / math.sqrt(len(zc)),
            "better": better,
            "worse": worse,
            "p_better": binom_tail(len(l), better),
            "mean_pct": sum(pct) / len(pct),
            "median_pct": pct[len(pct) // 2],
            "min_pct": pct[0],
            "max_pct": pct[-1],
            "per_design": {
                key: {"delta_ps": d, "z": z / k, "pct": p} for key, d, z, p in l
            },
        }
    return out


def verdict_word(v):
    if v is None:
        return "not yet measured"
    if v["Z"] < -2 and v["better"] > v["n"] / 2:
        return "better, above the floor"
    if v["Z"] > 2 and v["worse"] > v["n"] / 2:
        return "worse, above the floor"
    return "within the floor"


def headroom_pct(floor_row):
    """The most any retiming could win at grt, % of the period (floors.json)."""
    if not floor_row or floor_row.get("floor") is None or not floor_row.get("period"):
        return None
    return 100.0 * (floor_row["period"] - floor_row["floor"]) / floor_row["period"]


# ----------------------------------------------------------------- collect


def _bazel(args):
    return subprocess.run(
        ["bazelisk"] + args, capture_output=True, text=True, cwd=ROOT, check=True
    ).stdout.split()


def _cquery(targets, groups="logs,default"):
    out = _bazel(
        [
            "cquery",
            "--keep_going",
            "--output=files",
            "--output_groups=" + groups,
            "set(%s)" % " ".join(targets),
        ]
    )
    return [os.path.join(ROOT, f) for f in out]


def _metrics(path):
    if path and os.path.exists(path):
        return json.load(open(path))
    return None


def collect_control():
    rows = []
    for w in CONTROL_WIDTHS:
        pre = "pipe_mult_inv" if w == 32 else "pipe_mult_w%d" % w
        row = {"width": w}
        for a in ("base", "retime"):
            t = "//test/retime_ctl:%s_%s" % (pre, a)
            files = _cquery([t + "_grt_report", t + "_place"])
            rep = [f for f in files if f.endswith("_grt_report.json")]
            m = _metrics(rep[0] if rep else None)
            arm = {}
            if m:
                arm["period_ps"] = CONTROL_PERIOD_PS - m["globalroute__timing__setup__ws"]
                arm["area_um2"] = m.get("globalroute__design__instance__area__stdcell")
            gp = [f for f in files if f.endswith("/3_3_place_gp.log")]
            if a == "retime" and gp:
                arm["retime"] = parse_retime_log(gp[0])
            row[a] = arm
        rows.append(row)
    return rows


def collect():
    noise = {}
    if os.path.exists(NOISE):
        for n in json.load(open(NOISE)):
            noise["%s/%s" % (n["platform"], n["design"])] = n
    labels = _bazel(
        ["query", "attr(name, '_base_grt$', //test/repair_noise:all)"]
    )
    results = []
    for key in PANEL:
        v = variant(key)
        base = [l for l in labels if l.endswith("_%s_base_grt" % v)]
        if not base:
            continue
        top = base[0].split(":")[1][: -len("_%s_base_grt" % v)]
        pre = "//test/repair_noise:%s_%s_" % (top, v)
        targets = []
        for a in ARMS:
            targets += [pre + a + "_grt_report", pre + a + "_place", pre + a + "_grt"]
        if key in FINAL:
            for a in ("fin_base", "fin_rt"):
                targets += [pre + a + "_final_report", pre + a + "_place"]
        files = _cquery(targets)
        row = {"key": key, "arms": {}}
        for a in ARMS + (["fin_base", "fin_rt"] if key in FINAL else []):
            d = "/%s_%s/" % (v, a)
            final = a.startswith("fin_")
            suffix = "_%s_%s_%s_report.json" % (v, a, "final" if final else "grt")
            rep = [f for f in files if f.endswith(suffix)]
            m = _metrics(rep[0] if rep else None)
            logs = {
                os.path.basename(f): f for f in files if d in f and f.endswith(".log")
            }
            arm = {}
            if m:
                if final:
                    for stage in ("finish", "detailedroute"):
                        p = design_period_ps(m, stage)
                        if p is not None:
                            arm["period_ps"] = p
                            break
                else:
                    arm["period_ps"] = design_period_ps(m)
                    arm["area"] = m.get("globalroute__design__instance__area__stdcell")
                    arm["hold_ws"] = m.get("globalroute__timing__hold__ws")
                    arm["cells"] = m.get("globalroute__design__instance__count__stdcell")
            arm["gpl_s"] = elapsed_s(logs.get("3_3_place_gp.log"))
            rt = parse_retime_log(logs.get("3_3_place_gp.log"))
            if rt is not None:
                arm["retime"] = rt
            if arm.get("period_ps") is not None:
                row["arms"][a] = arm
            else:
                err = (rt or {}).get("error") or first_error(
                    [logs.get(n) for n in sorted(logs)]
                )
                if err:
                    row.setdefault("failed", {})[a] = err
                if rt is not None:
                    row["arms"][a] = arm
        n = noise.get(DASH.get(key, key))
        row["sigma_ps"] = n["sigma_ps"] * unit_ps(key) if n else None
        results.append(row)
    out = {"designs": results, "control": collect_control()}
    os.makedirs(DOCS, exist_ok=True)
    with open(RESULTS, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %d designs to %s" % (len(results), os.path.relpath(RESULTS, ROOT)))


# ------------------------------------------------------------------ report


def _f(x, fmt="{:,.0f}"):
    return "–" if x is None else fmt.format(x)


def _load():
    if not os.path.exists(RESULTS):
        raise SystemExit("run the campaign, then `retime.py collect`")
    data = json.load(open(RESULTS))
    floors = {f["key"]: f for f in json.load(open(FLOORS))} if os.path.exists(FLOORS) else {}
    return data, floors


def render(data, floors):
    results = data["designs"]
    byk = {r["key"]: r for r in results}
    v = verdicts(results)
    L = ["### Verdicts\n"]
    L.append(
        "| Effect | Against | Z (calibrated) | Better / worse | p (sign, better) | Mean / median Δ period | Range | Verdict |"
    )
    L.append("|---|---|---:|---:|---:|---:|---:|---|")
    for c, arm, ref in COMPARISONS:
        x = v[c]
        if x is None:
            L.append("| %s | %s | | | | | | not yet measured |" % (c, ref))
            continue
        L.append(
            "| %s | %s | %+.2f | %d / %d | %.2f | %+.2f%% / %+.2f%% | %+.1f%% … %+.1f%% | %s |"
            % (
                c,
                ref,
                x["Z"],
                x["better"],
                x["worse"],
                x["p_better"],
                x["mean_pct"],
                x["median_pct"],
                x["min_pct"],
                x["max_pct"],
                verdict_word(x),
            )
        )
    L.append("\nσ scaled by the seed arm's RMS z: ×%.2f.\n" % v["sigma_scale"])

    L.append("### Period at grt per design\n")
    L.append(
        "Δ in ps; bold where |z| > 2 on the calibrated σ. Headroom: the most any"
        " retiming could win on base's grt (odb-debug `floor_retime`).\n"
    )
    L.append(
        "| Design | Base (ps) | σ (ps) | Headroom | seed2 | rt | rt_seed2 − seed2 | Slides | Registers |"
    )
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key in PANEL:
        r = byk.get(key)
        if not r or "base" not in r["arms"]:
            L.append("| %s | not yet measured | | | | | | | |" % key)
            continue
        cells = []
        for c, arm, _ in COMPARISONS:
            pd = (v.get(c) or {}).get("per_design", {}).get(key)
            if pd is None:
                cells.append("failed" if arm in r.get("failed", {}) else "–")
                continue
            s = "%+.0f" % pd["delta_ps"]
            cells.append("**%s**" % s if abs(pd["z"]) > 2 else s)
        rt = r["arms"].get("rt", {}).get("retime") or {}
        tot = rt.get("totals") or {}
        rounds = rt.get("rounds") or []
        regs = (
            "%s → %s" % (_f(rounds[0]["registers"]), _f(tot.get("registers")))
            if rounds and tot
            else "–"
        )
        sig = r["sigma_ps"] * v["sigma_scale"] if r.get("sigma_ps") else None
        L.append(
            "| %s | %s | %s | %s | %s | %s | %s |"
            % (
                key,
                _f(r["arms"]["base"]["period_ps"]),
                _f(sig),
                _f(headroom_pct(floors.get(key)), "{:.0f}%"),
                " | ".join(cells),
                _f(tot.get("slides")),
                regs,
            )
        )
    for key in PANEL:
        for a, err in sorted(((byk.get(key) or {}).get("failed") or {}).items()):
            L.append("- %s, %s failed: `%s`" % (key, a, err))

    L.append("\n### To the end of the flow\n")
    L.append("| Design | Base grt (ps) | rt Δ at grt | Base final (ps) | rt Δ at final |")
    L.append("|---|---:|---:|---:|---:|")
    for key in FINAL:
        r = byk.get(key) or {"arms": {}}
        a = r["arms"]
        bg, rg = a.get("base", {}).get("period_ps"), a.get("rt", {}).get("period_ps")
        bf = a.get("fin_base", {}).get("period_ps")
        rf = a.get("fin_rt", {}).get("period_ps")
        L.append(
            "| %s | %s | %s | %s | %s |"
            % (
                key,
                _f(bg),
                _f(rg - bg if bg and rg else None, "{:+,.0f}"),
                _f(bf),
                _f(rf - bf if bf and rf else None, "{:+,.0f}"),
            )
        )

    L.append("\n### Which registers retime may move\n")
    L.append(
        "From the RETIME_CENSUS line (study instrumentation, patch 0262) of each rt arm:"
        " every register of the block, by the first reason retime cannot move it."
        " Outside the graph: registers retime does not model as movable (asynchronous"
        " set or reset, latches, negative edge, scan, memories and macros).\n"
    )
    cols = ["sequential", "outside_graph", "movable", "fenced", "sdc", "dont_touch", "shared_net", "constant"]
    L.append("| Design | " + " | ".join(cols) + " |")
    L.append("|---|" + "---:|" * len(cols))
    for key in PANEL:
        c = (((byk.get(key) or {}).get("arms", {}).get("rt") or {}).get("retime") or {}).get("census")
        if not c:
            continue
        L.append("| %s | %s |" % (key, " | ".join(_f(c.get(k)) for k in cols)))

    L.append("\n### The positive control\n")
    L.append(
        "`test/retime_ctl/pipe_mult.sv`: a W × W multiplier with %d empty register stages"
        " in front of it, an inverter between each port and its first register, %d ps"
        " clock, asap7. Ideal retiming spreads the multiplier over %d cycles.\n"
        % (CONTROL_STAGES, CONTROL_PERIOD_PS, CONTROL_STAGES + 1)
    )
    L.append("| W | Base period at grt (ps) | rt period at grt (ps) | Base / %d | Slides | Rounds |" % (CONTROL_STAGES + 1))
    L.append("|---:|---:|---:|---:|---:|---:|")
    for row in data.get("control", []):
        b = row.get("base", {}).get("period_ps")
        r = row.get("retime", {}).get("period_ps")
        tot = ((row.get("retime") or {}).get("retime") or {}).get("totals") or {}
        L.append(
            "| %d | %s | %s | %s | %s | %s |"
            % (
                row["width"],
                _f(b),
                _f(r),
                _f(b / (CONTROL_STAGES + 1) if b else None),
                _f(tot.get("slides")),
                _f(tot.get("rounds")),
            )
        )
    return "\n".join(L) + "\n"


def report():
    data, floors = _load()
    sys.stdout.write(render(data, floors))


# -------------------------------------------------------------------- plot

INK, INK2, GRID, BAND = "#191919", "#666666", "#bdbdbd", "#e8e8e8"
S1, S2, S3 = "#257de0", "#f47230", "#00b894"


def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)


def plot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data, floors = _load()
    results = data["designs"]
    byk = {r["key"]: r for r in results}
    v = verdicts(results)
    written = []

    # 1. each design's period change in noise sigma, per effect
    labels = {
        "seed2": "seed change\n(the noise reference)",
        "rt": "retime\n(against base)",
        "rt_seed2": "retime, second draw\n(against the seed change)",
    }
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=150)
    ax.axvspan(-2, 2, color=BAND, zorder=0, lw=0)
    ax.axvline(0, color=GRID, lw=1, zorder=1)
    names = [c for c, _, _ in COMPARISONS]
    allz = [0.0]
    for i, c in enumerate(reversed(names)):
        x = v.get(c)
        if not x:
            continue
        zs = [d["z"] for d in x["per_design"].values()]
        allz += zs + [x["Z"]]
        jit = [((k * 37) % 9 - 4) * 0.035 for k in range(len(zs))]
        ax.scatter(zs, [i + j for j in jit], s=46, color=S1, alpha=0.75,
                   edgecolors="white", linewidths=1.5, zorder=3)
        ax.scatter([x["Z"]], [i], marker="D", s=90, color=INK,
                   edgecolors="white", linewidths=2, zorder=4)
        ax.annotate("Z = %+.2f" % x["Z"], (x["Z"], i), xytext=(0, 13),
                    textcoords="offset points", ha="center", fontsize=9, color=INK)
    lim = max(3.6, max(abs(z) for z in allz) + 0.6)
    ax.set_xlim(-lim, lim)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([labels[c] for c in reversed(names)], fontsize=9, color=INK)
    ax.set_ylim(-0.6, len(names) - 0.1)
    ax.text(0, len(names) - 0.35, "within the noise floor  (|z| < 2)", ha="center",
            va="bottom", fontsize=9, color=INK2)
    ax.set_xlabel("period change at global route, in noise σ   (left: faster, right: slower)",
                  fontsize=9, color=INK2)
    _style(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("retime against the placement-seed noise floor, ORFS designs",
                 fontsize=11, color=INK, loc="left", pad=12)
    fig.text(0.01, 0.01, "Dots: one design, one run each.  Diamond: Z = Σz/√n.  "
             "σ: QoR dashboard master history ×%.2f (seed-calibrated)." % v["sigma_scale"],
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    written.append(_save(fig, "period_z.png"))

    # 2. what retiming could win against what retime won
    keys = [k for k in PANEL if headroom_pct(floors.get(k)) is not None]
    keys.sort(key=lambda k: headroom_pct(floors[k]))
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(keys) + 1.4), dpi=150)
    y = list(range(len(keys)))
    hr = [headroom_pct(floors[k]) for k in keys]
    won = []
    for k in keys:
        pd = ((v.get("rt") or {}).get("per_design") or {}).get(k)
        won.append(-pd["pct"] if pd else None)
    ax.barh([i + 0.2 for i in y], hr, height=0.36, color=S1, label="most any retiming could win (floor_retime)")
    ax.barh([i - 0.2 for i in y], [w if w is not None else 0 for w in won], height=0.36,
            color=S2, label="what retime won at grt (rt against base)")
    for i, w in enumerate(won):
        if w is None:
            ax.text(0.3, i - 0.2, "not measured / refused", va="center", fontsize=7.5, color=INK2)
    ax.axvline(0, color=GRID, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(keys, fontsize=8.5, color=INK)
    ax.set_xlabel("% of the period at global route", fontsize=9, color=INK2)
    _style(ax)
    ax.tick_params(axis="y", length=0)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.set_title("Retiming headroom against the gain retime delivers", fontsize=11,
                 color=INK, loc="left", pad=10)
    fig.tight_layout()
    written.append(_save(fig, "headroom.png"))

    # 3. the positive control: period against multiplier width
    ctl = [r for r in data.get("control", []) if r.get("base", {}).get("period_ps")]
    if ctl:
        fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
        w = [r["width"] for r in ctl]
        b = [r["base"]["period_ps"] for r in ctl]
        rt = [r.get("retime", {}).get("period_ps") for r in ctl]
        ideal = [x / (CONTROL_STAGES + 1) for x in b]
        ax.plot(w, b, color=S1, lw=2, marker="o", ms=7, mec="white", mew=1.5, label="base")
        ax.plot(w, rt, color=S2, lw=2, marker="o", ms=7, mec="white", mew=1.5, label="retime")
        ax.plot(w, ideal, color=INK2, lw=1.5, ls="--", label="base / %d (ideal retiming)" % (CONTROL_STAGES + 1))
        ax.axhline(CONTROL_PERIOD_PS, color=GRID, lw=1)
        ax.text(w[0], CONTROL_PERIOD_PS, " SDC clock %d ps" % CONTROL_PERIOD_PS, va="bottom",
                fontsize=8, color=INK2)
        ax.set_xscale("log", base=2)
        ax.set_xticks(w)
        ax.set_xticklabels([str(x) for x in w])
        ax.set_xlabel("multiplier width W (bits)", fontsize=9, color=INK2)
        ax.set_ylabel("period at global route (ps)", fontsize=9, color=INK2)
        ax.set_ylim(0, max(b) * 1.1)
        _style(ax)
        ax.legend(frameon=False, fontsize=8, loc="upper left")
        ax.set_title("Positive control: %d empty stages in front of a multiplier" % CONTROL_STAGES,
                     fontsize=11, color=INK, loc="left", pad=10)
        fig.tight_layout()
        written.append(_save(fig, "control.png"))

    # 4. WNS after each retime round, as % of the period, per design
    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    any_line = False
    for key in PANEL:
        r = byk.get(key)
        rt = ((r or {}).get("arms", {}).get("rt") or {}).get("retime") or {}
        rounds = rt.get("rounds") or []
        per = ((r or {}).get("arms", {}).get("base") or {}).get("period_ps")
        if len(rounds) < 2 or not per:
            continue
        u = unit_ps(key)
        gain = [100 * (x["wns"] - rounds[0]["wns"]) * u / per for x in rounds]
        ax.plot([x["round"] for x in rounds], gain, color=S1, lw=1.5, alpha=0.7,
                marker="o", ms=4)
        ax.annotate(key, (rounds[-1]["round"], gain[-1]), xytext=(4, 0),
                    textcoords="offset points", fontsize=7, color=INK2, va="center")
        any_line = True
    for row in data.get("control", []):
        rounds = (((row.get("retime") or {}).get("retime")) or {}).get("rounds") or []
        b = (row.get("base") or {}).get("period_ps")
        if len(rounds) < 2 or not b:
            continue
        gain = [100 * (x["wns"] - rounds[0]["wns"]) / b for x in rounds]
        ax.plot([x["round"] for x in rounds], gain, color=S2, lw=1.5, marker="o", ms=4)
        ax.annotate("control W=%d" % row["width"], (rounds[-1]["round"], gain[-1]),
                    xytext=(4, 0), textcoords="offset points", fontsize=7, color=INK2,
                    va="center")
        any_line = True
    if any_line:
        ax.axhline(0, color=GRID, lw=1)
        ax.set_xlabel("retime round (0: before)", fontsize=9, color=INK2)
        ax.set_ylabel("WNS gain, % of the period", fontsize=9, color=INK2)
        _style(ax)
        ax.set_title("What each retime round gained, as retime measures it", fontsize=11,
                     color=INK, loc="left", pad=10)
        fig.tight_layout()
        written.append(_save(fig, "rounds.png"))
    plt.close("all")
    for p in written:
        print("wrote " + os.path.relpath(p, ROOT))


def _save(fig, name):
    path = os.path.join(DOCS, name)
    fig.savefig(path, facecolor="white")
    return path


if __name__ == "__main__":
    {"collect": collect, "report": report, "plot": plot}[
        sys.argv[1] if len(sys.argv) > 1 else "report"
    ]()
