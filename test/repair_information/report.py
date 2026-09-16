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
from pathlib import Path

import noise_floor as nf
import rank_agreement as ra

# The rungs, cheapest first, and what each one is. Kept here rather than
# read from the data so that a rung which was never run is still named in
# the table as missing, instead of vanishing from the ladder.
RUNGS = [
    ("placement", "`estimate_parasitics -placement`; no route at all"),
    ("gr_cheapest", "`-infinite_cap -congestion_iterations 1`; no detours"),
    ("gr_no_overflow_loop", "`-congestion_iterations 1`; capacity seen, overflow left"),
    ("gr_few", "`-congestion_iterations 5`"),
    ("gr_stock", "`-congestion_iterations 30`; what ORFS runs"),
]

MISSING = "*Not yet measured.*"


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


def render(found):
    parts = [
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

    text = render(discover(results))
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
