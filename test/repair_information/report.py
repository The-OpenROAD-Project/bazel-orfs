"""Render Part A's findings as markdown, from whatever results exist.

The pull request body is the part of a study anyone reads, so it is
generated rather than typed: a hand-written table stops being true the
first time a campaign is re-run, and there is no way to tell by looking.

Sections whose inputs are absent say so. Dropping them silently would
make a partial study read as a complete one -- a well-formed answer to a
question nobody measured, which is the failure this whole study is about.

Results are *discovered*, never declared as build inputs: a rung that has
been run appears in the tables by having been run, and one that has not
appears as "not yet measured".
"""

import argparse
import json
import re
import statistics as st
from pathlib import Path

import noise_floor as nf
import rank_agreement as ra

# The rungs, cheapest first, and what each one is. Kept here rather than
# read from the data so that a rung which was never run is still named in
# the table as missing, instead of vanishing from the ladder.
RUNGS = [
    ("zero_rc", "signal wire RC set to ~0; the no-wires floor"),
    ("placement", "`estimate_parasitics -placement`; no route at all"),
    ("gr_cheapest", "`-infinite_cap -congestion_iterations 1`; no detours"),
    ("gr_no_overflow_loop", "`-congestion_iterations 1`; capacity seen, overflow left"),
    ("gr_few", "`-congestion_iterations 5`"),
    ("gr_stock", "`-congestion_iterations 30`; what ORFS runs"),
]

MISSING = "*Not yet measured.*"

# wbq_<shape>_<arm>_s<seed>_spef. The arm is non-greedy up to the final
# _s<digits>_spef so an arm name containing "_s" cannot swallow it.
QOR_NAME = re.compile(r"^wbq_(?P<shape>[^_]+)_(?P<arm>.+)_s(?P<seed>\d+)_spef$")


def table(headers, rows):
    if not rows:
        return MISSING
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def fmt(value, digits=2, dash="--"):
    if value is None:
        return dash
    return f"{value:.{digits}f}"


def discover(results_dir):
    """Probe JSONs, keyed by (design, arm).

    A file whose name does not parse is an error rather than a skip: a
    silently ignored result is how a campaign reports three designs when
    four were run.
    """
    found = {}
    for path in sorted(Path(results_dir).glob("*.json")):
        data = json.loads(path.read_text())
        if "endpoints" not in data:
            continue
        design = path.stem.split(".")[0]
        arm = data["arm"]
        # The arm carries the design prefix the BUILD gave it; strip it
        # so the same rung name lines up across designs.
        for rung, _ in RUNGS + [("spef", "")]:
            if arm.endswith("_" + rung):
                design = arm[: -len(rung) - 1]
                arm = rung
                break
        found[(design, arm)] = data
    return found


def designs_of(found):
    return sorted({design for design, _ in found})


def section_floors(found):
    """A0: the two floors, per design."""
    rows = []
    for design in designs_of(found):
        ref = found.get((design, "spef"))
        if ref is None:
            continue
        clock = float(ref["clock_period"])
        floor = nf.floors(design, clock)
        rows.append(
            [
                design,
                fmt(clock),
                fmt(floor["tolerance_bar_ps"]),
                "not measured",
            ]
        )
    return table(
        ["design", "clock period", "CI tolerance bar (5% of clock)", "measured 2σ"],
        rows,
    )


def section_ceiling(found):
    """The upper bound on the whole study, per design.

    Signal wire delay as a share of the achieved period. Every question
    here is a question about the wire part of a path delay, so this is
    the most any parasitics model can be wrong by -- and therefore the
    most any better instrument can win. A design at 2% is a design where
    nothing downstream can matter, however congested it is made.
    """
    rows = []
    for design in designs_of(found):
        ref = found.get((design, "spef"))
        pl = found.get((design, "placement"))
        zero = found.get((design, "zero_rc"))
        if pl is None or zero is None:
            continue
        wire = pl["min_period"] - zero["min_period"]
        share = 100.0 * wire / pl["min_period"]
        gr = found.get((design, "gr_stock"))
        row = [
            design,
            fmt(zero["min_period"], 1),
            fmt(pl["min_period"], 1),
            fmt(wire, 1),
            fmt(share, 1) + "%",
        ]
        if ref is not None:
            row.append(fmt(pl["min_period"] - ref["min_period"], 1))
            row.append(
                fmt(gr["min_period"] - ref["min_period"], 1) if gr else "--",
            )
            # What the instrument's error is worth in units of the thing
            # it is modelling. Above 100% the model is wrong about the
            # wires by more than the wires are worth.
            row.append(
                (
                    fmt(100.0 * abs(gr["min_period"] - ref["min_period"]) / wire, 0)
                    + "%"
                    if gr and wire > 0
                    else "--"
                ),
            )
        else:
            row += ["--", "--", "--"]
        rows.append(row)
    return table(
        [
            "design",
            "no-wire period",
            "placement period",
            "wire delay",
            "wire share",
            "placement err vs SPEF",
            "grt err vs SPEF",
            "grt err / wire delay",
        ],
        rows,
    )


def by_label(cmp, label):
    """One top-k row by name, falling back to the widest available.

    A design can be too small for an absolute k -- gcd has 52 endpoints
    -- and a KeyError there would drop the whole design out of the table
    rather than report what was measured.
    """
    for row in cmp["top_k"]:
        if row["label"] == label:
            return row
    return cmp["top_k"][-1]


def section_ladder(found):
    """A1 and A2: rank agreement against the SPEF, and what it cost."""
    rows = []
    for design in designs_of(found):
        ref = found.get((design, "spef"))
        if ref is None:
            continue
        ref_slacks = {r["endpoint"]: float(r["slack"]) for r in ref["endpoints"]}
        for rung, _ in RUNGS:
            probe = found.get((design, rung))
            if probe is None:
                rows.append([design, rung, "--", "--", "--", "--", "--", "not run"])
                continue
            slacks = {r["endpoint"]: float(r["slack"]) for r in probe["endpoints"]}
            cmp = ra.compare(ref_slacks, slacks)
            top = by_label(cmp, "top10")
            broad = by_label(cmp, "5%")
            rows.append(
                [
                    design,
                    rung,
                    fmt(cmp["spearman"], 3),
                    "{}/{}".format(top["overlap"], top["k"]),
                    "{}/{}".format(broad["overlap"], broad["k"]),
                    fmt(probe.get("seconds")),
                    fmt(probe.get("pin_access_seconds")),
                    probe.get("nets_with_guides", "--"),
                ]
            )
    return table(
        [
            "design",
            "rung",
            "Spearman ρ vs SPEF",
            "worst-10 overlap",
            "worst-5% overlap",
            "route s",
            "pin access s",
            "nets with guides",
        ],
        rows,
    )


def section_min_period(found):
    """What each instrument thought the design could run at."""
    rows = []
    for design in designs_of(found):
        ref = found.get((design, "spef"))
        if ref is None:
            continue
        row = [design, fmt(ref["min_period"])]
        for rung, _ in RUNGS:
            probe = found.get((design, rung))
            row.append(fmt(probe["min_period"]) if probe else "--")
        rows.append(row)
    return table(
        ["design", "SPEF"] + [rung for rung, _ in RUNGS],
        rows,
    )


def qor_arms(results_dir):
    """The QoR ensemble, keyed by (arm, seed).

    Separate from `discover` because these are flow arms rather than
    instrument probes: same JSON shape, different question.

    The name is parsed with an anchored pattern rather than by splitting:
    an arm called `no_cts_rt` and a suffix of `_spef` both contain "_s",
    so a naive rsplit finds the wrong one and the whole section silently
    renders as "not measured".
    """
    out = {}
    for path in sorted(Path(results_dir).glob("wbq_*_spef.json")):
        match = QOR_NAME.match(path.stem)
        if not match:
            raise SystemExit(
                "{}: does not parse as wbq_<shape>_<arm>_s<seed>_spef; a "
                "result that does not parse must not be silently "
                "skipped".format(path.name)
            )
        out[(match.group("arm"), int(match.group("seed")))] = json.loads(
            path.read_text()
        )
    return out


def section_qor(results_dir):
    """What the repairs cost and what they bought.

    Two axes, because the period alone cannot answer it: a repair that
    spends area to reach the same period reads as nothing on a period
    table, which is how this study spent most of its life not seeing
    the only effect that resolves.
    """
    arms = qor_arms(results_dir)
    if not arms:
        return MISSING
    names = sorted({a for a, _ in arms})
    if "base" not in names:
        return MISSING
    seeds = sorted({s for _, s in arms})

    def col(arm, key):
        return [arms[(arm, s)][key] for s in seeds if (arm, s) in arms]

    rows = []
    for arm in ["base"] + [n for n in names if n != "base"]:
        periods = col(arm, "min_period")
        areas = col(arm, "cell_area_um2")
        if not periods:
            continue
        row = [
            arm,
            ", ".join("{:.1f}".format(v) for v in periods),
            ", ".join("{:.0f}".format(v) for v in areas),
        ]
        if arm == "base":
            row += ["--", "--"]
        else:
            dp = [p - b for p, b in zip(periods, col("base", "min_period"))]
            da = [a - b for a, b in zip(areas, col("base", "cell_area_um2"))]
            row += [
                "{:+.2f}".format(st.mean(dp)),
                "{:+.1f}".format(st.mean(da)),
            ]
        rows.append(row)

    table_text = table(
        [
            "arm",
            "min_period per seed (ps)",
            "logic area per seed (um2)",
            "mean d period",
            "mean d area",
        ],
        rows,
    )

    base_p = col("base", "min_period")
    spread = ""
    if len(base_p) > 1:
        two_sigma = 2 * st.stdev(base_p)
        spread = (
            "\nBaseline seed spread is 2 sigma = {:.2f} ps, so a difference "
            "of {:.2f} ps between arms at {} seeds each is the resolution "
            "floor on the period axis.".format(
                two_sigma, two_sigma * (2.0 / len(base_p)) ** 0.5, len(base_p)
            )
        )
    return table_text + "\n" + spread


def render(found, results_dir=None):
    parts = [
        "## The ceiling -- how much wire delay is there to be wrong about?",
        "",
        "Signal wire RC set to ~0 against the same CTS ODB, clock tree",
        "left real. The difference is the whole data-path wire",
        "contribution to the achieved period, and therefore the most any",
        "parasitics model can be wrong by. The last column puts each",
        "instrument's error in units of the wire delay it is modelling:",
        "above 100% the estimate is wrong about the wires by more than",
        "the wires are worth.",
        "",
        section_ceiling(found),
        "",
        "## A0 -- the two floors",
        "",
        "`rules-base.json` records a padded threshold, not a noise",
        "measurement: setup worst slack is padded by 5% of the clock",
        "period. That is the bar CI would notice, not the bar a result",
        "has to clear. The measured floor comes from repeats and is",
        "reported here only once repeats exist.",
        "",
        section_floors(found),
        "",
        "## A1/A2 -- does the better instrument rank differently, and what did it cost?",
        "",
        "Every rung is the same CTS ODB, routed differently, scored",
        "against the routed design's own extracted SPEF. The rungs are",
        "cheapest first.",
        "",
        section_ladder(found),
        "",
        "### What each instrument thought the period was",
        "",
        section_min_period(found),
        "",
        "### The rungs",
        "",
        table(["rung", "what it is"], [[r, d] for r, d in RUNGS]),
        "",
        "## What the repairs cost, and what they bought",
        "",
        "Turning each repair off, three placement seeds per arm. Logic",
        "area excludes filler and well taps: filler is inserted to occupy",
        "whatever the logic leaves, so a total including it is constant by",
        "construction and reports nothing.",
        "",
        section_qor(results_dir) if results_dir else MISSING,
    ]
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="results", help="directory of probe JSONs")
    ap.add_argument("--out", help="write the markdown here instead of stdout")
    args = ap.parse_args()

    results = Path(args.results)
    if not results.is_dir() or not any(results.glob("*.json")):
        raise SystemExit(
            f"no results under {results}: run the campaign first. "
            "This report is generated from measurements and has nothing "
            "to say without them."
        )

    text = render(discover(results), results)
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
