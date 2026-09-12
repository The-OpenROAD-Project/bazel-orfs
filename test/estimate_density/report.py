"""Turn whatever is in results/ into the tables the PR body carries.

The report discovers results; nothing here declares what should exist. A
design with no samples renders as "not yet measured" rather than being
silently absent, because a partial campaign that reads as a complete one
is the way a study lies without anyone deciding to.

    python3 test/estimate_density/report.py            # markdown to stdout
    python3 test/estimate_density/report.py --csv      # raw samples
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import campaign  # noqa: E402
import harvest  # noqa: E402

RESULTS_DIR = campaign.RESULTS_DIR

NOT_MEASURED = "_Not yet measured._"


def load(results_dir=RESULTS_DIR):
    """Every sample on disk, newest-first order irrelevant."""
    if not os.path.isdir(results_dir):
        raise SystemExit(
            "no results in {} -- run the campaign first:\n"
            "  python3 test/estimate_density/campaign.py --design gcd".format(
                results_dir
            )
        )
    records = []
    for path in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        with open(path) as handle:
            records.append(json.load(handle))
    return records


def missing(designs):
    """Declared designs with nothing measured yet.

    A table that simply leaves them out reads as a finished campaign with
    fewer designs in it. Naming them is the difference between "eight
    designs, three measured" and a quiet lie.
    """
    return [name for name in sorted(campaign.DESIGN_TOPS) if name not in designs]


def render_missing(names):
    if not names:
        return "Every declared design has samples."
    return "{} {}: {}".format(
        NOT_MEASURED,
        "Declared but not measured",
        ", ".join(names),
    )


def rung_index(record):
    """The ladder position of a sample, or None for `ship` and `est`.

    The variant is what ORFS was told, so it is also what the sample is
    named after; a rung is the subset that looks like `t07`.
    """
    variant = record.get("variant", "")
    if len(variant) == 3 and variant.startswith("t") and variant[1:].isdigit():
        return int(variant[1:])
    return None


def arm(record):
    """`ship`, `est`, or None for a rung."""
    variant = record.get("variant", "")
    return variant if variant in ("ship", "est") else None


def by_design(records):
    designs = {}
    for record in records:
        designs.setdefault(record["design"], []).append(record)
    return designs


def _density(record):
    """The density global placement was actually told to use.

    Three sources, in the order of how directly each one witnesses it:
    ORFS's own line on the ladder arms, the probe's line on the arm it
    drove, and the design's shipped PLACE_DENSITY on the arm where
    nothing intervened.
    """
    orfs = record.get("orfs_density")
    if orfs:
        return orfs["density"]
    if record.get("driven_density") is not None:
        return float(record["driven_density"])
    context = record.get("context") or {}
    shipped = context.get("place_density")
    return float(shipped) if shipped not in (None, "") else None


def _uniform(record):
    orfs = record.get("orfs_density")
    if orfs:
        return orfs["uniform_density"]
    context = record.get("context")
    return context["uniform_density"] if context else None


def _estimate(record, overflow="0.1"):
    estimates = (record or {}).get("estimates") or {}
    found = estimates.get(overflow)
    return found["estimated_density"] if found else None


def _search_converged(record, overflow="0.1"):
    """Did gpl's own binary search arrive, or did it warn and return?

    GPL-0186 says the search ran out of iterations and the value is the
    best it had. Quoting such a value as "the estimate" without saying so
    would report a number the tool itself disowned.
    """
    estimates = (record or {}).get("estimates") or {}
    found = estimates.get(overflow)
    return found.get("search_converged") if found else None


def threshold(records):
    """(highest miss, lowest hit) as (rung, density) pairs.

    Only rungs that actually produced a global placement count; a rung
    that never built (density above 1.0) is not evidence about where the
    threshold sits.
    """
    usable = [
        r for r in records if r.get("gp") and rung_index(r) is not None
    ]
    misses = [r for r in usable if not r["gp"]["converged"]]
    hits = [r for r in usable if r["gp"]["converged"]]
    lowest_hit = min(hits, key=rung_index) if hits else None
    below = [
        r
        for r in misses
        if lowest_hit is None or rung_index(r) < rung_index(lowest_hit)
    ]
    highest_miss = max(below, key=rung_index) if below else None
    return highest_miss, lowest_hit


def first_overflow(record):
    """Overflow at gpl's first reported iteration.

    The estimate is computed on the placement as it stands before the
    solve, and claims to produce the requested overflow there. The first
    row of gpl's own progress table is that same quantity, measured by
    the tool -- so on the `est` arm the two should agree, and any gap is
    the estimate's own arithmetic missing, not the placer's.
    """
    gp = record.get("gp") or {}
    trajectory = gp.get("trajectory") or []
    return trajectory[0]["overflow"] if trajectory else None


def table_arms(designs):
    """Per design: shipped density versus the estimate driving it."""
    rows = []
    for design in sorted(designs):
        arms = {arm(r): r for r in designs[design] if arm(r)}
        ship, est = arms.get("ship"), arms.get("est")
        if not ship and not est:
            continue
        rows.append(
            {
                "design": design,
                "ship_density": _density(ship) if ship else None,
                "est_density": _density(est) if est else None,
                "estimated": _estimate(est or ship),
                "search_converged": _search_converged(est or ship),
                "est_first_overflow": first_overflow(est) if est else None,
                "ship_first_overflow": first_overflow(ship) if ship else None,
                "est_converged": (est.get("gp") or {}).get("converged") if est else None,
                "ship_converged": (
                    (ship.get("gp") or {}).get("converged") if ship else None
                ),
                "est_iterations": (est.get("gp") or {}).get("iterations") if est else None,
                "ship_iterations": (
                    (ship.get("gp") or {}).get("iterations") if ship else None
                ),
                "est_hpwl": (est.get("gp") or {}).get("final_hpwl") if est else None,
                "ship_hpwl": (ship.get("gp") or {}).get("final_hpwl") if ship else None,
            }
        )
    return rows


def render_arms(rows):
    if not rows:
        return NOT_MEASURED
    lines = [
        "| design | shipped density | estimated density | gpl's search "
        "converged | overflow at gpl's first iteration (shipped / "
        "estimate-driven) | placement converged | iterations (shipped / "
        "estimate-driven) | final HPWL um (shipped / estimate-driven) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {} | {} | {} | {} | {} / {} | {} | {} / {} | {} / {} |".format(
                row["design"],
                _fmt(row["ship_density"]),
                _fmt(row["est_density"]),
                {True: "yes", False: "**no (GPL-0186)**"}.get(
                    row["search_converged"], "-"
                ),
                _fmt(row["ship_first_overflow"]),
                _fmt(row["est_first_overflow"]),
                "yes" if row["est_converged"] else "no",
                row["ship_iterations"] or "-",
                row["est_iterations"] or "-",
                _fmt_hpwl(row["ship_hpwl"]),
                _fmt_hpwl(row["est_hpwl"]),
            )
        )
    return "\n".join(lines)


def _fmt_hpwl(value):
    return "-" if value is None else "{:.3e}".format(float(value))


def _metric(record, key):
    metrics = (record or {}).get("metrics") or {}
    return metrics.get("globalplace__" + key)


def table_knob_sensitivity(designs):
    """Across the ladder, how much does the density knob move anything?

    The threshold table can only say whether global placement arrived.
    This one asks the question a maintainer would ask next: over the
    whole range of densities the command could return, how far does the
    result actually move? A knob whose whole range moves wirelength by a
    fraction of a percent is a knob whose exact value does not matter,
    and an estimate of it cannot be worth much either way.
    """
    rows = []
    for design in sorted(designs):
        ladder = [
            r
            for r in designs[design]
            if rung_index(r) is not None and _metric(r, "route__wirelength__estimated")
        ]
        if len(ladder) < 2:
            continue
        ladder.sort(key=rung_index)
        wirelength = [_metric(r, "route__wirelength__estimated") for r in ladder]
        best = min(ladder, key=lambda r: _metric(r, "route__wirelength__estimated"))
        arms = {arm(r): r for r in designs[design] if arm(r)}
        slack = [_metric(r, "timing__setup__ws") for r in ladder]
        density = [_density(r) for r in ladder if _density(r) is not None]
        rows.append(
            {
                "design": design,
                "rungs": len(ladder),
                "density_low": min(density) if density else None,
                "density_high": max(density) if density else None,
                "wirelength_low": min(wirelength),
                "wirelength_high": max(wirelength),
                "best_density": _density(best),
                "est_density": (
                    _density(arms["est"]) if arms.get("est") else None
                ),
                "wirelength_spread_pct": (
                    100.0 * (max(wirelength) - min(wirelength)) / min(wirelength)
                ),
                "slack_low": min(s for s in slack if s is not None) if any(
                    s is not None for s in slack
                ) else None,
                "slack_high": max(s for s in slack if s is not None) if any(
                    s is not None for s in slack
                ) else None,
            }
        )
    return rows


def render_knob(rows):
    if not rows:
        return NOT_MEASURED
    lines = [
        "| design | rungs | density range | estimated wirelength um "
        "(min - max) | spread | setup worst slack (min - max) | density at "
        "the best wirelength | the estimate chose |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {} | {} | {} - {} | {:.1f} - {:.1f} | {:.1f}% | {} - {} | "
            "{} | {} |".format(
                row["design"],
                row["rungs"],
                _fmt(row["density_low"]),
                _fmt(row["density_high"]),
                row["wirelength_low"],
                row["wirelength_high"],
                row["wirelength_spread_pct"],
                _fmt(row["slack_low"]),
                _fmt(row["slack_high"]),
                _fmt(row["best_density"]),
                _fmt(row["est_density"]),
            )
        )
    return "\n".join(lines)


def table_estimate_vs_actual(designs):
    rows = []
    for design in sorted(designs):
        records = designs[design]
        miss, hit = threshold(records)
        witness = next((r for r in records if r.get("context")), None)
        # What the design actually placed at, not what its config.mk
        # happens to set: riscv32i sets both PLACE_DENSITY and
        # PLACE_DENSITY_LB_ADDON, and ORFS uses the addon. Reading the
        # variable rather than the arm would quote 0.60 for a run that
        # used 0.749.
        ship = next(
            (r for r in records if arm(r) == "ship" and _density(r) is not None),
            None,
        )
        estimate = next(
            (_estimate(r) for r in records if _estimate(r) is not None), None
        )
        uniform = next((_uniform(r) for r in records if _uniform(r)), None)
        rows.append(
            {
                "design": design,
                "uniform": uniform,
                "estimated": estimate,
                "miss": _density(miss) if miss else None,
                "hit": _density(hit) if hit else None,
                "shipped_addon": (
                    witness["context"].get("place_density_lb_addon")
                    if witness
                    else None
                ),
                "shipped_density": (
                    _density(ship)
                    if ship
                    else (witness["context"].get("place_density") if witness else None)
                ),
                "samples": len(records),
            }
        )
    return rows


def render(rows):
    if not rows:
        return NOT_MEASURED
    lines = [
        "| design | uniform | shipped | estimated @ overflow 0.1 | "
        "threshold bracket (miss, hit) | estimate - hit | samples |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        bracket = "not bracketed"
        if row["miss"] is not None and row["hit"] is not None:
            bracket = "({:.3f}, {:.3f}]".format(row["miss"], row["hit"])
        elif row["hit"] is not None:
            bracket = "<= {:.3f} (hit at the bottom rung)".format(row["hit"])
        elif row["miss"] is not None:
            bracket = "> {:.3f} (no rung converged)".format(row["miss"])
        error = ""
        if row["estimated"] is not None and row["hit"] is not None:
            error = "{:+.3f}".format(row["estimated"] - row["hit"])
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                row["design"],
                _fmt(row["uniform"]),
                _fmt_maybe(row["shipped_density"] or row["shipped_addon"]),
                _fmt(row["estimated"]),
                bracket,
                error or "-",
                row["samples"],
            )
        )
    return "\n".join(lines)


def _fmt_maybe(value):
    """Three decimals for a number, verbatim for anything else.

    The shipped density comes back as a float from the arm that ran and
    as config.mk's own string when no arm did; printing the float raw put
    0.7489999806880951 in a column of three-decimal numbers.
    """
    try:
        return "{:.3f}".format(float(value))
    except (TypeError, ValueError):
        return "-" if value in (None, "") else str(value)


def _fmt(value):
    return "-" if value is None else "{:.3f}".format(float(value))


def csv(records):
    header = (
        "design,variant,repeat,density,uniform,estimated_0.1,"
        "estimate_search_converged,converged,"
        "final_overflow,iterations,hit_max_iter,diverged,wall_s,"
        "loadavg_at_start,threads,started_utc"
    )
    lines = [header]
    for record in sorted(
        records, key=lambda r: (r["design"], r["variant"], r.get("repeat", 0))
    ):
        gp = record.get("gp") or {}
        lines.append(
            ",".join(
                str(value)
                for value in [
                    record["design"],
                    record["variant"],
                    record.get("repeat", 0),
                    _density(record),
                    _uniform(record),
                    _estimate(record),
                    _search_converged(record),
                    gp.get("converged"),
                    gp.get("final_overflow"),
                    gp.get("iterations"),
                    gp.get("hit_max_iter"),
                    gp.get("diverged"),
                    round(record.get("wall_s", 0), 1),
                    record.get("loadavg_at_start"),
                    record.get("threads"),
                    record.get("started_utc"),
                ]
            )
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=RESULTS_DIR)
    parser.add_argument("--csv", action="store_true")
    args = parser.parse_args()

    records = load(args.results)
    if args.csv:
        print(csv(records))
        return 0

    designs = by_design(records)
    print("## What the command says, and what global placement then does\n")
    print(render_arms(table_arms(designs)))
    print("\n## Estimated versus actual\n")
    print(render(table_estimate_vs_actual(designs)))
    print("\n" + render_missing(missing(designs)))
    print("\n## Does the knob move anything at all?\n")
    print(render_knob(table_knob_sensitivity(designs)))
    print(
        "\nThe bracket is (highest density at which global placement missed "
        "overflow {}, lowest at which it hit it]. Density is what ORFS told "
        "global_placement to use, read back from the stage log.".format(
            harvest.DEFAULT_OVERFLOW
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
