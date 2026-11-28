"""The two-pass study: collect, and report from what was collected.

    python3 -I test/repair_noise/two_pass.py collect   # from bazel outputs
    python3 -I test/repair_noise/two_pass.py report    # PR body tables

`collect` asks bazel where the outputs are (cquery, exact paths, no
globbing in output trees) and writes docs/studies/two-pass-placement/
results.json: per design, the period at grt of each arm, the clock
latencies pass 1 measured, and the gaps between the timing global
placement sees and the timing at grt. `report` reads only that file; a
design or arm missing from it renders as "not yet measured".

Arms: base and seed2 are the ORFS#4893 arms (pass 1 and its seed
draw); tp_ctl reruns placement to grt from base's floorplan with nothing
fed back; tp_clk does so with pass 1's clock latencies set during global
placement; tp_vcts is one pass with global placement's own virtual
clock tree.
"""

import json
import math
import os
import re
import subprocess
import sys

PANEL = [
    "asap7/gcd",
    "asap7/ibex",
    "asap7/ethmac",
    "asap7/swerv_wrapper",
    "nangate45/black_parrot",
    "nangate45/ariane133",
    "nangate45/swerv_wrapper",
    "sky130hd/microwatt",
    "sky130hd/ibex",
    "sky130hd/riscv32i",
    "sky130hs/jpeg",
    "gf180/ibex",
    "asap7/mock-alu",
]
ARMS = ["base", "seed2", "tp_ctl", "tp_clk", "tp_vcts"]
COMPARED = ["seed2", "tp_ctl", "tp_clk", "tp_vcts"]
# global placement weights this share of the worst nets by default
# (gpl -timing_driven_nets_percentage)
TOP_SHARE = 0.10
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RESULTS = os.path.join(ROOT, "docs", "studies", "two-pass-placement", "results.json")
# The noise band of ORFS#4893: per-draw sigma of grt WNS from the QoR
# dashboard's master history, in the platform's time unit.
NOISE = os.path.join(ROOT, "docs", "studies", "two-pass-placement", "noise.json")
DASH = {"nangate45/black_parrot": "nangate45/bp"}


def variant(key):
    return key.replace("/", "_").replace("-", "_")


def design_period_ps(metrics, stage="globalroute"):
    """clk_period - WNS of the design clock, from ORFS's per-clock fmax.

    The largest period over the real clocks; ORFS's bare timing__fmax can
    be a virtual I/O clock's (OpenROAD #11668), so it is not used.
    """
    best = None
    prefix = stage + "__timing__fmax__clock:"
    for k, v in metrics.items():
        if not k.startswith(prefix) or k[len(prefix) :].startswith("vclk"):
            continue
        if not v:
            continue
        p = 1e12 / v
        best = p if best is None else max(best, p)
    return best


def read_tsv(path):
    """Rows of a probe TSV, comments dropped, fields split on tabs."""
    rows = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            rows.append(line.rstrip("\n").split("\t"))
    return rows


def _num(s):
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) and abs(v) < 1e29 else None


def ranks(values):
    """Average ranks, ties shared."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    if va == 0 or vb == 0:
        return None
    return cov / math.sqrt(va * vb)


def worst_set(rows, col, share):
    n = max(1, int(round(share * len(rows))))
    return set(r[0] for r in sorted(rows, key=lambda r: r[col])[:n])


def gap_metrics(slack_rows, share=TOP_SHARE):
    """How well the slacks global placement sees rank the nets at grt.

    slack_rows: (pin, gp, gi, pi) strings. Only pins constrained in all
    three readings count. Overlap is |worst share by one reading ∩ worst
    share by the other| / |worst share|; rho is Spearman over those
    pins.
    """
    rows = []
    for r in slack_rows:
        v = [_num(x) for x in r[1:4]]
        if None in v:
            continue
        rows.append((r[0], v[0], v[1], v[2]))
    out = {"pins": len(rows)}
    if not rows:
        return out
    sets = {c: worst_set(rows, i, share) for i, c in ((1, "gp"), (2, "gi"), (3, "pi"))}
    n = len(sets["gp"])
    for name, x, y in (
        ("clock", "gi", "gp"),
        ("wire", "pi", "gi"),
        ("total", "pi", "gp"),
    ):
        out["overlap_" + name] = len(sets[x] & sets[y]) / n
        i = {"gp": 1, "gi": 2, "pi": 3}
        out["rho_" + name] = spearman([r[i[x]] for r in rows], [r[i[y]] for r in rows])
    return out


def latency_stats(lat_rows):
    """Spread of rise-max latency over the register clock pins."""
    v = [_num(r[1]) for r in lat_rows]
    v = [x for x in v if x is not None]
    if not v:
        return {"sinks": 0}
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / len(v))
    return {"sinks": len(v), "min": min(v), "max": max(v), "mean": m, "sd": sd}


def took(log, what):
    """Seconds of ORFS 'Took N seconds: <what>' lines (under 5 s logs none)."""
    if not log or not os.path.exists(log):
        return None
    s = 0
    with open(log, errors="replace") as fh:
        for line in fh:
            m = re.match(r"Took (\d+) seconds: (\S+)", line)
            if m and m.group(2) == what:
                s += int(m.group(1))
    return s


def elapsed_s(log):
    """The stage's own wall time from the log's last 'Elapsed time' line."""
    if not log or not os.path.exists(log):
        return None
    t = None
    with open(log, errors="replace") as fh:
        for line in fh:
            m = re.search(r"Elapsed time: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", line)
            if m:
                h = int(m.group(1) or 0)
                t = h * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return t


def _comb(n, k):
    return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))


def first_error(logs):
    """The first '[ERROR ...]' line in the stage logs given, or None."""
    for log in logs:
        if not log or not os.path.exists(log):
            continue
        with open(log, errors="replace") as fh:
            for line in fh:
                if line.startswith("[ERROR "):
                    return line.strip()
    return None


def binom_tail(n, w):
    return sum(_comb(n, i) for i in range(w, n + 1)) / 2**n


def verdicts(results):
    """Per compared arm: z per design, calibrated Z, sign test.

    z = Δperiod / (√2 σ); σ is scaled by the RMS of the seed arm's z (at
    least 1), as ORFS#4893's decision rule does. Negative is better.
    """
    zs = {a: [] for a in COMPARED}
    for r in results:
        b = r["arms"].get("base", {}).get("period_ps")
        s = r.get("sigma_ps")
        if not b or not s:
            continue
        for a in COMPARED:
            p = r["arms"].get(a, {}).get("period_ps")
            if p is None:
                continue
            d = p - b
            zs[a].append((r["key"], d, d / (math.sqrt(2) * s), 100 * d / b))
    seed = [z for _, _, z, _ in zs["seed2"]]
    k = max(1.0, math.sqrt(sum(z * z for z in seed) / len(seed))) if seed else 1.0
    out = {"sigma_scale": k}
    for a in COMPARED:
        l = zs[a]
        if not l:
            out[a] = None
            continue
        zc = [z / k for _, _, z, _ in l]
        better = sum(1 for _, d, _, _ in l if d < 0)
        worse = sum(1 for _, d, _, _ in l if d > 0)
        pct = sorted(p for _, _, _, p in l)
        out[a] = {
            "n": len(l),
            "Z": sum(zc) / math.sqrt(len(zc)),
            "better": better,
            "worse": worse,
            "p_better": binom_tail(len(l), better),
            "mean_pct": sum(pct) / len(pct),
            "median_pct": pct[len(pct) // 2],
            "min_pct": pct[0],
            "max_pct": pct[-1],
            "per_design": {key: {"delta_ps": d, "z": z / k} for key, d, z, _ in l},
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


# ---------------------------------------------------------------- collect


def _cquery(targets, groups="logs,default"):
    out = subprocess.run(
        [
            "bazelisk",
            "cquery",
            "--output=files",
            "--output_groups=" + groups,
            "set(%s)" % " ".join(targets),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    ).stdout.split()
    return [os.path.join(ROOT, f) for f in out]


def collect():
    noise = {}
    if os.path.exists(NOISE):
        for n in json.load(open(NOISE)):
            noise["%s/%s" % (n["platform"], n["design"])] = n
    labels = subprocess.run(
        ["bazelisk", "query", "attr(name, '_base_grt$', //test/repair_noise:all)"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    ).stdout.split()
    results = []
    for key in PANEL:
        v = variant(key)
        base = [l for l in labels if l.endswith("_%s_base_grt" % v)]
        if not base:
            continue
        top = base[0].split(":")[1][: -len("_%s_base_grt" % v)]
        row = {"key": key, "arms": {}}
        targets = []
        for a in ARMS:
            targets += [
                "//test/repair_noise:%s_%s_%s_grt_report" % (top, v, a),
                "//test/repair_noise:%s_%s_%s_place" % (top, v, a),
                "//test/repair_noise:%s_%s_%s_cts" % (top, v, a),
                "//test/repair_noise:%s_%s_%s_grt" % (top, v, a),
            ]
        files = _cquery(targets + ["//test/repair_noise:two_pass_probe_" + v])
        for a in ARMS:
            d = "/%s_%s/" % (v, a)
            rep = [f for f in files if f.endswith("_%s_%s_grt_report.json" % (v, a))]
            arm = {}
            if rep and os.path.exists(rep[0]):
                m = json.load(open(rep[0]))
                arm["period_ps"] = design_period_ps(m)
                arm["tns"] = m.get("globalroute__timing__setup__tns")
            logs = {
                os.path.basename(f): f for f in files if d in f and f.endswith(".log")
            }
            arm["gpl_s"] = elapsed_s(logs.get("3_3_place_gp.log"))
            arm["cts_s"] = elapsed_s(logs.get("4_1_cts.log"))
            arm["grt_s"] = elapsed_s(logs.get("5_1_grt.log"))
            arm["grt_repair_s"] = took(logs.get("5_1_grt.log"), "repair_timing")
            if arm.get("period_ps") is not None:
                row["arms"][a] = arm
            else:
                err = first_error([logs.get(n) for n in sorted(logs)])
                if err:
                    row.setdefault("failed", {})[a] = err
        lat = [f for f in files if f.endswith("two_pass_probe_%s_latencies.tsv" % v)]
        sl = [f for f in files if f.endswith("two_pass_probe_%s_slacks.tsv" % v)]
        if lat and os.path.exists(lat[0]):
            row["latency"] = latency_stats(read_tsv(lat[0]))
        if sl and os.path.exists(sl[0]):
            row["gap"] = gap_metrics(read_tsv(sl[0]))
        n = noise.get(DASH.get(key, key))
        unit = 1.0 if key.startswith("asap7") else 1000.0
        row["sigma_ps"] = n["sigma_ps"] * unit if n else None
        results.append(row)
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w") as fh:
        json.dump(results, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %d designs to %s" % (len(results), os.path.relpath(RESULTS, ROOT)))


# ----------------------------------------------------------------- report


def _f(x, fmt="{:,.0f}"):
    return "–" if x is None else fmt.format(x)


def render(results):
    if not results:
        raise SystemExit("no results: run the campaign, then `two_pass.py collect`")
    byk = {r["key"]: r for r in results}
    v = verdicts(results)
    L = []
    L.append("### Verdicts\n")
    L.append(
        "| Arm | Z (calibrated) | Better / worse | p (sign, better) | Mean / median Δ period | Range | Verdict |"
    )
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for a in COMPARED:
        x = v[a]
        if x is None:
            L.append("| %s | | | | | | not yet measured |" % a)
            continue
        L.append(
            "| %s | %+.2f | %d / %d | %.2f | %+.2f%% / %+.2f%% | %+.1f%% … %+.1f%% | %s |"
            % (
                a,
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
    L.append("Δ against base, ps; bold where |z| > 2 on the calibrated σ.\n")
    L.append("| Design | Base (ps) | σ (ps) | " + " | ".join(COMPARED) + " |")
    L.append("|---|---:|---:|" + "---:|" * len(COMPARED))
    for key in PANEL:
        r = byk.get(key)
        if not r or "base" not in r["arms"]:
            L.append("| %s | not yet measured | |" % key + " |" * len(COMPARED))
            continue
        cells = []
        for a in COMPARED:
            pd = (v.get(a) or {}).get("per_design", {}).get(key)
            if pd is None:
                cells.append("failed" if a in r.get("failed", {}) else "–")
                continue
            s = "%+.0f" % pd["delta_ps"]
            cells.append("**%s**" % s if abs(pd["z"]) > 2 else s)
        sig = r["sigma_ps"] * v["sigma_scale"] if r.get("sigma_ps") else None
        L.append(
            "| %s | %s | %s | %s |"
            % (key, _f(r["arms"]["base"]["period_ps"]), _f(sig), " | ".join(cells))
        )
    for key in PANEL:
        for a, err in sorted(((byk.get(key) or {}).get("failed") or {}).items()):
            L.append("- %s, %s failed: `%s`" % (key, a, err))
    L.append("\n### What global placement sees, against grt (step 0)\n")
    L.append(
        "On base's grt result: overlap of the worst %d%% of constrained output pins"
        " (one per net, the driver), and Spearman ρ over all of them. clock: ideal against"
        " propagated clock, both on grt wires. wire: placement against grt wires, both"
        " ideal. total: what global placement sees against grt.\n"
        % round(100 * TOP_SHARE)
    )
    L.append(
        "| Design | Pins | Overlap clock / wire / total | ρ clock / wire / total | Sinks | Latency min–max (ps) | Spread / period |"
    )
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for key in PANEL:
        r = byk.get(key)
        g = (r or {}).get("gap")
        lat = (r or {}).get("latency")
        if not g or not lat:
            L.append("| %s | not yet measured | | | | | |" % key)
            continue
        per = r["arms"].get("base", {}).get("period_ps")
        spread = (lat["max"] - lat["min"]) if lat.get("sinks") else None
        unit = 1.0 if key.startswith("asap7") else 1000.0
        L.append(
            "| %s | %s | %.2f / %.2f / %.2f | %.2f / %.2f / %.2f | %s | %s–%s | %s |"
            % (
                key,
                _f(g["pins"]),
                g["overlap_clock"],
                g["overlap_wire"],
                g["overlap_total"],
                g["rho_clock"] or 0,
                g["rho_wire"] or 0,
                g["rho_total"] or 0,
                _f(lat["sinks"]),
                _f(lat["min"] * unit, "{:,.1f}"),
                _f(lat["max"] * unit, "{:,.1f}"),
                _f(
                    100 * spread * unit / per if spread is not None and per else None,
                    "{:.1f}%",
                ),
            )
        )
    L.append("\n### Running time\n")
    L.append(
        "Stage wall time from the logs, summed over designs (s). The arms ran under remote"
        " execution at different times, so stage times carry the remote load; read them"
        " as an order of magnitude.\n"
    )
    L.append("| Arm | gpl | cts | grt | grt repair_timing |")
    L.append("|---|---:|---:|---:|---:|")
    for a in ARMS:
        tot = {}
        for c in ("gpl_s", "cts_s", "grt_s", "grt_repair_s"):
            vals = [byk[k]["arms"][a].get(c) for k in byk if a in byk[k]["arms"]]
            vals = [x for x in vals if x is not None]
            tot[c] = sum(vals) if vals else None
        L.append(
            "| %s | %s | %s | %s | %s |"
            % (
                a,
                _f(tot["gpl_s"]),
                _f(tot["cts_s"]),
                _f(tot["grt_s"]),
                _f(tot["grt_repair_s"]),
            )
        )
    return "\n".join(L) + "\n"


def report():
    if not os.path.exists(RESULTS):
        raise SystemExit("run the campaign first, then `two_pass.py collect`")
    sys.stdout.write(render(json.load(open(RESULTS))))


if __name__ == "__main__":
    {"collect": collect, "report": report}[
        sys.argv[1] if len(sys.argv) > 1 else "report"
    ]()
